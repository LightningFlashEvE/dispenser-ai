# CLAUDE.md — dispenser-ai 项目级指令

## 导入项目总指南

@AGENTS.md

---

## Serena 工具使用指南

本项目已配置 Serena MCP Server，提供强大的代码导航和重构能力。

### 优先使用 Serena Symbolic Tools 的场景

在以下场景中，**必须优先使用 Serena symbolic tools**，而不是 Claude Code 原生工具：

1. **代码导航与符号查找**
   - 查找类、函数、方法定义：使用 `find_symbol`
   - 查找符号引用：使用 `find_referencing_symbols`
   - 获取文件符号概览：使用 `get_symbols_overview`

2. **代码重构**
   - 重命名符号：使用 `rename_symbol`（自动处理所有引用）
   - 替换函数/方法体：使用 `replace_symbol_body`
   - 安全删除符号：使用 `safe_delete_symbol`（检查引用后删除）

3. **代码插入**
   - 在符号前插入代码：使用 `insert_before_symbol`
   - 在符号后插入代码：使用 `insert_after_symbol`

4. **内容替换**
   - 文件内容替换（支持正则）：使用 `replace_content`

### 可以使用 Claude Code 原生工具的场景

以下场景可以使用 Claude Code 原生工具（Read, Edit, Write, Grep, Glob 等）：

1. **普通文本文件**：README.md, AGENTS.md, 文档文件
2. **配置文件**：.env, .yml, .json, .toml
3. **小范围修改**：单行或几行的简单修改
4. **文件搜索**：按文件名或内容搜索
5. **创建新文件**：新建文件时

### Serena 使用示例

```python
# 查找所有名为 "build_command" 的函数
find_symbol(name_path_pattern="build_command", relative_path="backend/")

# 查找 DraftManager 类的所有引用
find_referencing_symbols(name_path="DraftManager", relative_path="backend/app/services/dialog/draft_manager.py")

# 重命名符号（自动处理所有引用）
rename_symbol(name_path="old_function_name", relative_path="backend/app/api/tasks.py", new_name="new_function_name")

# 替换函数体
replace_symbol_body(name_path="MyClass/my_method", relative_path="backend/app/services/ai/extractor.py", body="新的函数体代码")

# 安全删除符号（检查引用）
safe_delete_symbol(name_path_pattern="unused_function", relative_path="backend/app/utils/helpers.py")
```

### 为什么优先使用 Serena？

1. **语义理解**：Serena 基于 LSP (Language Server Protocol)，理解代码语义，而不仅仅是文本匹配
2. **自动处理引用**：重命名、删除时自动处理所有引用，避免遗漏
3. **类型安全**：基于类型系统，避免误操作
4. **跨文件重构**：自动处理跨文件的符号引用

---

## Claude Code 专属注意事项

### 硬件接口快速提醒

- 不要假设设备路径固定（如 `/dev/ttyUSB0`）
- 涉及电机、泵、机械动作时，先确认安全
- 涉及 GPIO、电压、电流时，确认硬件规格
- 串口通信检查波特率、数据位、停止位、校验位、权限

### 相关文档快速索引

- 项目总览：`AGENTS.md`（已导入）
- 后端指南：`backend/AGENTS.md`
- 前端指南：`frontend/AGENTS.md`
- 架构文档：`docs/architecture.md`
- 协议文档：`docs/command_protocol.md`
- 硬件文档：`docs/hardware_setup.md`
- LLM Prompt 设计：`docs/llm_prompt_design.md`
- 升级手册：`docs/upgrade-v0.2.md`
- 资产管理：`docs/assets.md`
