"""TTS 客户端 —— MeloTTS HTTP 服务封装。

- 对应服务: melotts-git/melo/tts_server.py
- 返回值包含 audio_base64 + sample_rate，供后端通过 WebSocket 推给前端播放
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TTSClient:
    """MeloTTS HTTP 客户端。禁用系统代理，避免本地请求被 http_proxy 拦截。"""

    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = httpx.AsyncHTTPTransport(proxy=None)

    def _client(self, *, short: bool = False) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=10 if short else self.timeout,
            transport=self._transport,
            trust_env=False,
        )

    async def health(self) -> dict:
        async with self._client(short=True) as client:
            resp = await client.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()

    async def synthesize(self, text: str, play: bool = False) -> dict | None:
        try:
            payload = {"text": text, "save": True, "play": play}
            async with self._client() as client:
                resp = await client.post(f"{self.base_url}/synthesize", json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("TTS synthesize HTTP %s", e.response.status_code)
            return None
        except Exception as e:  # noqa: BLE001 — 网络/超时统一降级
            logger.error("TTS synthesize failed: %s", e)
            return None

    async def speak(self, text: str, interrupt: bool = False, speed: float | None = None) -> dict | None:
        """调用 /speak 生成 PCM Int16，返回 dict 含 audio_base64 / sample_rate / format / duration_ms。"""
        try:
            payload: dict = {"text": text, "interrupt": interrupt}
            if speed is not None:
                payload["speed"] = speed
            async with self._client() as client:
                resp = await client.post(f"{self.base_url}/speak", json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:  # noqa: BLE001
            logger.error("TTS speak failed: %s", e)
            return None

    async def stop(self) -> dict | None:
        try:
            async with self._client(short=True) as client:
                resp = await client.post(f"{self.base_url}/stop")
                resp.raise_for_status()
                return resp.json()
        except Exception as e:  # noqa: BLE001
            logger.error("TTS stop failed: %s", e)
            return None


_tts_instance: TTSClient | None = None


def get_tts_client() -> TTSClient:
    global _tts_instance
    if _tts_instance is None:
        from app.core.config import settings
        _tts_instance = TTSClient(settings.tts_base_url, settings.tts_timeout_sec)
    return _tts_instance


def reset_tts_client() -> None:
    """仅供测试使用，清空全局单例。"""
    global _tts_instance
    _tts_instance = None


__all__ = ["TTSClient", "get_tts_client", "reset_tts_client"]
