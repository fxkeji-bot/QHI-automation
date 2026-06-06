#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
core/help_system.py — 上下文帮助系统

功能:
  - 上下文感知帮助：每个 UI 组件可注册 topic_id，F1 打开对应主题
  - 帮助浏览器：内嵌 QTextBrowser 渲染 Markdown 帮助文档
  - 搜索：关键词搜索帮助主题
  - 索引：帮助主题注册与发现
  - 与工具栏 `?` 按钮联动
"""

import sys, os, re
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QSplitter, QLabel, QWidget,
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence

from models.constants import RESOURCES_DIR


# ── 帮助主题数据类 ───────────────────────────────────────────
@dataclass
class HelpTopic:
    """帮助主题"""
    id: str
    title: str
    content_file: str = ""           # Markdown 文件路径，或内联 content
    inline_content: str = ""
    keywords: List[str] = field(default_factory=list)
    parent_id: str = ""              # 父主题 id（构建树形结构）

    @property
    def content(self) -> str:
        if self.content_file:
            fp = Path(self.content_file)
            if fp.exists():
                return fp.read_text(encoding="utf-8")
        return self.inline_content


# ── 帮助浏览器窗口 ───────────────────────────────────────────
class HelpBrowser(QDialog):
    """帮助浏览器对话框

    使用方式:
        HelpBrowser.show_topic("setup_wizard")
        HelpBrowser.show_search("批量重命名")
    """

    _instance: Optional["HelpBrowser"] = None

    topic_opened = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助")
        self.resize(900, 620)
        self.setMinimumSize(700, 450)

        self._topics: Dict[str, HelpTopic] = {}
        self._context_map: Dict[int, str] = {}  # widget_id → topic_id
        self._current_topic: str = ""
        self._search_history: List[str] = []

        self._init_ui()
        self._register_default_topics()

    @classmethod
    def instance(cls, parent=None) -> "HelpBrowser":
        if cls._instance is None:
            cls._instance = cls(parent)
        elif parent:
            cls._instance.setParent(parent)
        return cls._instance

    # ── 公共接口 ──────────────────────────────────────────────
    def register_topic(self, topic: HelpTopic):
        """注册帮助主题"""
        self._topics[topic.id] = topic
        self._rebuild_tree()

    def register_topics(self, topics: List[HelpTopic]):
        for t in topics:
            self._topics[t.id] = t
        self._rebuild_tree()

    def register_context(self, widget, topic_id: str):
        """为 widget 注册上下文帮助（F1 触发）"""
        if widget:
            widget_id = id(widget)
            self._context_map[widget_id] = topic_id

    def show_topic(self, topic_id: str):
        """打开指定主题"""
        topic = self._topics.get(topic_id)
        if not topic:
            self._browser.setHtml(
                f"<h2>未找到帮助主题</h2><p>主题 ID: {topic_id}</p>"
            )
            return

        self._current_topic = topic_id
        html = self._markdown_to_html(topic.content)
        self._browser.setHtml(html)
        self.topic_opened.emit(topic_id)

        # 高亮树节点
        self._select_tree_node(topic_id)

        self.show()
        self.raise_()
        self.activateWindow()

    def show_search(self, keyword: str):
        """根据关键词搜索并打开"""
        self._search_input.setText(keyword)
        self._perform_search(keyword)
        self.show()
        self.raise_()

    def show_context_help(self, widget):
        """显示 widget 关联的帮助主题"""
        widget_id = id(widget)
        topic_id = self._context_map.get(widget_id)
        if topic_id:
            self.show_topic(topic_id)
        else:
            self._browser.setHtml(
                "<h2>帮助</h2><p>当前界面暂未关联帮助主题。</p>"
            )
            self.show()

    def has_topic(self, topic_id: str) -> bool:
        return topic_id in self._topics

    # ── UI 构建 ───────────────────────────────────────────────
    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部：搜索栏
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索帮助...")
        self._search_input.returnPressed.connect(
            lambda: self._perform_search(self._search_input.text())
        )
        search_row.addWidget(self._search_input)

        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(
            lambda: self._perform_search(self._search_input.text())
        )
        search_row.addWidget(btn_search)

        layout.addLayout(search_row)

        # 中间：树 + 浏览器
        splitter = QSplitter(Qt.Horizontal)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(180)
        self._tree.itemClicked.connect(self._on_tree_clicked)
        splitter.addWidget(self._tree)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setFont(QFont("Microsoft YaHei", 10))
        splitter.addWidget(self._browser)

        splitter.setSizes([220, 660])
        layout.addWidget(splitter, 1)

        # 底部：关闭按钮
        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _on_tree_clicked(self, item: QTreeWidgetItem, _col: int):
        topic_id = item.data(0, Qt.UserRole)
        if topic_id:
            self.show_topic(topic_id)

    def _select_tree_node(self, topic_id: str):
        """在树中选中指定主题节点"""
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == topic_id:
                self._tree.setCurrentItem(item)
                return
            # 递归子节点
            found = self._find_in_children(item, topic_id)
            if found:
                self._tree.setCurrentItem(found)
                return

    def _find_in_children(self, parent: QTreeWidgetItem, topic_id: str):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.UserRole) == topic_id:
                return child
            found = self._find_in_children(child, topic_id)
            if found:
                return found
        return None

    # ── 搜索 ──────────────────────────────────────────────────
    def _perform_search(self, keyword: str):
        keyword = keyword.strip()
        if not keyword:
            return
        self._search_history.append(keyword)

        results = []
        for tid, topic in self._topics.items():
            score = 0
            if keyword.lower() in topic.title.lower():
                score += 10
            if keyword.lower() in topic.content.lower():
                score += 5
            for kw in topic.keywords:
                if keyword.lower() in kw.lower():
                    score += 3
            if score > 0:
                results.append((score, tid, topic.title))

        results.sort(reverse=True, key=lambda x: x[0])

        if results:
            # 打开第一个结果
            self.show_topic(results[0][1])
        else:
            self._browser.setHtml(
                f"<h2>搜索结果</h2><p>未找到与「{keyword}」相关的帮助主题。</p>"
            )

    # ── 树重建 ────────────────────────────────────────────────
    def _rebuild_tree(self):
        self._tree.clear()

        # 构建树：按 parent_id 分组
        root_topics = [t for t in self._topics.values() if not t.parent_id]
        children: Dict[str, List[HelpTopic]] = {}
        for t in self._topics.values():
            if t.parent_id:
                children.setdefault(t.parent_id, []).append(t)

        def add_node(parent_item, topic: HelpTopic):
            item = QTreeWidgetItem(parent_item or self._tree, [topic.title])
            item.setData(0, Qt.UserRole, topic.id)
            for child in children.get(topic.id, []):
                add_node(item, child)
            return item

        for root in sorted(root_topics, key=lambda x: x.title):
            add_node(None, root)

        self._tree.expandAll()

    # ── 默认主题注册 ──────────────────────────────────────────
    def _register_default_topics(self):
        self.register_topics([
            HelpTopic(
                id="overview",
                title="系统概述",
                inline_content="""# QHI 快印智能处理系统

## 产品定位
专为数码快印行业设计的智能文件处理工具，支持 PDF 文件的自动化处理、拼版、报价、重命名。

## 核心功能
- **文件处理**：预检、规则匹配、拼版、后处理、输出归档
- **智能报价**：基于纸张/工艺/数量联动的实时报价计算
- **批量重命名**：5 套预设命名模板 + 自定义模板
- **插件扩展**：支持自定义处理钩子
- **多语言**：中文/英文切换

## 快速上手
请查看"快速上手向导"帮助主题。
""",
                keywords=["概述", "介绍", "简介", "功能", "about"],
            ),
            HelpTopic(
                id="setup_wizard",
                title="快速上手向导",
                parent_id="overview",
                inline_content="""# 快速上手向导

## 启动向导
首次启动时会自动弹出设置向导，您也可以从「帮助 → 使用向导」手动打开。

## 三步配置

### 第一步：选择业务模式
- **快印店模式**：适合门店散单，预置常见纸张和工艺
- **合版印刷模式**：适合批量拼版，预置大度/正度纸张
- **书刊印刷模式**：适合书刊装订，预置胶装/精装工艺

### 第二步：预置配置确认
向导会根据所选模式自动填充默认纸张、工艺、设备和规则。

### 第三步：设置监控目录
选择需要自动监控的文件目录，新文件到达时自动触发处理。
""",
                keywords=["向导", "设置", "初始化", "配置", "wizard", "setup"],
            ),
            HelpTopic(
                id="file_processing",
                title="文件处理",
                inline_content="""# 文件处理

## 拖拽处理
将 PDF 文件拖入拖拽区域，点击「即时处理」按钮即可。

## 处理阶段
1. **预检**：检查文件完整性、格式、页数
2. **规则匹配**：自动匹配适用的处理规则
3. **拼版处理**：执行 PDF 拼版操作
4. **后处理**：添加裁切标记、出血检查
5. **输出归档**：输出到指定目录

## 快捷键
- `Ctrl+P`：即时处理
- `Ctrl+R`：批量重命名
- `Ctrl+Q`：智能报价
- `Ctrl+I`：查看文件信息
""",
                keywords=["处理", "拼版", "PDF", "预检", "输出", "process"],
                parent_id="overview",
            ),
            HelpTopic(
                id="batch_rename",
                title="批量重命名",
                parent_id="file_processing",
                inline_content="""# 批量重命名

## 可用模板
1. **快印模板**：{jobno}_{name}_{pages}p_{date}
2. **书刊模板**：{name}_{part}_{binding_type}_{date}
3. **合版模板**：{paper}_{copies}份_{pages}p_{customer}
4. **默认模板**：{name}_{pages}p_{machine}
5. **简易序号**：{seq:04d}_{name}

## 可用变量
{seq} {name} {pages} {date} {customer} {machine} {jobno} {paper} {binding_type} {copies} {part} {version}

## 冲突处理
重名时自动添加 _1、_2 后缀。
""",
                keywords=["重命名", "命名", "模板", "批量", "rename"],
            ),
            HelpTopic(
                id="quoting",
                title="智能报价",
                parent_id="file_processing",
                inline_content="""# 智能报价

## 计算模型
总价 = 纸张成本 + Click费用 + 工艺成本 + 人工费(10%) + 利润(25%)

## 联动计算
- 纸张类型 → 克重 → 单价
- 尺寸 → 出血 → 有效面积
- 页数 → 印张数 → Click总量
- 份数 → 总印量

## 报价组成
| 项目 | 说明 |
|------|------|
| 纸张成本 | 印张数 × 纸张单价 |
| Click费用 | 彩色/黑白 × 单张Click单价 |
| 工艺成本 | 覆膜/烫金/UV/模切 |
| 人工费 | 纸张成本 × 10% |
| 利润 | 小计 × 25% |
""",
                keywords=["报价", "价格", "计算", "成本", "quote", "price"],
            ),
            HelpTopic(
                id="plugins",
                title="插件体系",
                parent_id="overview",
                inline_content="""# 插件体系

## 插件目录
插件放置在 `PLUGIN_DIR`（环境变量 `QHI_PLUGIN_DIR` 或默认 `D:\\deepseek_plugins`）。

## 插件结构
```
my_plugin/
├── manifest.json    # 插件声明
└── my_plugin.py     # 插件代码
```

## manifest.json 格式
```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entry_module": "my_plugin",
  "entry_class": "MyPlugin",
  "author": "Author",
  "description": "...",
  "depends_on": [],
  "tags": ["impose", "output"]
}
```

## 可用钩子
- `on_preflight` — 预检阶段
- `on_rule_match` — 规则匹配后
- `on_impose` — 拼版前
- `on_postprocess` — 后处理
- `on_output` — 输出后
- `on_startup` — 应用启动
- `on_shutdown` — 应用关闭
- `on_new_file` — 新文件加入

## 生命周期
发现 → 加载 → 启用 → 运行 → 禁用 → 卸载
""",
                keywords=["插件", "plugin", "扩展", "钩子", "hook"],
            ),
            HelpTopic(
                id="api",
                title="HTTP API",
                parent_id="overview",
                inline_content="""# HTTP API

## 启动服务
在「系统设置」中开启 API 服务，默认端口 8899。

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/health | 健康检查 |
| GET | /api/v1/status | 管线状态 |
| GET | /api/v1/orders | 订单列表 |
| POST | /api/v1/orders | 创建订单 |
| GET | /api/v1/orders/{id} | 订单详情 |
| POST | /api/v1/process | 提交处理任务 |
| GET | /api/v1/plugins | 插件列表 |
| POST | /api/v1/plugins/{id}/enable | 启用插件 |
| POST | /api/v1/plugins/{id}/disable | 禁用插件 |

## 示例
```bash
curl http://127.0.0.1:8899/api/v1/health
```
""",
                keywords=["API", "接口", "HTTP", "REST", "curl"],
            ),
            HelpTopic(
                id="pipeline",
                title="处理管线",
                parent_id="file_processing",
                inline_content="""# 处理管线

## 架构
- **五阶段管线**：预检 → 规则匹配 → 拼版 → 后处理 → 输出
- **多线程并发**：QThreadPool 支持 2-4 个文件并行处理
- **暂停/恢复**：随时暂停和恢复处理
- **进度追踪**：逐文件、逐阶段进度信号

## 配置
```python
pipeline = ProcessingPipeline(db, metadata_mgr, rule_engine)
pipeline.progress_updated.connect(on_progress)
pipeline.start(files, output_dir, max_workers=2)
pipeline.pause()
pipeline.resume()
pipeline.get_status()  # {total, done, failed, in_progress}
```
""",
                keywords=["管线", "pipeline", "并发", "线程"],
            ),
            HelpTopic(
                id="i18n",
                title="多语言支持",
                parent_id="overview",
                inline_content="""# 多语言支持

## 支持的语言
- 中文（简体）
- English

## 使用方式
在代码中使用 `i18n.tr()` 包裹所有用户可见字符串：

```python
from utils.i18n import I18nEngine
i18n = I18nEngine.instance()
label.setText(i18n.tr("共 {count} 个文件", count=10))
```

## 切换语言
```python
i18n.set_locale("en_US")
```

## 翻译文件
翻译文件位于 `resources/locales/{locale}/LC_MESSAGES/qhi_processor.json`。

## 添加新语言
1. 复制 `zh_CN` 目录为新语言目录
2. 编辑 JSON 翻译文件
3. 在 `SUPPORTED_LOCALES` 中添加语言码
""",
                keywords=["语言", "国际化", "i18n", "翻译", "locale", "language"],
            ),
            HelpTopic(
                id="shortcuts",
                title="快捷键参考",
                inline_content="""# 快捷键参考

## 文件操作
| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 打开文件 |
| `Ctrl+N` | 新建订单 |
| `Ctrl+S` | 保存 |
| `Ctrl+Shift+S` | 另存为 |

## 处理操作
| 快捷键 | 功能 |
|--------|------|
| `Ctrl+P` | 即时处理 |
| `Ctrl+R` | 批量重命名 |
| `Ctrl+Q` | 智能报价 |
| `Ctrl+I` | 查看文件信息 |

## 帮助
| 快捷键 | 功能 |
|--------|------|
| `F1` | 上下文帮助 |
| `Ctrl+Shift+F1` | 关于 |
""",
                keywords=["快捷键", "热键", "shortcut", "键盘"],
            ),
            HelpTopic(
                id="troubleshooting",
                title="常见问题",
                inline_content="""# 常见问题

## 文件无法处理
1. 确认文件为 PDF 格式
2. 检查文件是否损坏（用 Adobe Reader 打开测试）
3. 查看日志 `qhi_processor.log`

## 处理速度慢
1. 增大 `max_workers` 线程数（建议 2-4）
2. 检查 PDF 页数和图片分辨率

## 插件加载失败
1. 确认 `manifest.json` 格式正确
2. 确认 `entry_module` 和 `entry_class` 可导入
3. 检查依赖的 `depends_on` 插件是否已加载

## API 无法访问
1. 确认 API 服务已在设置中开启
2. 检查端口 8899 是否被防火墙拦截
3. 使用 `http://127.0.0.1:8899/api/v1/health` 测试
""",
                keywords=["问题", "故障", "错误", "FAQ", "troubleshoot", "debug"],
            ),
        ])


# ── 便捷函数 ─────────────────────────────────────────────────
def show_help(topic_id: str = "overview", parent=None):
    """快捷显示帮助主题"""
    browser = HelpBrowser.instance(parent)
    browser.show_topic(topic_id)


def show_help_search(keyword: str, parent=None):
    """快捷搜索帮助"""
    browser = HelpBrowser.instance(parent)
    browser.show_search(keyword)


def register_widget_help(widget, topic_id: str):
    """为 widget 注册 F1 帮助"""
    browser = HelpBrowser.instance()
    browser.register_context(widget, topic_id)


# ── Markdown → HTML 简易转换 ────────────────────────────────
def _markdown_to_html(md_text: str) -> str:
    """将 Markdown 文本转换为 HTML 用于 QTextBrowser 渲染"""
    # 默认渲染完整的 Markdown，QTextBrowser 富文本模式不支持完整 Markdown，
    # 这里做基础转换
    lines = md_text.split("\n")
    html_lines = []
    in_code_block = False
    in_table = False
    code_lines = []

    for line in lines:
        stripped = line.rstrip()

        # 代码块
        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append(
                    f"<pre><code>{''.join(code_lines)}</code></pre>"
                )
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            # 转义 HTML
            escaped = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            code_lines.append(escaped + "\n")
            continue

        # 表格（简易检测）
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                html_lines.append('<table border="1" cellpadding="4" cellspacing="0">')
                in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(c.startswith("---") for c in cells):
                continue  # 跳过分隔行
            is_header = in_table and len(html_lines) - html_lines.index(
                [x for x in html_lines if x.startswith("<table")][-1]
            ) <= 1
            tag = "th" if is_header else "td"
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False

        # 标题
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("### "):
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("- "):
            html_lines.append(f"<li>{_inline_md(stripped[2:])}</li>")
        elif re.match(r"^\d+\.\s", stripped):
            html_lines.append(f"<li>{_inline_md(stripped[stripped.index('.')+2:])}</li>")
        elif stripped == "":
            html_lines.append("<br>")
        else:
            # 行内加粗
            html_lines.append(f"<p>{_inline_md(stripped)}</p>")

    if in_table:
        html_lines.append("</table>")

    css = """
    <style>
    body { font-family: 'Microsoft YaHei', sans-serif; font-size: 14px; }
    h1 { color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 8px; }
    h2 { color: #16213e; border-bottom: 1px solid #0f3460; padding-bottom: 4px; }
    h3 { color: #0f3460; }
    table { border-collapse: collapse; width: 100%; margin: 10px 0; }
    th { background: #e94560; color: white; }
    td, th { border: 1px solid #ccc; padding: 6px 10px; }
    pre { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px; }
    code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
    pre code { background: transparent; padding: 0; }
    li { margin: 2px 0; }
    </style>
    """
    return css + "\n".join(html_lines)


def _inline_md(text: str) -> str:
    """行内 Markdown 转换"""
    # **加粗**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # `代码`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text
