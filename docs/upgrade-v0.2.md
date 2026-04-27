# dispenser-ai v0.2 升级与验证手册

本次重构覆盖 AI 交互、语音链路、后端结构、Jetson 启动脚本与契约统一，存在破坏性变更（WebSocket 协议、`intent_type` 命名、配置项），升级时务必按本文档操作并完成验收清单。

适用版本：`0.1.x` → `0.2.0`
执行环境：Jetson Orin NX Super 16GB（部署）/ Windows（仅审查）
预计停机时长：5–10 分钟（不含 whisper.cpp 重编译）

---

## 1. 变更概览

### 1.1 行为级变更（用户可感知）

| 项 | 旧 | 新 |
|---|---|---|
| AI 反问的语音播报 | 听不到（后端丢弃 TTS 数据） | 通过 `tts_audio` 经 WS 推到前端播放 |
| "确认执行" 按钮 | 始终可点，常返回"我没理解" | 仅在 AI 收敛到可执行意图（pending）时启用 |
| 触发执行的语音关键词 | 含 `好的 / 是的 / 可以` 等宽泛词，易误触 | 收紧到精确匹配 `{确认执行, 确认, 开始执行, 执行}` |
| 待确认意图过期时间 | 无 | 默认 60s（`PENDING_INTENT_TTL_SEC`） |
| WS 重连策略 | 固定 3s | 指数退避 1s → 15s |
| TTS 默认采样率 | 22050 | 44100（MeloTTS 中文实际值，从消息透传） |

### 1.2 协议级破坏性变更

#### `shared/intent_schema.json` v1.0 → v1.1

| 旧 intent_type | 新 intent_type |
|---|---|
| `dispense_powder` | `dispense` |
| `aliquot_powder` | `aliquot` |
| `mix_powder` | `mix` |
| `query_device_status` | `device_status` |
| `save_formula` | `formula` |
| `cancel_task` | `cancel` |

`intent_type` 与 `command_schema.command_type` 完全对齐（unknown 除外），规则引擎不再需要映射表。

#### WebSocket 新增消息（详见 [backend/app/ws/channels.py](../backend/app/ws/channels.py) 顶部注释）

后端 → 前端：`tts_audio` / `pending_intent` / `pending_cleared` / `slot_filling` / `user_message`
前端 → 后端：`cancel_pending`

`confirm` 消息不再要求带 `text` 字段。

### 1.3 后端结构重构

```
backend/app/services/
├── ai/
│   ├── llm.py          (瘦身：移除 DialogSession / reasoning_content 兜底)
│   ├── stt.py          (保留)
│   ├── tts.py          (新位置，原 services/tts_client.py)
│   └── prompts.py      (新文件，集中 system prompt 模板)
├── dialog/
│   ├── dispatcher.py   (新文件，IntentDispatcher 收敛业务逻辑)
│   ├── session.py      (新文件，含 PendingIntent + dialog/intent 历史分离)
│   ├── intent.py       (改用 jsonschema Draft-07 真校验)
│   ├── rules.py        (移除 INTENT_TO_COMMAND 映射表)
│   └── state_machine.py (保留)
└── device/
    └── control_client.py (重写：retries=2 / keepalive_expiry=3s / 返回 (ok, reason))
```

已删除：

- `backend/app/services/tts_client.py`
- `backend/app/services/dialog/session_store.py`
- `backend/app/models/dialog_session.py`
- 根目录 `check-page.mjs / check-page2.mjs / screenshot.png`

### 1.4 配置项变更

| 类型 | 配置项 |
|---|---|
| 新增 | `LLM_DIALOG_TEMPERATURE` / `LLM_INTENT_TEMPERATURE` / `PENDING_INTENT_TTL_SEC` / `CORS_ALLOWED_ORIGINS` |
| 删除 | `LLM_TEMPERATURE`（已被 dialog / intent 两套温度替代） |
| `requirements.txt` | 删除 `piper-tts`（项目实际使用 MeloTTS） |

### 1.5 LLM 模型切换

| 项 | 旧 | 新 |
|---|---|---|
| 默认模型 | Gemma 4 E4B Q6_K（~6GB 显存） | **Qwen3-4B-Instruct-2507-Q4_K_M**（~2.5GB 显存） |
| 路径 | `models/gemma4/gemma-4-E4B-it-Q6_K.gguf` | `models/Qwen/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` |
| chat template | GGUF 内嵌（`--jinja`） | GGUF 内嵌（`--jinja`，与旧配置一致，**切勿**加 `--chat-template gemma`） |
| 对话温度 | 0.7 | 0.6 |
| 意图温度（force_json） | 0.1 | **0.05** |
| 最大生成 tokens | 1024 | 768 |

**为什么调低温度**：Qwen3 在 llama.cpp 上强制 JSON 输出（`response_format=json_object`）时，偶发出现夹带解释文本或省略字段的情况，0.05 比 0.1 更稳。若生产中仍出现 JSON 解析失败，可进一步设为 0.0。

**如何回滚到 Gemma**：在 `backend/.env` 临时改回：
```env
LLM_MODEL_PATH=models/gemma4/gemma-4-E4B-it-Q6_K.gguf
LLM_DIALOG_TEMPERATURE=0.7
LLM_INTENT_TEMPERATURE=0.1
LLM_MAX_TOKENS=1024
```
并重启 `llama-server + backend` 即可。不需要改 `--chat-template`（`--jinja` 对两个模型都适用）。

---

## 2. 升级步骤（Jetson 上执行）

### 2.1 拉新代码并停旧服务

```bash
cd ~/dispenser-ai
git pull            # 或同步打包文件
./scripts/stop-all.sh
```

### 2.2 备份并更新 `.env`

```bash
cp backend/.env backend/.env.bak.$(date +%Y%m%d)
diff backend/.env backend/.env.example
# 按 .env.example 补充以下新增字段：
#   LLM_DIALOG_TEMPERATURE=0.7
#   LLM_INTENT_TEMPERATURE=0.1
#   PENDING_INTENT_TTL_SEC=60
#   CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://<jetson-IP>:5173
# 删除已废弃字段：
#   LLM_TEMPERATURE=...
```

### 2.3 同步后端依赖（无新增包，但确保一致）

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### 2.4（强烈建议）让 whisper 与 MeloTTS 真正走 GPU

#### 2.4.1 重编 whisper.cpp 带 CUDA

```bash
cd ~/dispenser-ai
./scripts/rebuild-whisper-cuda.sh
```

成功标志：`whisper.cpp/build/bin/whisper-server` 重新生成。

#### 2.4.2 升级到 small 模型（如未下载）

```bash
mkdir -p models/whisper
wget -O models/whisper/ggml-small.bin \
  https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-model-whisper-small.bin
```

#### 2.4.3 安装 Jetson 版 PyTorch（让 MeloTTS 走 GPU）

```bash
./scripts/install-jetson-torch.sh
# 按打印的命令手动 pip install NVIDIA 官方 wheel
# 完成后再次运行此脚本应显示 "torch.cuda.is_available() = True"
```

### 2.5 全部启动

```bash
cd ~/dispenser-ai
./scripts/start-all.sh
./scripts/status.sh
```

---

## 3. 验收清单

逐项检查，全部通过才算升级成功。

### 3.1 服务侧（看日志）

- [ ] `tail logs/whisper-server.log | grep "device 0"` 显示 `device 0: CUDA`（不是 CPU）
- [ ] `tail logs/melotts.log | grep 设备` 显示 `设备: cuda`（不是 cpu）
- [ ] `tail logs/llama-server.log` 包含 `model loaded` 且加载的是 `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`；未出现 `--chat-template` 覆盖警告
- [ ] `grep -i "qwen" logs/llama-server.log` 能看到模型元数据（架构 `qwen3` / `qwen2` 系列）
- [ ] `tail -F logs/backend.log` 持续 5 分钟，**没有** `RemoteProtocolError: Server disconnected without sending a response`
- [ ] 后端启动日志包含 `intent_schema.json 加载成功（Draft-07）`
- [ ] `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok","env":"...","version":"0.2.0"}`

### 3.2 前端基础

- [ ] 浏览器打开 `http://<jetson-ip>:5173`，AI 球可见、可拖动
- [ ] 控制台无 `connectWebSocket` 报错
- [ ] AI 球面板里"AI 后端连接"显示`已连接`

### 3.3 文本对话流程

测试输入 1：`你是谁`

- [ ] AI 气泡回答："我是配药助手，负责协助您完成药品称量、分装、混合等操作。"（或类似中文）
- [ ] **听到 TTS 朗读**该回答（音量正常）
- [ ] 浏览器 DevTools → Network → WS 帧里能看到 `tts_audio` 消息（base64 数据）
- [ ] "确认执行" 按钮处于 disabled 状态，文本显示"等待指令"

测试输入 2：`配100毫克氯化钠到工位1`

- [ ] AI 气泡回答类似"好的，我将称量100毫克氯化钠到工位1，请说'确认执行'或点击按钮"
- [ ] WS 帧含 `pending_intent` 消息，`intent_type=dispense`、`target_mass_mg=100`、`target_vessel` 非空
- [ ] "确认执行" 按钮变为 enabled、绿色、文本"确认执行"
- [ ] 旁边出现"取消"按钮
- [ ] `backend.log` **不应**出现 `LLM 首轮输出无法解析为 JSON` 警告；偶发可接受，连续多次需下调 `LLM_INTENT_TEMPERATURE` 至 0.0

测试输入 3：在以上 pending 状态下，输入 `好的`

- [ ] **不应该** 触发执行
- [ ] AI 应作为普通对话回应，pending 仍在

测试输入 4：点击"确认执行"按钮（或输入 `确认执行`）

- [ ] 收到 `command_sent` 消息
- [ ] mock-qt 日志显示 `收到指令` + `dispense`
- [ ] 2 秒后收到 `command_result` 状态 `completed`
- [ ] AI 气泡和 TTS 提示"已下发指令，正在执行"
- [ ] "确认执行" 按钮变回 disabled

### 3.4 语音对话流程

- [ ] 点击麦克风图标，允许浏览器麦克风权限
- [ ] 说"配五十毫克氯化钠到工位一"
- [ ] 释放后看到 ASR 转写气泡
- [ ] AI 给出反问 / 确认提示，**听到** TTS
- [ ] 说"确认执行"，命令被下发
- [ ] 说"好的"，**不**触发执行

### 3.5 错误路径

- [ ] 当 mock-qt 设备忙时再下发一条 `dispense`：前端 error 区域应显示具体的 `DEVICE_BUSY: ...` 文案，而不是泛泛"命令下发失败"
- [ ] 60 秒后未确认 pending：再次点"确认执行"应提示"没有待确认的任务"
- [ ] 关闭 mock-qt 后下发命令：错误提示应包含具体原因（超时/连接失败），且 backend.log 不刷 traceback 风暴

### 3.6 性能基线（升级前后对比）

| 指标 | 旧（CPU） | 新（CUDA） |
|---|---|---|
| 一句中文（约 3s 音频）ASR 端到端 | 2.5–4s | 300–600ms |
| MeloTTS 一句反问合成 | 1–2s | 200–400ms |
| LLM 单轮 dialog 响应 | ~2s（不变，本来就在 GPU） | ~2s |

---

## 4. 回滚方案

如出现严重问题：

```bash
cd ~/dispenser-ai
./scripts/stop-all.sh
git checkout v0.1.x       # 或之前的标签 / 提交
cp backend/.env.bak.YYYYMMDD backend/.env
./scripts/start-all.sh
```

注意：

- whisper.cpp 重编译后的 `build/` 不影响回滚（可执行文件向后兼容旧启动脚本）
- l4t-pytorch 安装可保留，旧代码也能用 GPU 加速 MeloTTS

---

## 5. 已知不在本次范围

- 前端 `ScriptProcessorNode` → `AudioWorkletNode`（浏览器有 deprecation warning，功能不影响）
- 前端 `systemStore` 高频轮询改 WebSocket push（不影响功能）
- 天平 MT-SICS 驱动（占位文件未实现）
- 视觉 ROI / QRCodeDetector（未实现）

---

## 6. 故障排查速查

| 现象 | 检查 |
|---|---|
| 听不到 TTS | DevTools 看 WS 是否收到 `tts_audio`；后端日志找 `TTS 无返回` |
| 确认按钮始终灰 | 看 WS 是否收过 `pending_intent`，`pendingIntent` store 状态 |
| LLM 输出非 JSON | backend.log 找 `LLM 首轮输出无法解析为 JSON，触发一次 retry`；连续多次需检查 `--jinja` 是否生效 |
| `RemoteProtocolError` 复发 | 检查 mock-qt 是否在跑；检查 `keepalive_expiry=3.0` 是否在 `control_client.py` 里 |
| Schema 校验拒绝合法 intent | 启动日志找 `intent_schema.json 加载失败`；检查 `INTENT_SCHEMA_PATH` 是否相对 backend/ 工作目录解析正确 |
| ASR 慢 | `grep "no GPU found" logs/whisper-server.log`，若命中则需重跑 `rebuild-whisper-cuda.sh` |
