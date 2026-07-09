<!-- ================================================================
## 📋 开发前检查清单 - START HERE!
=================================================================

### 每次修改代码前，先花 10 秒看一遍：

---

## 🔍 Step 1: 先找正确位置

❌ 不要先动手写，先确认目录！

| 功能 | 应该放哪里 | 不要放哪里 |
|---|---|---
选币器逻辑 | `trading_service/pickers/` | `strategies/symbol_picker.py`
外部 API 客户端 | `trading_service/clients/` | 随便放
策略交易逻辑 | `trading_service/strategies/` | 不要混入选币逻辑
数据模型 | 已有 model 就复用 | 不要重新定义同样的类

---

## 🔗 Step 2: 检查接口契约

写任何 `*Picker` / `*Strategy` 前，先自问：

**这个类是给策略框架用的吗？**
→ 如果是，`pick()` 方法必须是 **async**！

**有返回数据结构吗？**
→ 如果是 `SymbolInfo`，不要再发明新字段！先看 `trading_service/pickers/symbol_picker.py` 里已有什么字段！

---

## 🧪 Step 3: 完成后必须验证

| 检查项 | 命令 |
|---|---
类型检查 | `.venv/bin/pyright trading_service/`
单元测试 | `.venv/bin/python -m pytest tests/`
架构契约 | `.venv/bin/python -m pytest tests/architecture/`

---

## 🚩 常见错误速查

| 错误 | 原因 | 正确做法 |
|---|---|---
❌ 把 pick() 写成同步 | 忘记 ISymbolPicker 是 async 框架 | `async def pick(self)`，需要同步IO时套 `run_in_executor`
❌ 在多个地方定义 SymbolInfo | 不知道已有定义 | `from trading_service.pickers import SymbolInfo`
❌ 测试通过但 pyright 报错 | 类型注解有问题 | 严格通过 0 errors 0 warnings
❌ 在 close() 里写逻辑 | 对象生命周期搞错 | 用 `__aenter__/__aexit__` 管理 async 资源

---

## 📚 哪里找上下文参考？

| 查找内容 | 位置 |
|---|---
接口约定 / 类目录 | `PROJECT_CONTEXT.md`  ⭐⭐⭐ 最重要！
领域模型 / 表结构 | `architecture_document/03-domain-model.md`
策略架构 / 扩展方式 | `architecture_document/04-strategy-engine.md`
API 设计 / 返回格式 | `architecture_document/05-api-design.md`
现有例子参考 | `trading_service/pickers/symbol_picker.py`
