# 部署与硬件注意事项

## 目标部署环境

### 硬件平台
- **主控**：Jetson Orin NX 16GB (Super Mode)
- **操作系统**：Linux (JetPack 6.x)
- **天平**：WKC204C (MT-SICS 协议，RS422-USB)
- **麦克风**：USB 麦克风
- **相机**：工业相机（固定 ROI 检测）
- **触摸屏**：工业触摸屏（局域网访问网页前端）

### 网络要求
- **前端访问**：
  - 本机：http://localhost:5173 或 https://localhost:5173
  - 局域网麦克风：必须使用 `https://<jetson-ip>:5173`（HTTP 局域网页面会被浏览器禁止调用麦克风）
- **后端 API**：http://localhost:8000
- **LLM 服务**：http://localhost:8080 (llama.cpp server)
- **TTS 服务**：http://127.0.0.1:8020 (MeloTTS)
- **C++ 控制程序**：TCP 通信（非 HTTP）

## 环境变量配置

### 后端 `.env` 配置
复制 `backend/.env.example` 为 `backend/.env`，根据实际环境修改：

```bash
# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/dispenser.db

# LLM 服务
LLM_API_BASE=http://localhost:8080/v1
LLM_MODEL_NAME=Qwen3-4B-Instruct-2507-Q4_K_M

# ASR 服务
WHISPER_SERVER_URL=http://localhost:8001

# TTS 服务
TTS_SERVER_URL=http://127.0.0.1:8020

# 天平串口
BALANCE_PORT=/dev/ttyUSB0
BALANCE_BAUDRATE=9600

# C++ 控制程序
CONTROL_TCP_HOST=127.0.0.1
CONTROL_TCP_PORT=9999

# 日志级别
LOG_LEVEL=INFO
```

### 前端环境变量
前端通过 Vite 配置文件 `vite.config.ts` 管理，不使用 `.env` 文件。

## 依赖安装

### 后端依赖
```bash
# 在 backend/ 目录执行
python3 -m venv venv
source venv/bin/activate  # Linux
pip install -r requirements.txt
```

### 前端依赖
```bash
# 在 frontend/ 目录执行
npm install
```

### MCP Server 依赖
```bash
# 在 mcp-server/ 目录执行
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 模型与资产下载

模型、虚拟环境、编译产物、日志和本地数据库不进入 Git 仓库。

### 下载模型
```bash
# 在项目根目录执行
./scripts/download-models.sh
```

下载内容：
- Qwen3-4B-Instruct-2507-Q4_K_M.gguf (LLM 模型，约 2.5GB)
- whisper.cpp 模型（ASR）
- MeloTTS 模型（TTS）

详细说明见 `docs/assets.md`。

## Jetson 部署步骤

### 1. 环境设置
```bash
# 在项目根目录执行
./scripts/setup-nx.sh
./scripts/setup-runtime.sh
```

### 2. 编译本地二进制（可选）
优先在目标机本地编译 llama.cpp 和 whisper.cpp，以获得最佳性能。

```bash
# llama.cpp 编译
cd libs/llama.cpp
mkdir build && cd build
cmake .. -DGGML_CUDA=ON
make -j$(nproc)

# whisper.cpp 编译
cd libs/whisper.cpp
mkdir build && cd build
cmake .. -DGGML_CUDA=ON
make -j$(nproc)
```

### 3. 启动服务
```bash
# 在项目根目录执行
./scripts/start-all.sh
```

### 4. 验证部署
- 访问前端：https://<jetson-ip>:5173
- 检查后端健康：http://<jetson-ip>:8000/health
- 检查服务状态：`./scripts/status.sh`

## 硬件接口注意事项

### 天平串口（RS422-USB）
- **设备路径**：不要假设固定为 `/dev/ttyUSB0`，使用 `dmesg` 或 `ls /dev/tty*` 确认
- **权限**：确保用户在 `dialout` 组，或使用 udev rules 设置权限
- **协议**：MT-SICS 协议，波特率 9600，8N1
- **数据单位**：mg 整数
- **通信方向**：只读，不控制下料

### GPIO/串口/I2C/SPI
- 不要假设硬件连接一定正确
- 不要假设设备路径固定
- 涉及电机、泵、机械动作时，先断开危险负载或低速测试
- 涉及 GPIO、电压、电流时，确认硬件规格
- 涉及串口通信时，检查波特率、数据位、停止位、校验位、权限

### 设备权限排查
```bash
# 查看设备
ls -l /dev/ttyUSB*

# 查看内核日志
dmesg | tail -20

# 查看用户组
groups

# 添加用户到 dialout 组
sudo usermod -aG dialout $USER

# 临时修改权限（不推荐）
sudo chmod 666 /dev/ttyUSB0

# 使用 udev rules（推荐）
# 创建 /etc/udev/rules.d/99-serial.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="xxxx", ATTRS{idProduct}=="xxxx", MODE="0666"
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## 边缘 AI 部署注意事项

### 模型优化
- **模型格式**：使用 GGUF 格式（llama.cpp）或 ONNX/TensorRT（如需进一步优化）
- **量化**：Qwen3-4B 使用 Q4_K_M 量化，约 2.5GB 显存
- **推理引擎**：llama.cpp server，全层 GPU 推理
- **内存占用**：监控 GPU 显存和系统内存，避免 OOM

### 性能监控
- 使用 `psutil` 监控 CPU/GPU/内存
- Dashboard 系统资源采用后台 sampler + cache，不阻塞 event loop
- 日志记录推理延迟和吞吐量

### 离线运行
- 所有模型和依赖必须本地部署
- 不依赖外网服务
- 断网情况下能正常运行

### 自动启动
- 使用 systemd 服务或 supervisor 管理进程
- 设备启动后自动运行
- 异常退出自动重启

## 安全与权限

### 敏感信息保护
- `.env` 文件不进入 Git
- 密钥、token、API Key 使用环境变量
- 日志中不记录敏感信息

### 网络安全
- 前端使用 HTTPS（局域网麦克风需要）
- 后端 API 仅监听本地或局域网
- C++ 控制程序 TCP 通信仅本地或可信网络

### 文件权限
- 数据库文件权限 600 或 640
- 日志文件权限 640
- 配置文件权限 600

## 故障排查

### 常见问题排查顺序
1. **配置问题**：检查 `.env` 文件和环境变量
2. **依赖问题**：检查 Python/Node.js 依赖是否完整安装
3. **路径问题**：检查文件路径、设备路径是否正确
4. **权限问题**：检查文件权限、设备权限、用户组
5. **版本兼容问题**：检查 Python/Node.js/CUDA 版本
6. **代码逻辑问题**：查看日志、调试输出
7. **硬件连接问题**：检查串口、GPIO、相机连接

### 日志位置
- 后端日志：`backend/logs/`
- LLM 服务日志：`llama_server.log`
- ASR 服务日志：`whisper_server.log`
- 系统日志：`journalctl -u <service-name>`

### 调试工具
```bash
# 查看进程
ps aux | grep python
ps aux | grep llama

# 查看端口占用
netstat -tulnp | grep 8000
lsof -i :8000

# 查看 GPU 状态
nvidia-smi

# 查看系统资源
htop
jtop  # Jetson 专用
```

## 升级与回滚

详细升级步骤见 `docs/upgrade-v0.2.md`，包括：
- 破坏性变更说明
- Jetson 升级步骤
- 验收清单
- 回滚方案
