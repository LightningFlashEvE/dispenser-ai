# 系统架构

## 分层架构图

```
[ 本地网页前端 ] ←→ HTTP/REST + WebSocket ←→ [ FastAPI 后端 ]
                                               ↓ localhost HTTP/JSON
                                              [ 后端规则引擎 + 状态机 ]
                                               ↓ TCP + JSON
                                [ 后级控制程序（C++ / mock-qt）]
                                               ↓ CAN/RS485/串口/TCP
                                 [ 机械臂 / 称重模块 / 现场 IO ]

[ USB 麦克风 ] → [ VAD + whisper.cpp ] → [ ASR guard ] → [ Intent Router + AIExtractor patch ] → [ Draft / Validator / Catalog ] → [ 规则引擎 + 状态机 ]
[ 工业相机 ]   → [ 固定 ROI + QRCodeDetector ] → [ 工位/药品/坐标结果 ]
[ MeloTTS ]    → [ 语音反馈 ]

[ MCP Client ] → [ MCP Server (stdio) ] → HTTP 调用 → [ FastAPI 后端 ]
```

## 目录结构

```
dispenser-ai/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/                # REST 接口（配方/药品/日志管理、C++ 回调接收）
│   │   ├── ws/                 # WebSocket（语音交互、天平实时数据推送）
│   │   ├── core/               # 配置、日志、异常处理
│   │   ├── services/
│   │   │   ├── ai/             # ASR(whisper.cpp) / LLM(llama.cpp) / TTS(MeloTTS) / VAD
│   │   │   ├── vision/         # ROI检测 / QRCodeDetector / 坐标换算
│   │   │   ├── dialog/         # 意图解析、槽位管理、规则引擎、状态机
│   │   │   ├── device/
│   │   │   │   ├── balance_mtsics.py   # 天平 MT-SICS 驱动（RS422-USB）
│   │   │   │   └── control_client.py   # C++ 控制程序 TCP 客户端
│   │   │   └── inventory/      # 药品库、配方库、工位状态管理
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   └── schemas/            # Pydantic v2 输入输出 Schema
│   ├── tests/
│   ├── main.py                 # 入口
│   └── requirements.txt
├── frontend/                   # Vue 3 + TypeScript 前端
│   ├── src/
│   └── package.json
├── mcp-server/                 # MCP Server（stdio 模式）
├── mock-qt/                    # 模拟 C++ 后级控制程序（开发联调用）
├── shared/
│   ├── intent_schema.json      # 语义层 Schema（规则引擎校验用）
│   └── command_schema.json     # 执行层 Schema（C++ 控制程序接口契约）
├── scripts/                    # 启动/停止/部署脚本
├── config/                     # 配置文件
├── docs/                       # 架构/协议/硬件文档
├── .serena/                    # Serena 配置与 memories
└── .env.example                # 环境变量模板
```

## 核心执行链路（Draft Workflow）

```
用户输入（语音 / 文本 / 前端表单）
  ↓
Intent Router（分流：普通对话、查询、开始/更新/取消/确认任务）
  ↓
AIExtractor patch（AI 只提取本轮字段 patch，不生成 command，不写 chemical_id）
  ↓
DraftManager merge（后端合并 session 级 draft，记录审计事件）
  ↓
Validator（后端判断 missing_slots / ready_for_review）
  ↓
ASR guard（保留 raw_text / normalized_text / confidence，低置信关键字段先确认）
  ↓
Chemical Catalog lookup（chemical_id 只能来自 catalog lookup 或用户候选选择）
  ↓
前端结构化确认卡片（任务字段、catalog 匹配、ASR 提示、确认/修改/取消）
  ↓
用户确认 = self_approved（本机操作员确认即授权）
  ↓
后端规则校验（库存、单位、容器、设备状态、配方步骤等硬门槛）
  ↓
build_command（生成 shared/command_schema.json）
  ↓
send_command（TCP/HTTP 适配层下发最终 command JSON）
  ↓
C++ 控制层（只执行后端签发的 command JSON）
  ↓
执行反馈 → 页面与语音反馈

天平数据流（并行常驻，仅展示）：
天平 WKC204C → RS422-USB → 后端 MT-SICS 驱动 → mg 整数 → WebSocket → 前端实时展示
```

## 通信与数据通道边界

| 数据类型 | 主通道 | 说明 |
|----------|--------|------|
| 称重实时曲线 | WebSocket | 高频推送，仅用于显示，不作为安全闭环依据 |
| Dashboard 系统资源 | HTTP | 读取后台 sampler cache，不得阻塞 event loop |
| 任务确认 / 执行进度 | 后端状态机 + WebSocket 通知 | 规则校验通过后生成 command_id 下发 |
| 历史任务 / 日志 / 审计 | HTTP 分页 | WebSocket 只推新增/变更通知 |
| 库存 / 配方 / 药品库 | HTTP 查询和修改 | 修改后可 WebSocket 通知前端刷新 |
| 急停 / 安全联锁 | C++ / 硬件优先 | 后端只显示和记录状态 |

## Schema 文件说明

- `shared/intent_schema.json`：语义层，由后端基于已确认 draft/proposal 生成；AI 只能提供 patch，不能直接生成最终 intent
- `shared/command_schema.json`：执行层，字段来自数据库、catalog lookup、规则引擎和状态机，所有字段必须合法且通过校验

## 关键边界约束

1. AIExtractor 只输出字段 patch，不输出 `complete` / `ready_for_review` 的可信判断
2. `chemical_id` 只能来自 catalog lookup 或用户候选选择，AI 不能写入
3. AI 不能写 `slot_id` / `motor_id` / `pump_id` / `valve_id` / `station_id` 等控制层字段
4. 任何 `async def` API 中不得直接执行阻塞采样、`subprocess.run()`、长时间 `psutil` 调用或同步 I/O
5. 后端天平驱动只负责读数，不直接控制下料电机（下料由 C++ 控制）
6. 重复确认不能重复生成 proposal 或重复下发 command（幂等）
