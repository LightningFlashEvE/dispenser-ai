# 硬件选型与部署指南

---

## 0. 开发环境与部署目标

### 目标部署平台规格

| 项目 | 规格 |
|------|------|
| 主控板 | 英伟达 **Jetson Orin NX Super 开发板** |
| 内存 | 16GB（CPU+GPU 共享） |
| 存储 | 512GB M.2 2280 NVMe SSD |
| 系统 | JetPack 6.x（Ubuntu 22.04 aarch64） |
| 模式 | **Super Mode** 启用 |

### 当前开发环境

| 项目 | 规格 |
|------|------|
| OS | Windows(x86_64) |
| 用途 | 核心业务逻辑开发（规则引擎、状态机、REST API、WebSocket、前端） |
| Ollama | Windows 桌面版 |
| mock-qt | FastAPI 模拟 C++ 控制程序 |

### 跨平台开发须知

| 差异项 | Windows 开发 | Jetson 部署 |
|--------|-------------|-------------|
| 串口设备路径 | `COM3` | `/dev/ttyUSB0` |
| whisper.cpp | subprocess 调用 Windows 预编译可执行文件 | 需 git clone + cmake 编译 ARM64 版本 |
| MeloTTS | Windows 支持差，跳过 | Linux 部署 |
| 音频索引 | Windows WASAPI 设备索引 | Linux ALSA 设备索引，含义不同 |
| 控制通信 | HTTP → mock-qt (localhost:9000) | TCP → 真实 C++ 控制程序 |
| pyserial 设备 | 无硬件，跳过 | RS422-USB 工业隔离转换器 |
| 内存限制 | 通常 32GB+ | 16GB 共享（CPU+GPU 各用），实际可用 ~12-14GB |

**内存预算（16GB 环境）：**

| 组件 | 内存占用 |
|------|---------|
| OS + UI | ~2GB |
| Ollama + 7B 模型 | ~4-6GB |
| whisper.cpp | ~1-2GB |
| MeloTTS | ~500MB-1GB |
| FastAPI + 数据库 | ~500MB |
| **总计** | **~8-12GB** |

### `config.py` 跨平台设计原则

```python
# 所有路径使用 pathlib.Path
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent

# 串口路径按平台默认
import platform
balance_serial_port: str = "/dev/ttyUSB0" if platform.system() == "Linux" else "COM3"
```

---

## 1. 核心硬件清单

| 序号 | 设备名称 | 规格参数 | 用途 | 预算(元) |
|------|----------|----------|------|----------|
| 1 | Jetson Orin NX 16GB | 16GB 模块 + 载板，启用 Super Mode | 系统主控、AI 计算平台 | 待按采购渠道确认 |
| 2 | NVMe SSD | 512GB M.2 2280 | 系统、模型、日志存储 | 329 |
| 3 | 工业触摸屏 | 10.1 英寸 HDMI + USB | 用户交互界面 | 380 |
| 4 | 工业 USB 相机 | 1080P 全局快门 | 视觉检测、二维码识别 | 399 |
| 5 | USB 麦克风 | 工业降噪型 | 语音输入 | 60 |
| 6 | 小音箱 | 5V/12V 工业级 | 语音输出 | 40 |
| 7 | 精密天平 | 梅特勒 WKC204C，量程 220 g，分辨率 0.1 mg，RS422 接口，MT-SICS 协议，配静电处理器、防风罩及料盘框架 | 称重闭环核心 | 待询价 |
| 8 | RS422 转 USB 转换器 | 工业级隔离型，用于 Jetson USB 接口与天平 RS422 对接 | 天平通信接口 | 约 80 |
| 9 | CAN 通信模块 | 工业级 CAN 收发器 | 与控制器通信 | 49 |
| 10 | 串口模块 | TTL / RS485 转换器 | 备用通信 | 29 |
| 11 | 相机支架 | 可调高度桌面支架 | 相机固定 | 59 |
| 12 | 标定板 | 棋盘格标定板 | 相机标定 | 29 |
| 13 | 电源适配器 | 工业级稳压电源 | 系统供电 | 129 |
| 14 | 散热器 | 铜管+双风扇或等效 | 长稳运行散热 | 89 |
| 15 | 线材配件 | 电源、USB、HDMI 等 | 系统连接 | 50 |

---

## 2. 主控与部署建议

### 2.1 Jetson 平台说明

- 正式文档统一表述为：**Jetson Orin NX 16GB 启用 Super Mode**
- 采购与量产时需重点确认：
  - 模块版本
  - 载板兼容性
  - 电源设计
  - 散热方案

### 2.2 天平说明（梅特勒 WKC204C）

| 参数 | 值 |
|------|-----|
| 型号 | Mettler Toledo WKC204C |
| 量程 | 220 g |
| 分辨率 / 可读性 | 0.1 mg |
| 通信接口 | RS232 / RS422（M12 接头） |
| 通信协议 | **MT-SICS**（ASCII 串口命令集） |
| 最高更新率 | 92 Hz |
| 供电 | 12–24 V DC |
| 附件 | 静电处理器、防风罩、料盘框架 |

**重要说明：**
- 天平使用 **MT-SICS 协议**，不是 Modbus，不能直接套用 Modbus 驱动
- RS422 引脚在接线手册中与 RS485 共用命名，但电气协议是 RS422 全双工点对点
- Jetson 侧通过 **RS422-USB 工业隔离转换器** 接入，推荐使用带光耦隔离的型号防干扰
- 波特率、数据位、奇偶校验需按梅特勒配置手册与后级控制程序侧保持一致

**常用 MT-SICS 命令参考：**

| 命令 | 说明 | 响应示例 |
|------|------|---------|
| `S\r\n` | 查询稳定重量 | `S S 1.2345 g` |
| `SI\r\n` | 查询即时重量（不等稳定）| `S D 1.2300 g` |
| `Z\r\n` | 归零（去皮）| `ZA` |
| `ZI\r\n` | 立即归零 | `ZA` |
| `@\r\n` | 软复位 | `I4 A "Reset"` |

> 后级控制程序中的天平驱动需解析 MT-SICS 响应格式，提取数值后转换为 **mg 整数**（乘以 1000 后取整）再上报 AI 层。

### 2.3 软件基础平台

- JetPack 6.2 或 6.x 生产可用版本
- 根据是否启用 Super Mode、驱动兼容性和量产稳定性选择具体小版本

---

## 3. 算力与进程分配

### GPU
- 本地 LLM 推理独占优先

### CPU
- whisper.cpp
- MeloTTS
- OpenCV 视觉检测与二维码识别
- FastAPI 服务
- 本地网页交互
- 控制适配层
- 日志与数据管理

### 运行策略
- LLM 与视觉服务建议分进程运行
- 语音模块按需启动，降低资源占用
- 启用守护进程和异常自动拉起
- 日志滚动归档，限制磁盘增长

---

## 4. 软件环境部署

### 4.1 基础依赖

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    nodejs npm sqlite3 \
    git curl wget ffmpeg v4l-utils alsa-utils \
    libopencv-dev pkg-config
```

### 4.2 音频设备确认

```bash
arecord -l
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

### 4.3 摄像头设备确认

```bash
v4l2-ctl --list-devices
python3 - <<'PY'
import cv2
cap = cv2.VideoCapture(0)
print('camera_opened=', cap.isOpened())
cap.release()
PY
```

### 4.4 服务部署步骤

1. 组装硬件并确认供电与散热
2. 安装 JetPack 与基础依赖
3. 部署视觉、ASR、LLM、TTS、后端与前端服务
4. 配置开机自启与守护进程
5. 完成相机标定、坐标标定、通信调试
6. 完成规则引擎、状态机与控制白名单配置
7. 进行联调与长稳测试

---

## 5. 模型与运行组件

| 模块 | 运行位置 | 说明 |
|------|----------|------|
| whisper.cpp | CPU | 本地离线 ASR |
| 本地 LLM | GPU | 任务级 JSON 生成 |
| MeloTTS | CPU | 本地中文 TTS |
| OpenCV ROI 检测 | CPU | 固定工位有无检测 |
| QRCodeDetector | CPU | 二维码识别、坐标与角度提取 |
| 规则引擎 / 状态机 | CPU | 控制适配层核心 |

---

## 6. 通信方式

### Jetson ↔ 后级控制程序
- `localhost HTTP/REST + JSON`

### 后级控制程序 ↔ 设备执行层
- 电机驱动器：`RS485 + Modbus RTU`
- 天平（WKC204C）：`RS422 + MT-SICS ASCII 串口协议`（**不使用 Modbus**）
- 其他现场设备：`CAN / 串口 / TCP`（按实际设备确认）

---

## 7. 音频与视觉参数建议

### 音频参数

| 参数 | 建议值 | 说明 |
|------|--------|------|
| 采样率 | 16000 Hz | whisper.cpp 适配 |
| 位深 | 16-bit PCM | 标准格式 |
| 声道 | 单声道（Mono） | 降低处理负担 |
| VAD 静音阈值 | 800~1200ms | 判断说话结束 |

### 视觉参数

| 参数 | 建议值 | 说明 |
|------|--------|------|
| 分辨率 | 1280×720 或 1920×1080 | 固定工位识别 |
| 帧率 | 15~30 FPS | 满足检测需求 |
| ROI | 固定矩形区域 | 每个工位单独配置 |
| 标定 | 棋盘格标定 | 坐标映射 |

---

## 8. 运维建议

- 每日巡检温度、风扇、存储和日志
- 每周检查识别样本与误报情况
- 每月清理缓存与归档日志
- 每季度评估模型版本是否需要替换
- 变更模型或规则前必须做回归测试

---

## 9. 故障排查

| 现象 | 排查步骤 |
|------|---------|
| 麦克风无输入 | `arecord -l` 确认设备存在；检查 `AUDIO_DEVICE_INDEX` |
| 摄像头打不开 | `v4l2-ctl --list-devices`；检查 `CAMERA_DEVICE_INDEX` |
| ASR 速度慢 | 检查 whisper.cpp 模型大小；确认 CPU 占用 |
| LLM 推理慢 | 检查 Jetson 电源模式、Super Mode、散热和 GPU 占用 |
| 二维码识别不稳 | 检查 ROI、补光、对焦和标定结果 |
| 控制下发失败 | 检查后级控制程序地址、CAN/RS485/串口配置和日志 |
| 长稳异常 | 检查守护进程、日志滚动和供电稳定性 |
