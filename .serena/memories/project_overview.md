# 项目概览

## 项目名称
dispenser-ai — 龙门机械臂粉末自动配料系统

## 项目定位
基于 **Jetson Orin NX 16GB 启用 Super Mode** 的全本地离线智能配料系统，面向龙门机械臂粉末称量、抓取、投料与混合场景。

## 核心目标
构建"**AI理解 + 规则校验 + 控制执行**"分层架构，在本地完成语音识别、意图理解、语音合成、视觉检测、结构化任务生成、日志记录和网页服务，不依赖外网服务。

## 核心特性
- **全本地离线**：ASR、LLM、TTS、视觉均在 Jetson 本地运行，不依赖云端
- **语音交互**：USB 麦克风 + whisper.cpp 语音识别 + MeloTTS 语音播报
- **AI 字段提取**：Qwen3-4B 大模型通过 llama.cpp 部署，只负责理解自然语言并提取 draft patch
- **规则引擎校验**：所有任务经过规则引擎和状态机检查后才可执行
- **MCP Server 工具集**：将系统能力封装为标准工具，AI 可按需调用
- **工业触摸屏**：本地网页前端，支持触摸屏操作和局域网访问
- **实时天平推送**：MT-SICS 协议读取天平数据，WebSocket 高频推送前端显示
- **资源监控不阻塞**：Dashboard 系统资源由后端后台 sampler + cache 提供，HTTP 只读缓存
- **视觉工位检测**：固定 ROI + 二维码识别，自动识别工位药品和位置

## 技术栈

### 后端 (Python)
- **Web 框架**：FastAPI + Uvicorn
- **数据校验**：Pydantic v2 + pydantic-settings
- **数据库**：SQLAlchemy 2.0 + aiosqlite (SQLite 异步驱动)
- **HTTP 客户端**：httpx + websockets
- **串口通信**：pyserial (天平 MT-SICS 协议)
- **JSON Schema 校验**：jsonschema
- **视觉**：opencv-python-headless
- **音频处理**：sounddevice + numpy
- **系统监控**：psutil
- **中文处理**：opencc-python-reimplemented

### AI 模型
- **ASR**：whisper.cpp (本地离线语音识别)
- **LLM**：llama.cpp server + Qwen3-4B-Instruct-2507-Q4_K_M (约 2.5GB 显存，全层 GPU 推理)
- **TTS**：MeloTTS (独立服务运行于 http://127.0.0.1:8020)

### 前端 (Vue 3 + TypeScript)
- **框架**：Vue 3.4 + TypeScript 5.6
- **构建工具**：Vite 5.4
- **状态管理**：Pinia 2.2
- **路由**：Vue Router 4.3
- **UI 组件**：Element Plus 2.9 + shadcn-vue (Radix Vue)
- **样式**：Tailwind CSS 3.4 + tailwindcss-animate
- **图表**：ECharts 5.5
- **HTTP 客户端**：axios 1.7
- **工具库**：class-variance-authority, clsx, tailwind-merge, lucide-vue-next

### 其他
- **MCP Server**：Python stdio 模式，封装系统能力为 AI 工具
- **后级控制程序**：C++ (mock-qt 用于开发联调)
- **通信协议**：TCP + JSON (后端与 C++ 控制程序)

## 部署环境
- **目标平台**：Jetson Orin NX 16GB (Super Mode)
- **操作系统**：Linux (JetPack 6.x)
- **开发环境**：Windows (WSL 可选)
