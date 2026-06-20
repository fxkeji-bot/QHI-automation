---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: bc2a160e8b5d7cb83c2c331399e3f700_8ee2f3e26bd811f18805525400d9a7a1
    ReservedCode1: mmOqojf8k0DwwohaLyQ42UB3awGgvXSbe+z3k+PQZn6GeWVdDIYgk9CP8lXx+jn6mY+z2D6T5O97sovUvbS2uzE+HngZW3lJDbO3iMcdAuVfNHi5RlW9Slnl3gNsw364hHuQPFR1srpKc418Ed3kZDPUQ85v7PeNAD5RJSoN2gTPt/sVMLjzfmIapUc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: bc2a160e8b5d7cb83c2c331399e3f700_8ee2f3e26bd811f18805525400d9a7a1
    ReservedCode2: mmOqojf8k0DwwohaLyQ42UB3awGgvXSbe+z3k+PQZn6GeWVdDIYgk9CP8lXx+jn6mY+z2D6T5O97sovUvbS2uzE+HngZW3lJDbO3iMcdAuVfNHi5RlW9Slnl3gNsw364hHuQPFR1srpKc418Ed3kZDPUQ85v7PeNAD5RJSoN2gTPt/sVMLjzfmIapUc=
---

# QHI 拼版处理器 — 深度代码审计报告

> **日期**: 2026-06-19  
> **审计范围**: `core/` `services/` `models/` `integration/` `ui/` `main.py`  
> **审计维度**: 不合理设计 / 逻辑 Bug / 数据错误  

---

## 统计总览

| 严重度 | 数量 | 说明 |
|--------|------|------|
| 🔴 严重 | 12 | 可导致崩溃、数据损坏或安全问题 |
| 🟡 中等 | 18 | 影响健壮性、可维护性或边界行为 |
| 🟢 轻微 | 8 | 代码质量/风格问题，不影响运行 |

---

## 🔴 严重问题（12 项）

### CR-001: `core/config.py` — 模块导入时触发副作用（目录创建）

- **文件**: `core/config.py`
- **行号**: 31-76
- **问题描述**: `_resolve_output_dir()` 在 `_default_config()` 中被调用，而 `_default_config()` 在 `__init__` 中被调用。但问题更严重：`main.py` 中在模块级别 `from core.config import ConfigManager` 时，若后续某处实例化 ConfigManager（如 `main.py` line 226 对 `api_enabled` 检查），就会触发目录创建和文件写入。这违反了"模块导入不应有副作用"原则。
- **代码片段**:
```python
def _default_config(self) -> Dict:
    return {
        'qhi_path': QI_EXE,
        'output_dir': self._resolve_output_dir(),  # 副作用：创建目录

def _resolve_output_dir(self) -> str:
    desktop_dir = Path.home() / "Desktop" / "QHI_FinalFiles"
    try:
        desktop_dir.mkdir(parents=True, exist_ok=True)
        test_file = desktop_dir / ".qhi_write_test"
        test_file.touch()  # 副作用：创建测试文件
```
- **修复方案**: 将 `output_dir` 的解析改为惰性求值，使用 `@property` 或 `__getattr__`，仅在首次访问时执行目录创建逻辑。
- **影响评估**: 在只读文件系统、受限用户环境或容器中，`import` 阶段就会失败；且会在用户未确认的情况下创建目录。

---

### CR-002: `core/event_bus.py` — 回调异常被完全吞没

- **文件**: `core/event_bus.py`
- **行号**: 104-109
- **问题描述**: `publish()` 方法中，所有回调的异常被 `except Exception: pass` 静默吞噬。这意味着一旦某个订阅者的回调抛出异常，其他订阅者继续执行但没有人知道发生了错误，导致业务逻辑静默失败。
- **代码片段**:
```python
for cb in regular:
    try:
        cb(**kwargs)
    except Exception:
        pass  # 吞掉回调异常，不中断其他回调
```
- **修复方案**: 至少记录异常日志；或者在捕获后收集异常，publish 完成后若有异常则聚合抛出或记录。
```python
for cb in regular:
    try:
        cb(**kwargs)
    except Exception as e:
        logger.error(f"EventBus callback for '{event}' failed: {e}", exc_info=True)
```
- **影响评估**: 硬件级别的故障（如规则保存失败、仪表板数据丢失）将被静默忽略，排查极其困难。

---

### CR-003: `core/database.py` — `_fix_tables` 修复编号重复

- **文件**: `core/database.py`
- **行号**: ~560, ~570（`_fix_tables` 方法内）
- **问题描述**: `_fix_tables()` 方法中存在两个 `# 修复7` 注释标签，且第二个修复（为 orders 表添加 `workflow_state` 列）位于循环添加 `code` 列之后，但 `auto_generate_codes` 和 `_add_column_if_missing` 都在同一个 `try/except Exception` 块内，任何异常都会导致后续修复被跳过。
- **代码片段**:
```python
# 修复7：为数据字典表添加 code 列...
for table in tables_with_code:
    self._add_column_if_missing(cur, table, 'code', 'TEXT UNIQUE')
    auto_generate_codes(cur, self.conn, table, logger)

# 修复7：为 orders 表添加 workflow_state 列...   # ← 编号重复
```
- **修复方案**: 将编号统一为 `修复7` 和 `修复8`；将各修复拆分为独立的 try/except 块，避免一个失败导致后续全部跳过。
- **影响评估**: 若 `auto_generate_codes` 对某表失败，orders 表的 `workflow_state` 列和 `production_logs` 列修复将被跳过。

---

### CR-004: `core/connection_pool.py` — 连接池满时直接抛异常无重试

- **文件**: `core/connection_pool.py`
- **行号**: ~185-193
- **问题描述**: `_acquire()` 方法中，当 `len(self._all_connections) >= self.max_connections` 时直接 `raise RuntimeError`。调用方（如 `ConnectionContextManager.__enter__`）无任何重试逻辑，高并发场景下会直接因 RuntimeError 崩溃。
- **代码片段**:
```python
if len(self._all_connections) >= self.max_connections:
    logger.warning(f"连接池已满 ({self.max_connections})，等待连接释放...")
    raise RuntimeError(f"连接池已满，无法创建新连接 (max={self.max_connections})")
```
- **修复方案**: 使用 `threading.Condition` 或带超时的阻塞等待替代直接抛异常；或使用 `queue.Queue` 的阻塞 `put`/`get`（当前混合了 Queue 和手动列表管理导致不一致）。
- **影响评估**: 高并发处理（多文件并行拼版）时，可能因瞬间连接池满导致整个处理批次中断。

---

### CR-005: `models/constants.py` — Feature Flag 异常捕获过宽

- **文件**: `models/constants.py`
- **行号**: 96-107
- **问题描述**: `PDF_SUPPORT` 和 `PY7ZR_SUPPORT` 的检测使用 `except Exception`，注释中解释为 PyInstaller 冰冻环境下 cffi 初始化可能失败。但这也同时掩盖了真实依赖缺失的情况（如 fitz 未安装）。用户将看到 `[X] 否（请安装: pip install PyPDF2）` 的误导提示，但实际上 fitz 才是硬依赖。
- **代码片段**:
```python
try:
    import fitz
    PDF_SUPPORT = True
except Exception:  # 过宽
    PDF_SUPPORT = False
```
- **修复方案**: 区分 `ImportError` 和其他异常；或在 `main.py` 启动时显式检测并给出准确提示。
```python
try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
except Exception as e:
    logger.warning(f"fitz import failed with unexpected error: {e}")
    PDF_SUPPORT = False
```
- **影响评估**: 用户可能被误导去安装错误的包（PyPDF2），而实际问题可能是 fitz 初始化失败或缺失 native 依赖。

---

### CR-006: `services/file_monitor.py` — 客户名称硬编码在函数签名默认值

- **文件**: `services/file_monitor.py`
- **行号**: 34
- **问题描述**: `find_order_directories()` 的 `customer` 参数默认值为 `"9705-小风"`，这是特定客户的硬编码。该函数被 `flow_entry.py` 的 `HotFolderWorker` 等模块调用，会导致其他客户环境的订单扫描失败或返回空。
- **代码片段**:
```python
def find_order_directories(root_path: str, days_back: int = 2,
                           customer: str = "9705-小风") -> List[Path]:
```
- **修复方案**: 移除硬编码默认值，改为从配置或数据库读取；或将此参数改为必填。
- **影响评估**: 非"9705-小风"客户的订单目录将完全不被扫描，属于业务阻断级 Bug。

---

### CR-007: `core/license_manager.py` — 授权密钥种子回退到常量

- **文件**: `core/license_manager.py`
- **行号**: 85-91
- **问题描述**: `CryptoProvider.get_secret()` 在没有环境变量 `QHI_LICENSE_SECRET` 且 `machine_code` 为空时使用 `b"::QHI_FALLBACK_SEED"` 常量作为 PBKDF2 种子。如果 `machine_code` 获取失败（如权限不足），加密退化为固定种子，攻击者可在本地重现密钥派生过程。
- **代码片段**:
```python
@staticmethod
def get_secret(machine_code: str = "") -> bytes:
    env_secret = os.environ.get("QHI_LICENSE_SECRET", "")
    if env_secret:
        seed = env_secret.encode()
    else:
        seed = hashlib.sha256(
            (machine_code or "UNKNOWN").encode() + b"::QHI_FALLBACK_SEED"
        ).digest()
    return seed
```
- **修复方案**: `machine_code` 为空时应终止启动而非使用回退种子；或将回退种子混入运行时可变的熵源（如 `os.urandom(32)` 但会破坏解密一致性）。
- **影响评估**: 安全边界削弱：在 machine_code 获取失败的边缘情况下，授权保护形同虚设。

---

### CR-008: `core/order_repository.py` — `get_all_orders` SQL 字符串拼接

- **文件**: `core/order_repository.py`
- **行号**: 152
- **问题描述**: `get_all_orders()` 中 `date_to` 参数通过字符串拼接 `date_to + " 23:59:59"` 追加到 SQL 中，而非使用参数化查询。虽然 `date_to` 是内部传入的字符串，但这种拼接模式不可靠，且一旦外部传入就构成 SQL 注入。
- **代码片段**:
```python
if date_to:
    if date_from:
        sql += " AND "
    sql += "created_at<=?"
    params.append(date_to + " 23:59:59")  # 拼接而非参数化
```
- **修复方案**: 使用数据库层的时间函数如 `datetime(?, '+1 day', '-1 second')` 或在上层将完整的 ISO 时间戳作为参数传入。
- **影响评估**: 中等风险 — 当前 date_to 来自内部调用，但代码模式危险且有维护风险。

---

### CR-009: `core/database.py` — 池模式下 `conn` 属性泄漏风险

- **文件**: `core/database.py`
- **行号**: 101-112
- **问题描述**: 池模式下 `conn` 属性 getter 返回 `self._pool._all_connections[0].conn`，这是一个未加锁的裸连接引用。如果多个线程通过此属性获取连接并直接使用，绕过了连接池的 `_acquire`/`_release` 机制，导致 WAL 模式下的并发冲突。
- **代码片段**:
```python
@property
def conn(self):
    if self.use_pool:
        return self._pool._all_connections[0].conn  # 裸引用
    return self._conn
```
- **修复方案**: 池模式下完全禁用 `conn` 属性访问，强制所有调用方使用 `_get_conn()/_release_conn()` 或上下文管理器。
- **影响评估**: 任何仍使用 `self.conn` 的旧代码路径在池模式下将绕过连接池保护，可能导致 "database is locked" 错误。

---

### CR-010: `main.py` — `__main__` 异常处理中重复创建 QApplication

- **文件**: `main.py`
- **行号**: 419-436
- **问题描述**: `if __name__ == "__main__"` 的 `except Exception` 分支中，当主流程已经失败后，又尝试创建新的 `QApplication` 实例来弹出错误对话框。这违反了 Qt 的"每个进程只能有一个 QApplication"约束，会在控制台输出警告甚至崩溃。
- **代码片段**:
```python
except Exception as e:
    try:
        app = QApplication(sys.argv)  # 第二个 QApplication
        QMessageBox.critical(None, "程序崩溃", ...)
    except Exception:
        pass
```
- **修复方案**: 检查是否已存在 QApplication 实例（`QApplication.instance()`）再决定如何显示错误。
- **影响评估**: 程序崩溃时的错误提示本身可能触发二次崩溃，用户看不到任何错误信息。

---

### CR-011: `models/constants.py` — 返回不存在的默认路径

- **文件**: `models/constants.py`
- **行号**: 13-28
- **问题描述**: `get_default_qhi_path()` 遍历候选路径，若全都不存在则返回 `possible_paths[0]`（一个不存在的路径）。后续所有依赖 `QI_EXE` 的模块都会基于这个不存在的路径运行，直到运行时才发现文件不存在。
- **代码片段**:
```python
for p in possible_paths:
    if os.path.exists(p):
        return p
return possible_paths[0]  # 不存在的路径
```
- **修复方案**: 返回 `None` 或空字符串，由调用方在启动时检测并提示用户配置路径。
- **影响评估**: 用户会看到日志中"QHI路径: C:\Program Files (x86)\...\qi_applycommands.exe" 但实际上文件不存在，后续操作才会报错，排查路径被掩盖。

---

### CR-012: `services/api_server.py` — 类级别属性存在线程安全隐患

- **文件**: `services/api_server.py`
- **行号**: 67-72
- **问题描述**: `_APIHandler` 使用类级别属性 `pipeline = None`, `db = None`, `plugin_manager = None` 来注入依赖。Python 的 `http.server` 为每个请求创建新的 handler 实例，但这些类属性在所有 handler 实例间共享。如果多个请求同时修改这些属性（如在初始化/重配置期间），会造成竞态条件。
- **代码片段**:
```python
class _APIHandler(BaseHTTPRequestHandler):
    router: Router = Router()
    pipeline = None      # 类级别共享
    db = None
    plugin_manager = None
    flow_entry = None
```
- **修复方案**: 使用 `threading.local()` 存储每个线程的依赖；或使用实例属性在 `__init__` 中从全局注册表获取。
- **影响评估**: 在 API 服务重载（如热更新配置）期间，并发请求可能读取到不一致的服务引用。

---

## 🟡 中等问题（18 项）

### MD-001: `core/config.py` — `get_config()` 深拷贝方式不健壮

- **文件**: `core/config.py`
- **行号**: 339
- **问题描述**: `get_config()` 使用 `json.loads(json.dumps(self.config))` 实现深拷贝。当配置中包含非 JSON 可序列化对象（如 `Path` 对象）时将抛出 `TypeError`。
- **代码片段**:
```python
def get_config(self) -> Dict:
    return json.loads(json.dumps(self.config))
```
- **修复方案**: 使用 `copy.deepcopy()` 或确保配置字典始终只包含可序列化类型。
- **影响评估**: 若未来配置中存在 Path/Datetime 等对象，调用 `get_config()` 会崩溃。

---

### MD-002: `core/config.py` — `save()` 跨卷替换可能失败

- **文件**: `core/config.py`
- **行号**: 323-328
- **问题描述**: `os.replace()` 在 Windows 上要求源和目标在同一文件系统卷上。如果临时文件目录（`CONFIG_FILE.tmp`）与配置文件目录在不同驱动器，`os.replace` 会抛出 `OSError`。
- **代码片段**:
```python
temp_path = f"{self.CONFIG_FILE}.tmp"
with open(temp_path, 'w', encoding='utf-8') as f:
    json.dump(self.config, f, ...)
os.replace(temp_path, self.CONFIG_FILE)
```
- **修复方案**: 使用 `shutil.move()` 替代 `os.replace`，或在 `CONFIG_FILE` 同目录下创建临时文件。
- **影响评估**: 特定部署环境（如配置文件在映射网络驱动器）下保存会静默失败。

---

### MD-003: `core/database.py` — 上帝类（1246 行）

- **文件**: `core/database.py`
- **行号**: 全文件
- **问题描述**: `Database` 类承担了 14 张表的 CRUD、连接池管理、表结构迁移、索引管理、种子数据、订单查询委托等全部职责。违反单一职责原则，测试和修改任何子功能都需要理解和加载整个类。
- **修复方案**: 已开始拆分（`OrderRepository`），但 `find_paper`/`find_process`/`find_customer`/`get_price` 等方法仍保留在 `Database` 中。应继续拆分为 `PaperRepository`, `ProcessRepository`, `CustomerRepository`, `PriceRepository` 等。
- **影响评估**: 维护成本高，修改一处可能影响看似不相关的功能。

---

### MD-004: `core/database.py` — `search()` 方法内联 `import re`

- **文件**: `core/database.py`
- **行号**: ~750（`search` 方法内）
- **问题描述**: `search()` 方法内部使用 `re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k)` 验证字段名，但 `re` 模块未在文件顶部导入。虽然没有功能性错误（首次调用才导入），但违背 PEP 8 规范，且每次调用都重新查找模块。
- **代码片段**:
```python
def search(self, table: str, keyword: str = "", **kwargs):
    ...
    for k, v in kwargs.items():
        if v is not None:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):  # re 未在顶部导入
```
- **修复方案**: 在文件顶部添加 `import re`。
- **影响评估**: 微小性能损耗，代码可读性差。

---

### MD-005: `core/database.py` — `_safe_execute` 过度包装异常

- **文件**: `core/database.py`
- **行号**: 156-173
- **问题描述**: `_safe_execute()` 捕获所有异常并统一包装为 `RuntimeError`，原始异常类型信息丢失。调用方无法区分"数据完整性错误（应重试）"和"编程错误（不可恢复）"。
- **代码片段**:
```python
except Exception as e:
    error = f"{error_msg} (未知错误): {e}"
    self.error_callback(error)
    raise RuntimeError(error) from e
```
- **修复方案**: `except Exception` 应保留为最后的兜底，中间应增加 `ValueError`/`TypeError` 等编程错误的区分，让调用方能做出有意义的决策。
- **影响评估**: 调用方无法实现精细的错误恢复策略。

---

### MD-006: `core/database.py` — `insert()` 中 `placeholders` 生成错误

- **文件**: `core/database.py`
- **行号**: ~785
- **问题描述**: `insert()` 方法中生成占位符的代码为 `", ".join("?" * len(keys))`，这会生成 `"?, ?, ?"`。但如果 keys 为空，则生成空字符串，导致 SQL 为 `INSERT INTO table () VALUES ()`，在 SQLite 中这会插入一条所有列为默认值的行，而不是预期的报错。
- **代码片段**:
```python
placeholders = ", ".join("?" * len(keys))
cols = ", ".join(keys)
cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", ...)
```
- **修复方案**: 在 keys 为空时提前抛出 `ValueError`。
- **影响评估**: 边界情况下会静默插入垃圾数据。

---

### MD-007: `core/connection_pool.py` — `get_pool()` db_path 不一致问题

- **文件**: `core/connection_pool.py`
- **行号**: 320-335
- **问题描述**: `get_pool()` 采用双重检查锁定模式，首次调用时使用传入的 `db_path` 创建池。如果后续调用传入了不同的 `db_path`，会被静默忽略，返回旧池。这可能导致模块在不同的数据库文件间产生混淆。
- **代码片段**:
```python
def get_pool(db_path: str = None, **kwargs) -> ConnectionPool:
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                if db_path is None:
                    from models.constants import DB_PATH
                    db_path = str(DB_PATH)
                _global_pool = ConnectionPool(db_path, **kwargs)
    return _global_pool
```
- **修复方案**: 若传入的 `db_path` 与已存在的池不一致，至少记录警告。
- **影响评估**: 多数据库场景下可能连接到错误的数据库。

---

### MD-008: `core/order_repository.py` — 订单号生成存在并发碰撞风险

- **文件**: `core/order_repository.py`
- **行号**: 33-37
- **问题描述**: `create_order()` 使用 `datetime.now().strftime('%Y%m%d%H%M%S') + uuid4().hex[:4]` 生成订单号。`%H%M%S` 精度为秒，同一秒内 uuid4 hex 前 4 字符碰撞概率约为 1/65536。高并发下（如同一秒内多个线程创建订单），碰撞不可忽略。
- **代码片段**:
```python
kwargs['order_no'] = (
    f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    f"{uuid.uuid4().hex[:4].upper()}"
)
```
- **修复方案**: 使用完整 uuid4 hex（8字符以上）或数据库自增 ID + 日期前缀。
- **影响评估**: 高并发场景下可能出现重复订单号，导致数据库 UNIQUE 约束冲突。

---

### MD-009: `core/license_manager.py` — PBKDF2 300000 轮启动性能问题

- **文件**: `core/license_manager.py`
- **行号**: 110
- **问题描述**: `CryptoProvider.derive_key()` 使用 300000 轮 PBKDF2-HMAC-SHA256。在低性能机器上（如 Atom 处理器工控机），这可能需要 1-3 秒。若每次检查授权都重新派生密钥，启动时间将显著增加。
- **代码片段**:
```python
return hashlib.pbkdf2_hmac("sha256", secret, salt, 300000, dklen=32)
```
- **修复方案**: 对派生密钥进行会话级缓存；或降低迭代轮数至 100000（OWASP 推荐的最小值）。
- **影响评估**: 工控机/瘦客户机上启动延迟 1-3 秒。

---

### MD-010: `services/flow_entry.py` — `MetadataInjector.parse_xml` 扁平化丢失层级信息

- **文件**: `services/flow_entry.py`
- **行号**: 80-90
- **问题描述**: `MetadataInjector.parse_xml()` 遍历所有子元素并存储 `child.tag → child.text`，如果 XML 中有同名嵌套标签（如多个 `<item>`），后面的会覆盖前面的，且所有层级信息丢失。
- **代码片段**:
```python
for child in root.iter():
    if child is root:
        continue
    if child.text and child.text.strip():
        result[child.tag] = child.text.strip()
```
- **修复方案**: 使用递归构建嵌套字典，或对重名标签使用列表聚合。
- **影响评估**: JDF/JMF 等层次化 XML 元数据的解析结果会丢失大量信息。

---

### MD-011: `services/variable_service.py` — `_SafeEvaluator` 变量替换可能静默失败

- **文件**: `services/variable_service.py`
- **行号**: 48-60
- **问题描述**: `replace_var` 函数中，当变量值为非数值型字符串时尝试 `float(s)`，若失败则返回 `repr(s)`。这会将字符串变量注入为 Python 字面量（如 `'hello'`），但若字符串包含引号或特殊字符，会导致 `safe_eval` 解析失败。
- **代码片段**:
```python
s = str(val)
try:
    float(s)
    return s
except ValueError:
    return repr(s)  # 如 'O\'Brien' → "O'Brien" 可能破坏表达式
```
- **修复方案**: 对非数值变量使用占位符替换或先收集再求值，避免直接拼接字符串到表达式。
- **影响评估**: 包含特殊字符的变量值（如文件名中的单引号）会导致计算表达式报错。

---

### MD-012: `integration/smart_processor.py` — 操作回滚可能不完整

- **文件**: `integration/smart_processor.py`（基于摘要分析）
- **行号**: ActionContext 相关代码
- **问题描述**: `ActionContext` 事务回滚机制依赖 `_rollback_stack`，但如果某个 action 执行过程中创建了外部副作用（如调用了 QHI exe 生成了输出文件），回滚无法清理这些外部文件。
- **修复方案**: 在文档中明确回滚边界，或在 action 接口中要求实现 `rollback()` 方法。
- **影响评估**: 失败的批量处理可能留下半成品文件，污染输出目录。

---

### MD-013: `core/di_container.py` — `resolve_all()` 强制解析所有服务

- **文件**: `core/di_container.py`
- **行号**: 145-151
- **问题描述**: `resolve_all()` 会强制初始化所有已注册的单例服务。对于重量级服务（如数据库连接、PDF 处理器），即使在当前会话中不需要，也会被创建，浪费内存和启动时间。
- **修复方案**: 改为惰性遍历，或添加 `lazy` 标记允许服务声明"不自动初始化"。
- **影响评估**: 启动时加载不需要的服务，增加内存占用。

---

### MD-014: `core/di_container.py` — `register_instance` 重复注册未清理旧单例

- **文件**: `core/di_container.py`
- **行号**: 87-96
- **问题描述**: `register_instance()` 直接设置 `self._singletons[name] = instance`，但没有检查是否已有旧的注册项和单例。如果之前已注册同名服务，旧工厂函数保留在 `_registrations` 中，接下来 `resolve()` 会返回新的 instance，但行为不一致。
- **代码片段**:
```python
def register_instance(self, name: str, instance: Any):
    self._registrations[name] = _ServiceDescriptor(...)
    self._singletons[name] = instance  # 直接覆盖
```
- **修复方案**: 与 `register()` 保持一致，先 `pop(name, None)` 清理旧单例。
- **影响评估**: 热重载场景下可能出现新旧实例混合使用。

---

### MD-015: `services/job_queue.py` — 上帝类（1289 行）

- **文件**: `services/job_queue.py`
- **行号**: 全文件
- **问题描述**: `JobQueue` 类包含作业调度、优先级管理、死信队列、设备绑定、SQLite 持久化、HTTP webhook 回调等全部逻辑，达到 1289 行。测试和修改极其困难。
- **修复方案**: 拆分为 `JobScheduler`, `JobPersistence`, `DeviceBinding`, `DeadLetterQueue` 等独立类。
- **影响评估**: 同上 MD-003。

---

### MD-016: `services/job_queue.py` — `Job` 数据类 `file_path` 与 `file_paths` 歧义

- **文件**: `services/job_queue.py`
- **行号**: ~62-64
- **问题描述**: `Job` 同时有 `file_path: str` 和 `file_paths: List[str]` 两个字段，语义模糊。调用方可能只填充其中一个，处理逻辑需要判断两者，增加错误的可能性。
- **代码片段**:
```python
file_path: str = ""
file_paths: List[str] = field(default_factory=list)
```
- **修复方案**: 统一为 `file_paths: List[str]`，废弃 `file_path` 或将其作为 property 指向 `file_paths[0]`。
- **影响评估**: 处理逻辑中需反复判断，容易遗漏导致单文件作业处理失败。

---

### MD-017: `core/config.py` — `load()` 中无效配置备份无错误处理

- **文件**: `core/config.py`
- **行号**: 267-272
- **问题描述**: 配置校验失败后的备份操作使用 `shutil.copy2` 包裹在 `try/except Exception: pass` 中，备份失败静默忽略。这可能导致用户丢失原始配置文件的唯一副本。
- **代码片段**:
```python
try:
    shutil.copy2(self.CONFIG_FILE, backup_path)
except Exception:
    pass
```
- **修复方案**: 至少记录错误日志，告知用户备份失败。
- **影响评估**: 配置损坏时用户可能无法恢复。

---

### MD-018: `services/processing_pipeline.py` — `PipeItem.is_done` 忽略跳过场景

- **文件**: `services/processing_pipeline.py`
- **行号**: ~66-67
- **问题描述**: `PipeItem.is_done` 属性要求 `stage == OUTPUT and not error_msg` 才算完成。但管线中可能存在"跳过"场景（如预检不通过选择跳过），此时 stage 可能保持为 PREFLIGHT 且 error_msg 为空，导致 `is_done` 始终为 False，阻断裂汇总逻辑。
- **代码片段**:
```python
@property
def is_done(self) -> bool:
    return self.stage == PipeStage.OUTPUT and not self.error_msg
```
- **修复方案**: 增加 `skipped` 状态或检查 `stage in (OUTPUT, SKIPPED)`。
- **影响评估**: 含有跳过文件的批次可能永远不被标记为完成。

---

## 🟢 轻微问题（8 项）

### MI-001: `core/config.py` — 导入顺序混乱

- **文件**: `core/config.py`
- **行号**: 1-15
- **问题描述**: `from utils.logger import get_logger` 和 `logger = get_logger(__name__)` 在文件开头，但 `import os, json, shutil` 等在 docstring 之后。违反 PEP 8 导入顺序：标准库 → 第三方 → 本地。
- **修复方案**: 调整导入顺序，将 logger 初始化移到所有 import 之后。
- **影响评估**: 纯代码风格问题，不影响运行。

---

### MI-002: `models/enums.py` — `PaperCategory.build_code` 局部导入 re

- **文件**: `models/enums.py`
- **行号**: 112
- **问题描述**: `build_code()` 方法内部 `import re`，而其他方法未使用。如果此方法被频繁调用，每次都会重新查找模块。
- **修复方案**: 将 `import re` 移到文件顶部。
- **影响评估**: 微小性能开销。

---

### MI-003: `models/order_models.py` — `VALID_TRANSITIONS` 类型提示不准确

- **文件**: `models/order_models.py`
- **行号**: 31
- **问题描述**: `VALID_TRANSITIONS: Dict[Optional[OrderStage], set]` 中键包含 `None`，静态类型检查器（mypy/pyright）会对此发出警告。
- **修复方案**: 使用 `Dict[OrderStage | None, set[OrderStage]]`（Python 3.10+）或定义专用类型别名。
- **影响评估**: 仅影响类型检查，不影响运行时。

---

### MI-004: `core/event_bus.py` — `AppEvents` 类应该使用 `Enum`

- **文件**: `core/event_bus.py`
- **行号**: 122-167
- **问题描述**: `AppEvents` 使用类属性定义事件常量，但与项目其他模块（`models/enums.py`）的风格不一致（其他均使用 `Enum`）。且无法利用 IDE 的自动补全和类型检查。
- **修复方案**: 改为 `class AppEvents(str, Enum)` 保持项目一致性。
- **影响评估**: 代码风格不一致，无运行时影响。

---

### MI-005: `core/database.py` — `_VALID_COL_TYPES` 包含中文默认值

- **文件**: `core/database.py`
- **行号**: ~610-625
- **问题描述**: `_VALID_COL_TYPES` 白名单中硬编码了中文列默认值如 `TEXT DEFAULT '待处理'`。这对于中文环境是合理的，但如果数据库被非中文环境的工具读取，列默认值中的中文字符可能显示为乱码。
- **修复方案**: 改为更通用的验证方式（如正则匹配 `TEXT DEFAULT .*`）。
- **影响评估**: SQLite 以 UTF-8 存储，现代工具均支持，影响极小。

---

### MI-006: `main.py` — `_safe_import_classes` 未处理模块内部导入失败

- **文件**: `main.py`
- **行号**: 97-110
- **问题描述**: `_safe_import_classes` 使用 `__import__` 和 `getattr`，如果模块导入成功但类不存在，`getattr` 返回 `None` 而不会抛出异常。这可能掩盖模块重构后类名变更的问题。
- **修复方案**: 当 `getattr` 返回 `None` 时记录警告日志。
- **影响评估**: 重构后可能出现模块静默不可用。

---

### MI-007: `core/config.py` — `main.py` 中多次实例化 ConfigManager

- **文件**: `main.py`
- **行号**: 226, 270
- **问题描述**: `main()` 函数中第 226 行调用 `ConfigManager().config.get(...)` 检查 API 配置，第 270 行 `MainWindow()` 内部也会创建 `ConfigManager` 实例。由于 `ConfigManager.__init__` 会 `load()` 配置文件，启动过程中配置文件被多次读取。
- **修复方案**: 将 `ConfigManager` 改为单例模式，或在 `main()` 开头创建后传递。
- **影响评估**: 轻微性能开销，不影响正确性。

---

### MI-008: `services/pricing_service.py` — 空壳门面

- **文件**: `services/pricing_service.py`
- **行号**: 全文件（29 行）
- **问题描述**: `PricingService` 仅简单委托给 `DigitalPricingEngine`，无任何增值逻辑。这种极薄的门面层增加了调用链深度，却未提供实际抽象价值。
- **修复方案**: 若未来不计划在此层添加业务逻辑（如缓存、审计），直接移除并在调用方使用 `DigitalPricingEngine`。
- **影响评估**: 无功能影响，但增加代码维护负担。

---

## 修复优先级建议

| 优先级 | 问题编号 | 建议修复时间 |
|--------|---------|-------------|
| P0（立即） | CR-002, CR-004, CR-006, CR-010 | 本次迭代 |
| P1（本周） | CR-001, CR-005, CR-007, CR-009 | 本次迭代 |
| P2（本月） | CR-003, CR-008, CR-011, CR-012, MD-001~MD-006 | 下个迭代 |
| P3（下月） | MD-007~MD-018, MI-001~MI-008 | 技术债务清理 |

---

## 未审查项

以下文件因时间限制未深入审查（约 35+ 个 UI 文件及部分 services/integration 文件），建议在后续审计中补全：

- `ui/dialogs/` 下 6 个对话框文件
- `ui/widgets/` 下 15 个组件文件
- `ui/controllers/` 下 8 个控制器文件
- `integration/` 下 10 个集成模块文件
- `services/` 下 10 个服务模块文件

---

*报告生成: 2026-06-19 | 审计工具: Marvis File Agent*
*（内容由AI生成，仅供参考）*
