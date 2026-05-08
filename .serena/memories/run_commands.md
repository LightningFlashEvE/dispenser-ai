# 运行命令

## 开发环境快速启动

### 首次 clone 后初始化
```bash
# 在项目根目录执行
cp .env.example .env
./scripts/download-models.sh
```

### 一键启动全部服务
```bash
# 在项目根目录执行
./scripts/start-all.sh
```
启动后访问：
- 前端（本机）：http://localhost:5173 或 https://localhost:5173
- 前端（局域网麦克风）：必须使用 `https://<jetson-ip>:5173`（HTTP 局域网页面会被浏览器禁止调用麦克风）
- 后端健康检查：http://localhost:8000/health

### 检查服务状态
```bash
# 在项目根目录执行
./scripts/status.sh
```

### 停止所有服务
```bash
# 在项目根目录执行
./scripts/stop-all.sh
```

## 单服务控制

### LLM 服务（llama.cpp server）
```bash
# 在项目根目录执行
./llama_server.sh start|stop|restart|status|logs
```

### ASR 服务（whisper.cpp）
```bash
# 在项目根目录执行
./scripts/start-whisper-server.sh start|stop|restart|status|logs
```

## 后端开发

### 创建虚拟环境（首次）
```bash
# 在 backend/ 目录执行
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows
```

### 安装依赖
```bash
# 在 backend/ 目录执行，激活 venv 后
pip install -r requirements.txt
```

### 启动后端开发服务器
```bash
# 在 backend/ 目录执行，激活 venv 后
python main.py
# 或使用 uvicorn 直接启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 运行后端测试
```bash
# 在 backend/ 目录执行，激活 venv 后
pytest tests/
```

## 前端开发

### 安装依赖（首次）
```bash
# 在 frontend/ 目录执行
npm install
```

### 启动前端开发服务器
```bash
# 在 frontend/ 目录执行
npm run dev
```

### 前端类型检查
```bash
# 在 frontend/ 目录执行
npm run typecheck
```

### 前端代码检查
```bash
# 在 frontend/ 目录执行
npm run lint
```

### 前端构建生产版本
```bash
# 在 frontend/ 目录执行
npm run build
```

### 前端预览生产构建
```bash
# 在 frontend/ 目录执行
npm run preview
```

## MCP Server

### MCP Client 配置示例
在支持 MCP 的工具中（如 Claude Desktop、Cursor、opencode 等），添加以下配置：

```json
{
  "mcpServers": {
    "dispenser-ai": {
      "command": "/home/lightning/dispenser-ai/mcp-server/venv/bin/python",
      "args": ["/home/lightning/dispenser-ai/mcp-server/server.py"]
    }
  }
}
```

## Mock C++ 控制程序

### 启动 mock-qt（开发联调用）
```bash
# 在 mock-qt/ 目录执行
# 具体命令见 mock-qt/AGENTS.md
```

## 常用 Git 命令

```bash
# 查看状态
git status

# 查看差异
git diff

# 查看提交历史
git log --oneline -10

# 创建新分支
git checkout -b feature/your-feature-name

# 提交更改
git add .
git commit -m "feat: your commit message"

# 推送到远程
git push origin your-branch-name
```

## 系统工具命令（Windows）

```powershell
# 列出文件
Get-ChildItem  # 或 ls

# 切换目录
Set-Location path  # 或 cd path

# 查看文件内容
Get-Content file.txt  # 或 cat file.txt

# 搜索文件
Get-ChildItem -Recurse -Filter "*.py"

# 搜索文本内容
Select-String -Path "*.py" -Pattern "pattern"

# 查看进程
Get-Process

# 杀死进程
Stop-Process -Id <pid>
```

## 部署相关

### Jetson 环境设置
```bash
# 在项目根目录执行
./scripts/setup-nx.sh
./scripts/setup-runtime.sh
```

详细部署说明见 `docs/hardware_setup.md` 和 `docs/assets.md`。
