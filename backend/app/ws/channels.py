"""WebSocket 消息路由  ——  薄层，所有业务逻辑委托给 IntentDispatcher。

消息协议（前端 → 后端）：
  chat.user_text   — 文字输入（替代旧 transcript）
  audio.commit     — 录音结束，触发 ASR（替代旧 audio_end）
  barge_in         — 用户打断正在播放的 TTS
  confirm          — 用户确认 pending_intent
  cancel_pending   — 取消待确认意图
  cancel           — 取消正在执行的任务
  [binary frame]   — PCM Int16 音频帧（替代旧 audio_chunk base64）

  ── 旧协议兼容（逐步废弃）───────────────────────────────────────
  audio_chunk      — Base64 PCM 块（旧）
  audio_end        — 音频结束（旧）
  transcript       — 纯文本输入（旧）

消息协议（后端 → 前端）：
  connected        — 连接建立
  state.update     — 会话状态变更
  asr.partial      — ASR 实时中间结果（预留）
  asr.final        — ASR 最终转写结果
  chat.delta       — LLM 流式文本片段
  chat.done        — LLM 本轮完整回复
  tts.chunk        — TTS 音频分段
  tts.done         — 本轮所有 TTS 分段发送完毕
  tts_end          — 立即停止播放（barge-in 触发）
  pending_intent   — 进入待确认状态
  pending_cleared  — pending 已取消
  slot_filling     — 要求补槽位
  question         — AI 文字反问（兼容保留）
  user_message     — 用户消息气泡回显
  command_sent     — 指令已下发
  command_result   — C++ 回调结果
  balance_reading  — 天平实时读数
  balance_over_limit — 天平超限
  error            — 错误信息
  ping             — 心跳
"""

from __future__ import annotations

import asyncio
import binascii
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.services.ai.llm import get_llm_async
from app.services.ai.stt import AudioSession, get_whisper_client
from app.services.ai.tts import get_tts_client
from app.services.ai_extractor import AIExtractor
from app.services.asr.lexicon import DomainLexicon
from app.services.asr.normalizer import normalize_asr_text
from app.services.dialogue_service import (
    build_cancel_reply,
    build_draft_reply,
    build_proposal_reply,
)
from app.services.dialog.dispatcher import (
    DispatchResult,
    IntentDispatcher,
)
from app.services.dialog.session import Session
from app.services.dialog.state_machine import get_state_machine
from app.services.device.control_client import get_control_client
from app.services.draft_manager import draft_manager
from app.services.intent_router import route_intent
from app.core.config import settings
from app.ws.manager import ws_manager

router = APIRouter(tags=["WebSocket"])
logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── 句子切分（TTS 分段起播） ─────────────────────────────────────

_SENTENCE_ENDS = frozenset("。？！；\n")
_SOFT_ENDS = frozenset("，,")
_SOFT_MAX_LEN = 20
_MIN_TTS_LEN = 10


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """从 LLM 流式缓冲区提取完整可播短句，返回 (句子列表, 剩余缓冲)。"""
    sentences: list[str] = []
    start = 0
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_ENDS:
            seg = buf[start : i + 1].strip()
            if seg:
                sentences.append(seg)
            start = i + 1
        elif ch in _SOFT_ENDS and (i - start) >= _SOFT_MAX_LEN:
            seg = buf[start : i + 1].strip()
            if seg:
                sentences.append(seg)
            start = i + 1
    return sentences, buf[start:]


# ─── 应用 DispatchResult → WS 消息 ───────────────────────────────

async def _apply_dispatch_result(client_id: str, result: DispatchResult) -> None:
    if result.pending_only:
        if result.pending_payload == "clear":
            await ws_manager.send_json(client_id, {"type": "pending_cleared"})
        elif isinstance(result.pending_payload, dict):
            await ws_manager.send_json(
                client_id, {"type": "pending_intent", "data": result.pending_payload}
            )
        return

    if result.pending_payload == "clear":
        await ws_manager.send_json(client_id, {"type": "pending_cleared"})
    elif isinstance(result.pending_payload, dict):
        await ws_manager.send_json(
            client_id, {"type": "pending_intent", "data": result.pending_payload}
        )

    if result.slot_filling:
        await ws_manager.send_json(
            client_id, {"type": "slot_filling", "data": result.slot_filling}
        )

    _reply_text = result.dialog_text or result.speak_text
    if _reply_text:
        await ws_manager.send_json(
            client_id, {"type": "chat.done", "text": _reply_text}
        )

    if result.speak_text:
        await ws_manager.send_json(
            client_id, {"type": "question", "text": result.speak_text}
        )
        asyncio.create_task(_tts_send_single(client_id, result.speak_text))

    if result.command_id:
        await ws_manager.send_json(
            client_id, {"type": "command_sent", "command_id": result.command_id}
        )

    await ws_manager.send_json(
        client_id, {"type": "state.update", "state": result.state}
    )

    if result.error_code:
        await ws_manager.send_json(
            client_id,
            {
                "type": "error",
                "code": result.error_code,
                "message": result.error_message or "",
            },
        )


async def _send_draft_update(client_id: str, draft) -> None:
    await ws_manager.send_json(
        client_id,
        {
            "type": "draft_update",
            "data": {
                "draft_id": draft.draft_id,
                "session_id": draft.session_id,
                "task_type": draft.task_type.value,
                "status": draft.status.value,
                "complete": draft.complete,
                "missing_slots": draft.missing_slots,
                "ready_for_review": draft.ready_for_review,
                "current_draft": draft.current_draft,
                "created_at": draft.created_at.isoformat(),
                "updated_at": draft.updated_at.isoformat(),
            },
        },
    )


# ─── TTS 辅助 ────────────────────────────────────────────────────

async def _tts_send_single(client_id: str, text: str) -> None:
    """整段文本合成并推前端（非流式路径用）。"""
    from app.core.config import settings
    tts = get_tts_client()
    result = await tts.speak(text, speed=settings.tts_speed)
    if not result or not result.get("audio_base64"):
        logger.warning("TTS 无返回或缺少 audio_base64，跳过语音播放")
        return
    await ws_manager.send_json(
        client_id,
        {
            "type": "tts.chunk",
            "data": result["audio_base64"],
            "sample_rate": result.get("sample_rate", 44100),
            "format": result.get("format", "pcm_int16"),
            "seq": 0,
            "text": text,
        },
    )
    await ws_manager.send_json(client_id, {"type": "tts.done"})


async def _tts_worker(
    client_id: str,
    queue: asyncio.Queue,
) -> None:
    """串行消费句子队列，每句调一次 TTS 并推 tts.chunk。None 为终止信号。"""
    tts = get_tts_client()
    seq = 0
    while True:
        item = await queue.get()
        if item is None:
            await ws_manager.send_json(client_id, {"type": "tts.done"})
            queue.task_done()
            break
        try:
            from app.core.config import settings
            result = await tts.speak(item, speed=settings.tts_speed)
        except Exception:
            logger.exception("TTS speak 异常，跳过片段 seq=%d", seq)
            queue.task_done()
            seq += 1
            continue

        if result and result.get("audio_base64"):
            await ws_manager.send_json(
                client_id,
                {
                    "type": "tts.chunk",
                    "data": result["audio_base64"],
                    "sample_rate": result.get("sample_rate", 44100),
                    "format": result.get("format", "pcm_int16"),
                    "seq": seq,
                    "text": item,
                },
            )
        queue.task_done()
        seq += 1


async def _stop_tts_playback(client_id: str) -> None:
    tts = get_tts_client()
    try:
        await tts.stop()
    except Exception:
        logger.debug("TTS stop 异常（忽略）")
    await ws_manager.send_json(client_id, {"type": "tts_end"})


# ─── 流式对话 + 分段 TTS ─────────────────────────────────────────

async def _stream_dialog_with_tts(
    dispatcher: IntentDispatcher,
    session: Session,
    client_id: str,
    user_text: str,
) -> None:
    """LLM 流式输出 → 实时切句 → 串行 TTS → 推前端。
    TTS 采用累积策略：短句合并到 _MIN_TTS_LEN 再合成，减少调用次数。"""
    tts_queue: asyncio.Queue = asyncio.Queue()
    tts_task = asyncio.create_task(_tts_worker(client_id, tts_queue))

    buf = ""
    full_text = ""
    tts_acc = ""
    seq = 0

    try:
        async for token in dispatcher.llm.process_dialog_stream(
            user_text=user_text,
            dialog_history=session.dialog_history[:-1],
        ):
            buf += token
            full_text += token

            sentences, buf = _split_sentences(buf)
            for sent in sentences:
                await ws_manager.send_json(
                    client_id, {"type": "chat.delta", "text": sent, "seq": seq}
                )
                # TTS 累积：凑够 _MIN_TTS_LEN 或遇到句子结束符才入队
                tts_acc += sent
                if len(tts_acc) >= _MIN_TTS_LEN:
                    await tts_queue.put(tts_acc)
                    tts_acc = ""
                seq += 1

    except asyncio.CancelledError:
        await tts_queue.put(None)
        tts_task.cancel()
        raise
    except Exception:
        logger.exception("[stream_dialog] LLM streaming 异常")
        await tts_queue.put(None)
        await tts_task
        fallback = "抱歉，处理时出现异常，请重试。"
        await ws_manager.send_json(client_id, {"type": "chat.done", "text": fallback})
        await ws_manager.send_json(client_id, {"type": "state.update", "state": "ERROR"})
        session.add_assistant_dialog(fallback)
        return

    remaining = buf.strip()
    if remaining:
        await ws_manager.send_json(
            client_id, {"type": "chat.delta", "text": remaining, "seq": seq}
        )
        tts_acc += remaining

    if tts_acc:
        await tts_queue.put(tts_acc)
    await tts_queue.put(None)

    full_text_clean = full_text.strip() or "我正在思考..."
    await ws_manager.send_json(
        client_id, {"type": "chat.done", "text": full_text_clean}
    )

    session.add_assistant_dialog(full_text_clean)

    await tts_task

    # 对话阶段结束，异步触发轻量 intent 解析（查询类意图自动执行）
    auto_result: DispatchResult | None = None
    try:
        auto_result = await dispatcher.try_auto_resolve(session, user_text)
    except Exception:
        logger.exception("[stream_dialog] try_auto_resolve 异常")

    # 查询类意图自动执行结果直接推送
    if auto_result is not None and auto_result.output_type == "execute_now":
        auto_result.pending_payload = "clear"
        await _apply_dispatch_result(client_id, auto_result)
        # 推送配方详细信息（如果有）
        if auto_result.debug and auto_result.debug.get("formula_info"):
            await ws_manager.send_json(
                client_id,
                {
                    "type": "formula_info",
                    "data": auto_result.debug["formula_info"],
                },
            )
        logger.info(
            "[%s] _stream_dialog_with_tts auto_resolve executed, skip awaiting_confirmation",
            client_id,
        )
        if session.session_id:
            asyncio.create_task(_persist_session(session.session_id, session))
        return

    # 对话阶段结束，进入等待确认状态（用户可点击"确认执行"或继续对话）
    if session.session_id:
        asyncio.create_task(_persist_session(session.session_id, session))
    await ws_manager.send_json(
        client_id, {"type": "state.update", "state": "awaiting_confirmation"}
    )


# ─── 统一文本输入处理 ─────────────────────────────────────────────

async def _process_text_input(
    dispatcher: IntentDispatcher,
    session: Session,
    client_id: str,
    user_text: str,
) -> None:
    """所有文本输入（ASR / 直接输入）的统一处理路径。"""
    import time as _time
    _t0 = _time.time()
    logger.info("[%s] _process_text_input START text=%r", client_id, user_text[:60])

    await ws_manager.send_json(
        client_id, {"type": "state.update", "state": "thinking"}
    )

    active_draft = draft_manager.get_active(session.session_id)
    route = route_intent(user_text, active_draft)

    if route.route == "cancel_task":
        cancelled = draft_manager.cancel(session.session_id)
        session.reset()
        reply = build_cancel_reply(cancelled is not None)
        await ws_manager.send_json(client_id, {"type": "pending_cleared"})
        if cancelled is not None:
            await _send_draft_update(client_id, cancelled)
        await ws_manager.send_json(client_id, {"type": "chat.done", "text": reply})
        await ws_manager.send_json(client_id, {"type": "state.update", "state": "IDLE"})
        return

    if route.route == "clarify":
        reply = route.clarification or "请补充更多信息。"
        session.add_assistant_dialog(reply)
        await ws_manager.send_json(client_id, {"type": "chat.done", "text": reply})
        await ws_manager.send_json(client_id, {"type": "state.update", "state": "ASKING"})
        return

    if route.route in ("start_task", "update_task") and route.task_type is not None:
        session.add_user_dialog(user_text)
        draft = draft_manager.get_active(session.session_id)
        current = draft.current_draft if draft else {}
        extractor = AIExtractor(dispatcher.llm)
        patch = await extractor.extract_patch(route.task_type, current, user_text)
        draft = draft_manager.get_active(session.session_id)
        if draft is None:
            draft = draft_manager.start(session.session_id, route.task_type)
        draft_manager.record_event(draft, "patch_extracted", user_message=user_text, ai_patch=patch)
        draft = draft_manager.apply_patch(
            session.session_id,
            route.task_type,
            patch,
            user_message=user_text,
            ai_patch=patch,
        )
        reply = build_draft_reply(draft)
        session.add_assistant_dialog(reply)
        await _send_draft_update(client_id, draft)
        await ws_manager.send_json(client_id, {"type": "chat.done", "text": reply})
        await ws_manager.send_json(
            client_id,
            {
                "type": "state.update",
                "state": "awaiting_confirmation" if draft.ready_for_review else "ASKING",
            },
        )
        return

    if route.route == "confirm_task" and active_draft is not None:
        session.add_user_dialog(user_text)
        try:
            intent_data = draft_manager.create_proposal_intent(
                active_draft,
                user_message=user_text,
            )
        except ValueError as e:
            await ws_manager.send_json(
                client_id,
                {"type": "error", "code": "DRAFT_NOT_READY", "message": str(e)},
            )
            return
        reply = build_proposal_reply(intent_data)
        session.add_assistant_dialog(reply)
        await _send_draft_update(client_id, active_draft)
        await ws_manager.send_json(client_id, {"type": "chat.done", "text": reply})
        result = await dispatcher.create_pending_from_intent(session, intent_data)
        await _apply_dispatch_result(client_id, result)
        return

    if route.route == "query_device_status":
        result = await dispatcher.handle_query_device_status(session)
        await _apply_dispatch_result(client_id, result)
        return

    if route.route == "query_inventory":
        result = await dispatcher.handle_query_stock(session, user_text)
        await _apply_dispatch_result(client_id, result)
        return

    # 状态驱动：awaiting_confirmation 下先解释用户意图
    if session.state == "awaiting_confirmation" and session.has_active_pending():
        logger.info("[%s] 状态 awaiting_confirmation，走确认态解析", client_id)
        try:
            result = await dispatcher.handle_confirmation_input(session, user_text)
        except Exception as e:
            logger.exception("[%s] handle_confirmation_input 异常: %s", client_id, e)
            result = DispatchResult(
                error_code="INTERNAL_ERROR",
                error_message=str(e),
                state="ERROR",
            )
        await _apply_dispatch_result(client_id, result)
        logger.info(
            "[%s] _process_text_input END (confirmation) elapsed=%.3fs",
            client_id, _time.time() - _t0,
        )
        return

    # 普通对话路径：流式 dialog + 分段 TTS
    session.add_user_dialog(user_text)

    if session.is_over_limit(settings.dialog_max_rounds):
        session.reset()
        result = DispatchResult(
            speak_text="对话轮数过多，已重置，请重新描述您的操作",
            state="IDLE",
            pending_payload="clear",
        )
        await _apply_dispatch_result(client_id, result)
        return

    await _stream_dialog_with_tts(dispatcher, session, client_id, user_text)

    logger.info(
        "[%s] _process_text_input END elapsed=%.3fs", client_id, _time.time() - _t0
    )


# ─── 会话持久化辅助 ───────────────────────────────────────────────

_last_persist_time: dict[str, float] = {}
_PERSIST_INTERVAL_SEC = 3.0


async def _persist_session(session_id: str, session: Session) -> None:
    """将会话消息异步持久化到 DialogSession 表（节流 3 秒）。"""
    import time
    now = time.time()
    last = _last_persist_time.get(session_id, 0.0)
    if now - last < _PERSIST_INTERVAL_SEC:
        return
    _last_persist_time[session_id] = now

    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.models.dialog_session import DialogSession
            stmt = select(DialogSession).where(DialogSession.session_id == session_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None:
                record = DialogSession(
                    session_id=session_id,
                    messages_json="[]",
                    round_count=session.round_count,
                )
                db.add(record)
            record.messages = session.dialog_history
            record.round_count = session.round_count
            record.updated_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        logger.exception("[_persist_session] 持久化失败 session_id=%s", session_id)


async def _force_persist_session(session_id: str, session: Session) -> None:
    """强制立即持久化（断线时调用）。"""
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.models.dialog_session import DialogSession
            stmt = select(DialogSession).where(DialogSession.session_id == session_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None:
                record = DialogSession(
                    session_id=session_id,
                    messages_json="[]",
                    round_count=session.round_count,
                )
                db.add(record)
            record.messages = session.dialog_history
            record.round_count = session.round_count
            record.updated_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        logger.exception("[_force_persist_session] 持久化失败 session_id=%s", session_id)


# ─── /ws/voice ────────────────────────────────────────────────────

@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    client_id = f"voice_{uuid.uuid4().hex[:12]}"

    session_id = websocket.query_params.get("session_id") or ""
    if not session_id:
        session_id = str(uuid.uuid4())

    llm = await get_llm_async()
    state_machine = get_state_machine()
    control_client = get_control_client()
    dispatcher = IntentDispatcher(
        llm=llm,
        state_machine=state_machine,
        control_client=control_client,
    )
    whisper_client = get_whisper_client()

    # ── ASR 领域热词库（本地离线，不依赖云端） ───────────────────────
    lexicon = DomainLexicon()
    try:
        await lexicon.load_from_db()
    except Exception:
        logger.exception("[%s] 热词库数据库加载失败，使用默认词表", client_id)

    session = Session(
        session_id=session_id,
        history_max_messages=settings.dialog_history_max_messages,
    )
    audio_session = AudioSession()

    # 加载历史消息
    if session_id:
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.models.dialog_session import DialogSession
                stmt = select(DialogSession).where(DialogSession.session_id == session_id)
                result = await db.execute(stmt)
                record = result.scalar_one_or_none()
                if record and record.messages:
                    session.dialog_history = record.messages[: settings.dialog_history_max_messages]
                    session.round_count = record.round_count
                    logger.info(
                        "[%s] 加载历史会话 session_id=%s messages=%d",
                        client_id, session_id, len(record.messages),
                    )
        except Exception:
            logger.exception("[%s] 加载历史会话失败 session_id=%s", client_id, session_id)

    await ws_manager.connect(client_id, websocket)
    heartbeat_task: asyncio.Task | None = None
    if settings.ws_ping_interval_sec > 0:
        heartbeat_task = asyncio.create_task(_heartbeat_loop(client_id))

    try:
        await ws_manager.send_json(
            client_id,
            {"type": "connected", "client_id": client_id, "timestamp": _now_iso()},
        )

        while True:
            raw_data = await websocket.receive()

            # ── 二进制音频帧（新协议）──────────────────────────────
            if "bytes" in raw_data:
                frame = raw_data["bytes"]
                if not isinstance(frame, (bytes, bytearray)):
                    continue
                if not audio_session.chunks:
                    session.transition_to("listening")
                    await _stop_tts_playback(client_id)
                audio_session.add_chunk(bytes(frame))
                duration_ms = audio_session.get_duration_ms()
                if duration_ms > settings.audio_max_buffer_ms:
                    await ws_manager.send_json(
                        client_id,
                        {"type": "error", "code": "AUDIO_TOO_LONG",
                         "message": f"音频长度 {duration_ms}ms 超出限制"},
                    )
                    audio_session.reset()
                    session.transition_to("idle")
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "idle"}
                    )
                else:
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "listening"}
                    )
                continue

            # ── JSON 文本消息 ────────────────────────────────────────
            raw = raw_data.get("text", "")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_json(
                    client_id,
                    {"type": "error", "code": "INVALID_JSON", "message": "无效 JSON"},
                )
                continue

            msg_type: str = msg.get("type", "")

            # ── 旧协议：audio_chunk（base64）────────────────────────
            if msg_type == "audio_chunk":
                chunk_data = msg.get("data")
                if not isinstance(chunk_data, str):
                    continue
                if not audio_session.chunks:
                    session.transition_to("listening")
                    await _stop_tts_playback(client_id)
                try:
                    audio_session.add_base64_chunk(chunk_data)
                except (binascii.Error, ValueError):
                    await ws_manager.send_json(
                        client_id,
                        {
                            "type": "error",
                            "code": "INVALID_AUDIO_CHUNK",
                            "message": "无效音频数据，请重新录音",
                        },
                    )
                    audio_session.reset()
                    session.transition_to("idle")
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "idle"}
                    )
                    continue
                duration_ms = audio_session.get_duration_ms()
                if duration_ms > settings.audio_max_buffer_ms:
                    await ws_manager.send_json(
                        client_id,
                        {"type": "error", "code": "AUDIO_TOO_LONG",
                         "message": f"音频长度 {duration_ms}ms 超出限制"},
                    )
                    audio_session.reset()
                    session.transition_to("idle")
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "idle"}
                    )
                else:
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "listening"}
                    )
                continue

            # ── audio.commit（新）或 audio_end（旧）─────────────────
            if msg_type in ("audio.commit", "audio_end"):
                duration_ms = audio_session.get_duration_ms()
                if duration_ms < 250:
                    audio_session.reset()
                    session.transition_to("idle")
                    await _apply_dispatch_result(
                        client_id,
                        DispatchResult(speak_text="语音太短，请重新输入", state="IDLE"),
                    )
                    continue

                session.transition_to("recognizing")
                await ws_manager.send_json(
                    client_id, {"type": "state.update", "state": "recognizing"}
                )
                logger.info(
                    "开始 ASR 转写，音频长度 %d ms，客户端 %s", duration_ms, client_id
                )

                transcribe_result = await whisper_client.transcribe_chunks(
                    audio_session.chunks
                )
                audio_session.reset()

                if transcribe_result.error:
                    session.transition_to("idle")
                    await ws_manager.send_json(
                        client_id,
                        {"type": "error", "code": "ASR_ERROR",
                         "message": f"语音识别失败: {transcribe_result.error}"},
                    )
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "idle"}
                    )
                    continue

                raw_text = transcribe_result.text
                if not raw_text or not raw_text.strip():
                    session.transition_to("idle")
                    await ws_manager.send_json(
                        client_id,
                        {"type": "error", "code": "ASR_EMPTY", "message": "语音识别结果为空"},
                    )
                    await ws_manager.send_json(
                        client_id, {"type": "state.update", "state": "idle"}
                    )
                    continue

                # ── ASR 后处理：领域热词纠错与归一化 ─────────────────────
                asr_result = normalize_asr_text(raw_text, lexicon)
                normalized_text = asr_result["normalized_text"]
                corrections = asr_result["corrections"]
                suggestions = asr_result["suggestions"]
                needs_confirmation = asr_result["needs_confirmation"]

                logger.info(
                    "[%s] ASR 转写完成: raw=%s normalized=%s corrections=%d suggestions=%d",
                    client_id, raw_text, normalized_text,
                    len(corrections), len(suggestions),
                )

                # 向后兼容：旧前端只读取 text；新前端可读取 raw_text / normalized_text
                await ws_manager.send_json(
                    client_id,
                    {
                        "type": "asr.final",
                        "text": normalized_text,
                        "raw_text": raw_text,
                        "normalized_text": normalized_text,
                        "corrections": corrections,
                        "suggestions": suggestions,
                        "needs_confirmation": needs_confirmation,
                        "duration_ms": duration_ms,
                    },
                )
                await ws_manager.send_json(
                    client_id,
                    {"type": "user_message", "text": normalized_text, "timestamp": _now_iso()},
                )
                await _process_text_input(dispatcher, session, client_id, normalized_text)
                continue

            # ── chat.user_text（新）或 transcript（旧）──────────────
            if msg_type in ("chat.user_text", "transcript"):
                user_text = msg.get("text")
                if not isinstance(user_text, str) or not user_text.strip():
                    await ws_manager.send_json(
                        client_id,
                        {"type": "error", "code": "INVALID_TEXT", "message": "缺少有效文本"},
                    )
                    continue
                user_text = user_text.strip()
                await ws_manager.send_json(
                    client_id, {"type": "asr.final", "text": user_text}
                )
                await _process_text_input(dispatcher, session, client_id, user_text)
                continue

            # ── barge_in ─────────────────────────────────────────────
            if msg_type == "barge_in":
                session.transition_to("interrupted")
                await _stop_tts_playback(client_id)
                continue

            # ── confirm ──────────────────────────────────────────────
            if msg_type == "confirm":
                await ws_manager.send_json(
                    client_id, {"type": "state.update", "state": "PROCESSING"}
                )
                if session.has_active_pending():
                    result = await dispatcher.handle_confirm(session)
                else:
                    # 兼容旧流程：没有后端 proposal 时，再从对话历史解析。
                    try:
                        result = await dispatcher.resolve_intent_from_dialog(session)
                    except Exception:
                        logger.exception("[confirm] intent 解析异常")
                        result = DispatchResult(
                            error_code="INTENT_PARSE_ERROR",
                            error_message="意图解析失败，请重试",
                            state="ERROR",
                        )
                await _apply_dispatch_result(client_id, result)
                if session.session_id:
                    asyncio.create_task(_persist_session(session.session_id, session))
                continue

            # ── cancel_pending ───────────────────────────────────────
            if msg_type == "cancel_pending":
                result = await dispatcher.handle_cancel_pending(session)
                await _apply_dispatch_result(client_id, result)
                if session.session_id:
                    asyncio.create_task(_persist_session(session.session_id, session))
                continue

            # ── cancel ───────────────────────────────────────────────
            if msg_type == "cancel":
                result = await dispatcher.handle_cancel_current_task(session)
                await _apply_dispatch_result(client_id, result)
                if session.session_id:
                    asyncio.create_task(_persist_session(session.session_id, session))
                continue

            await ws_manager.send_json(
                client_id,
                {"type": "error", "code": "UNSUPPORTED_MESSAGE",
                 "message": f"不支持的消息类型: {msg_type}"},
            )

    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except RuntimeError as e:
        if "WebSocket is not connected" in str(e):
            logger.warning("WebSocket 客户端提前断开: %s", client_id)
            ws_manager.disconnect(client_id)
        else:
            logger.exception("voice_websocket RuntimeError: %s", e)
            ws_manager.disconnect(client_id)
    except Exception:
        logger.exception("voice_websocket 未预期异常")
        await ws_manager.send_json(
            client_id,
            {"type": "error", "code": "INTERNAL_ERROR", "message": "服务内部错误，请重试"},
        )
        ws_manager.disconnect(client_id)
    finally:
        # 断线时强制持久化会话
        if session.session_id:
            try:
                await _force_persist_session(session.session_id, session)
            except Exception:
                logger.exception("[%s] 断线持久化失败", client_id)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass


async def _heartbeat_loop(client_id: str) -> None:
    interval = max(5.0, settings.ws_ping_interval_sec)
    try:
        while True:
            await asyncio.sleep(interval)
            ok = await ws_manager.send_json(
                client_id, {"type": "ping", "ts": _now_iso()}
            )
            if not ok:
                return
    except asyncio.CancelledError:
        raise


# ─── 天平广播（由 balance 驱动层调用）────────────────────────────

async def push_balance(mass_mg: float, stable: bool) -> None:
    await ws_manager.broadcast(
        {
            "type": "balance_reading",
            "value_mg": mass_mg,
            "stable": stable,
            "timestamp": _now_iso(),
        }
    )


async def push_balance_over_limit(mass_mg: float) -> None:
    await ws_manager.broadcast(
        {
            "type": "balance_over_limit",
            "value_mg": mass_mg,
            "timestamp": _now_iso(),
        }
    )
