# QHI 拼版处理器 — 插件开发指南

## 目录结构

```
plugins/
├── my_plugin/
│   ├── plugin.json       # 插件元数据（必填）
│   ├── __init__.py       # 或 plugin.py / main.py
│   └── ...
```

## plugin.json 规范

```json
{
    "name": "auto_bleed",
    "version": "1.0.0",
    "author": "QHI Team",
    "description": "自动出血插件：按印刷规范自动添加出血位",
    "entry_point": "auto_bleed.AutoBleedPlugin",
    "hooks": ["on_post_process"],
    "dependencies": [],
    "min_qhi_version": "1.0.0",
    "license": "MIT",
    "homepage": "",
    "config_schema": {}
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 插件唯一标识符，建议使用 snake_case |
| `version` | 是 | 语义化版本号 (SemVer) |
| `author` | 否 | 作者或团队名称 |
| `description` | 否 | 插件功能简述 |
| `entry_point` | 是 | 入口点，格式为 `module.ClassName` |
| `hooks` | 是 | 关注的钩子点列表 |
| `dependencies` | 否 | 依赖的其他插件 name 列表 |
| `min_qhi_version` | 否 | 最低 QHI 版本要求 |
| `license` | 否 | 许可证类型 |
| `homepage` | 否 | 项目主页 |
| `config_schema` | 否 | JSON Schema 格式的配置定义 |

## 钩子点

### 生命周期钩子（5个）

| 钩子 | 调用时机 | 返回值 |
|------|---------|--------|
| `on_load` | 插件加载时 | `bool` |
| `on_unload` | 插件卸载时 | `bool` |
| `on_enable` | 插件启用时 | `bool` |
| `on_disable` | 插件禁用时 | `bool` |
| `on_config_change` | 插件配置变更时 | `bool` |

### 业务钩子（4个）

| 钩子 | 调用时机 | 返回值 |
|------|---------|--------|
| `on_file_arrive` | 文件到达热文件夹时 | `Optional[dict]` — 修改后的 metadata |
| `on_pre_process` | 订单进入处理管线前 | `Optional[dict]` — 修改后的 order |
| `on_post_process` | 订单处理完成后 | `Optional[dict]` — 修改后的 result |
| `on_rule_match` | 规则引擎匹配到规则时 | `bool` — 是否允许规则继续 |

## 快速开始

```python
from core.plugin_interface import PluginBase, PluginContext

class AutoBleedPlugin(PluginBase):
    name = "auto_bleed"
    version = "1.0.0"
    author = "QHI Team"
    description = "自动出血插件"

    def on_load(self, context: PluginContext) -> bool:
        context.logger.info("出血插件已加载")
        return True

    def on_post_process(self, order: dict, result: dict, context: PluginContext) -> dict:
        # 添加 3mm 出血位
        result["bleed_added"] = True
        result["bleed_mm"] = 3.0
        return result
```

## 安全机制

- **沙箱隔离**：高风险钩子（`on_file_arrive`、`on_post_process`）默认在子进程中执行
- **白名单**：可通过 `PluginManager.add_sandbox_whitelist()` 免沙箱
- **超时保护**：沙箱执行超时 30 秒自动终止
- **依赖检查**：加载前验证依赖版本
- **拓扑排序**：按依赖关系确定加载顺序

## 调试

设置环境变量启用详细日志：

```powershell
$env:QHI_PLUGIN_DEBUG = "1"
```
