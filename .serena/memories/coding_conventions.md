# 代码规范与约定

## 通用原则

1. **先读后写**：修改代码前必须先阅读相关文件，理解项目结构
2. **保持风格一致**：遵循项目现有代码风格，不要无意义重构
3. **小步提交**：一次只改相关内容，不要一次性改太多不相关内容
4. **明确说明**：修改前说明准备改哪些文件，修改后总结改了什么
5. **风险提示**：如果有风险，明确指出
6. **不删除文件**：除非明确需要，不要随意删除文件
7. **保护敏感信息**：不要随意改动 `.env`、密钥、token、生产配置；不要把密钥、API Key、Token 写进代码或提交文件

## Python 代码规范（后端）

### 命名约定
- **模块/包名**：小写字母 + 下划线，如 `balance_mtsics.py`
- **类名**：大驼峰（PascalCase），如 `DraftManager`, `AIExtractor`
- **函数/方法名**：小写字母 + 下划线，如 `build_command()`, `send_command()`
- **常量**：全大写 + 下划线，如 `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT`
- **私有成员**：单下划线前缀，如 `_internal_state`

### 类型提示
- 所有函数/方法必须有类型提示（参数和返回值）
- 使用 Python 3.10+ 的新式类型提示（`list[str]` 而非 `List[str]`）
- 复杂类型使用 `typing` 模块，如 `Optional`, `Union`, `Callable`

### 文档字符串
- 所有公开的类、函数、方法必须有 docstring
- 使用 Google 风格的 docstring
- 包含：简短描述、参数说明、返回值说明、异常说明（如有）

示例：
```python
def build_command(intent: dict, catalog_data: dict) -> dict:
    """根据 intent 和 catalog 数据构建 command JSON。

    Args:
        intent: 已确认的 intent JSON，符合 intent_schema.json
        catalog_data: 药品 catalog 查询结果

    Returns:
        符合 command_schema.json 的 command JSON

    Raises:
        ValidationError: 当 intent 或 catalog_data 不符合预期格式时
        RuleEngineError: 当规则引擎校验失败时
    """
    pass
```

### 异常处理
- 使用具体的异常类型，不要捕获裸 `Exception`
- 记录异常日志，包含上下文信息
- 关键路径（如 command 下发）必须有异常处理和回滚机制

### 日志规范
- 使用 Python `logging` 模块
- 日志级别：
  - `DEBUG`：详细调试信息
  - `INFO`：关键流程节点（如任务开始、确认、下发）
  - `WARNING`：可恢复的异常情况
  - `ERROR`：错误但不影响系统运行
  - `CRITICAL`：严重错误，系统无法继续
- 日志格式：包含时间戳、级别、模块名、消息
- 敏感信息（如密钥、token）不得出现在日志中

### 异步编程
- 使用 `async`/`await` 语法
- 不要在 `async def` 中直接调用阻塞函数（如 `time.sleep()`, `subprocess.run()`）
- 阻塞操作必须放入线程池或后台任务
- WebSocket 推送使用 `asyncio.create_task()` 避免阻塞主流程

### Pydantic 模型
- 所有 API 输入输出使用 Pydantic v2 模型
- 使用 `Field` 添加验证规则和描述
- 使用 `model_validator` 进行复杂校验

## TypeScript/Vue 代码规范（前端）

### 命名约定
- **组件名**：大驼峰（PascalCase），如 `TaskCard.vue`, `BalanceChart.vue`
- **文件名**：与组件名一致，或小写 + 连字符，如 `task-card.vue`
- **变量/函数名**：小驼峰（camelCase），如 `taskList`, `handleConfirm()`
- **常量**：全大写 + 下划线，如 `API_BASE_URL`, `WS_RECONNECT_INTERVAL`
- **类型/接口名**：大驼峰（PascalCase），如 `TaskData`, `ApiResponse`

### 类型定义
- 所有变量、函数参数、返回值必须有类型定义
- 使用 TypeScript 的 `interface` 或 `type` 定义复杂类型
- 避免使用 `any`，必要时使用 `unknown` 并进行类型守卫

### 组件规范
- 使用 Vue 3 Composition API（`<script setup>`）
- Props 必须定义类型和默认值
- Emits 必须显式声明
- 使用 `ref` 和 `reactive` 管理响应式状态
- 使用 `computed` 处理派生状态
- 使用 `watch` 监听状态变化

### 样式规范
- 使用 Tailwind CSS 工具类优先
- 组件特定样式使用 `<style scoped>`
- 避免内联样式（除非动态计算）
- 使用 CSS 变量管理主题色

### API 调用
- 使用 axios 进行 HTTP 请求
- 统一的错误处理和 loading 状态管理
- 使用 Pinia store 管理全局状态
- WebSocket 连接必须有重连机制和错误处理

## 目录组织约定

### 后端目录
- `app/api/`：REST 接口，按功能模块分文件（如 `chemicals.py`, `tasks.py`）
- `app/ws/`：WebSocket 接口
- `app/core/`：配置、日志、异常处理等核心功能
- `app/services/`：业务逻辑服务，按领域分目录
- `app/models/`：SQLAlchemy ORM 模型
- `app/schemas/`：Pydantic 输入输出 Schema
- `tests/`：测试文件，目录结构镜像 `app/`

### 前端目录
- `src/components/`：可复用组件
- `src/views/`：页面级组件
- `src/stores/`：Pinia 状态管理
- `src/api/`：API 调用封装
- `src/types/`：TypeScript 类型定义
- `src/utils/`：工具函数
- `src/composables/`：可复用的组合式函数

## Git 提交规范

使用 Conventional Commits 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整（不影响功能）
- `refactor`: 重构（不改变功能）
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具/依赖更新

### Scope 范围（可选）
- `backend`: 后端
- `frontend`: 前端
- `mcp`: MCP Server
- `docs`: 文档
- `scripts`: 脚本

### 示例
```
feat(backend): add chemical catalog lookup service

- Implement fuzzy matching for chemical names
- Support CAS number search
- Add caching for frequent queries

Closes #123
```

## 任务完成检查清单

完成任务后，按以下顺序检查：

1. **代码质量**
   - [ ] 代码符合项目风格
   - [ ] 有必要的类型提示/类型定义
   - [ ] 有必要的文档字符串/注释
   - [ ] 没有硬编码的配置（使用环境变量或配置文件）

2. **功能验证**
   - [ ] 本地测试通过
   - [ ] 相关测试用例已更新/添加
   - [ ] 没有引入新的 linting 错误

3. **文档更新**
   - [ ] 更新相关 AGENTS.md（如有架构变更）
   - [ ] 更新 README.md（如有使用方式变更）
   - [ ] 更新 API 文档（如有接口变更）

4. **安全检查**
   - [ ] 没有泄露敏感信息
   - [ ] 输入验证完整
   - [ ] 错误处理适当

5. **提交**
   - [ ] Git commit message 符合规范
   - [ ] 只提交相关文件
   - [ ] 没有提交 `.env`, 密钥, token 等敏感文件
