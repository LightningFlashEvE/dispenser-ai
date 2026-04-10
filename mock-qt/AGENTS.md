# mock-qt/AGENTS.md — Mock 控制执行层说明

> Mock 服务用于开发阶段模拟真实的 **Linux + C++/Qt 无界面控制服务**，**不部署到生产环境**。

---

## 用途

在真实控制执行层尚未开发完成时，Mock 服务提供相同的 HTTP 接口，使 AI 层可以完整联调：
1. 接收 AI 层下发的 JSON 指令
2. 校验指令格式是否符合 `command_schema.json`
3. 模拟执行过程（可配置延迟和成功/失败概率）
4. 主动回调 AI 层的 `/api/device/callback` 接口

---

## 文件结构

```
mock-qt/
├── AGENTS.md       # 本文件
├── server.py       # Mock HTTP 服务主程序
├── config.json     # 模拟行为配置（延迟、失败率等）
└── requirements.txt
```

---

## server.py 接口规范

### 接收指令

**`POST /api/command`**

请求体：符合 `shared/command_schema.json` 的完整指令 JSON

成功响应（立即返回，不等执行完）：
```json
{
  "command_id": "...",
  "received_at": "2026-04-03T10:30:00.150+08:00",
  "status": "accepted",
  "message": ""
}
```

失败响应（格式错误 / 设备忙）：
```json
{
  "command_id": "...",
  "received_at": "...",
  "status": "rejected",
  "message": "DEVICE_BUSY: 设备正在执行其他指令"
}
```

### 查询设备状态

**`GET /api/status`**

```json
{
  "device_status": "idle",
  "balance_ready": true,
  "current_command_id": null,
  "timestamp": "..."
}
```

---

## config.json 配置说明

```json
{
  "execution_delay_ms": 2000,
  "failure_rate": 0.05,
  "ai_callback_url": "http://localhost:8000/api/device/callback",
  "log_all_commands": true,
  "simulate_actual_mass": true,
  "actual_mass_deviation_pct": 0.3
}
```

| 字段 | 说明 |
|------|------|
| `execution_delay_ms` | 模拟执行耗时（ms），默认 2000ms |
| `failure_rate` | 模拟执行失败概率，0~1，默认 5% |
| `ai_callback_url` | 回调 AI 层的地址 |
| `simulate_actual_mass` | 是否模拟实际称量值（带随机偏差）|
| `actual_mass_deviation_pct` | 实际质量相对目标质量的最大偏差百分比 |

---

## 启动方式

```bash
cd mock-qt
pip install -r requirements.txt
python server.py --port 9000

# 或指定配置文件
python server.py --port 9000 --config config.json
```

---

## 回调行为

接收指令后，Mock 服务：
1. 立即返回 `accepted`
2. 等待 `execution_delay_ms` 毫秒
3. 按 `failure_rate` 概率随机决定成功/失败
4. 生成回调数据（含模拟实际质量）
5. POST 到 `ai_callback_url`

回调数据示例（dispense 成功）：
```json
{
  "command_id": "550e8400-...",
  "status": "completed",
  "completed_at": "2026-04-03T10:30:02.500+08:00",
  "result": {
    "actual_mass_mg": 498,
    "deviation_mg": -2,
    "vessel": "A1"
  },
  "error": null
}
```

回调数据示例（失败）：
```json
{
  "command_id": "550e8400-...",
  "status": "failed",
  "completed_at": "...",
  "result": null,
  "error": {
    "code": "HARDWARE_ERROR",
    "message": "天平通信超时"
  }
}
```

---

## 注意事项

- Mock 服务**不做业务逻辑**，只做格式验证 + 模拟延迟 + 回调
- 收到 `emergency_stop` 时立即取消所有待执行任务，同步返回，不延迟
- 收到 `cancel` 时如果目标指令正在延迟中，取消该延迟并回调 `cancelled` 状态
- **仅用于开发联调，不得用于生产**
