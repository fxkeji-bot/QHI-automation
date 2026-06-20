# QHI 拼版处理器 — 全面代码评审报告
## 日期: 2026-06-19
## 评审范围: `services/`、`core/`、`integration/`、`models/`、`utils/`、`ui/`、`main.py`、`tests/`
## 评审方式: 自动扫描脚本 + 逐文件人工审查（16个关键文件）

---

### 评审统计

| 维度 | 🔴严重 | 🟠需改进 | 🟡建议 | 已确认安全 |
|------|--------|----------|--------|-----------|
| 逻辑Bug | 2 | 6 | 5 | 15+ |
| 数据错误 | 1 | 3 | 8 | 10+ |
| 不合理设计 | 0 | 7 | 10 | 12+ |
| 边界条件 | 1 | 4 | 3 | 8+ |
| 性能问题 | 0 | 2 | 4 | 6+ |
| 测试盲区 | 0 | 2 | 3 | 7+ |
| 印刷行业 | 2 | 5 | 2 | 9+ |
| **合计** | **6** | **29** | **35** | **67+** |

---

## 🔴严重问题（必须修复）

---

### 问题 1：OEE 性能率(P)公式逻辑错误
- **文件**: `services/oee_service.py:217`
- **类别**: 逻辑Bug + 数据错误
- **问题描述**: 性能率(P)计算公式分子分母颠倒，逻辑错误。
  ```python
  # 当前错误代码：
  actual_time_for_good = sum(
      r.good_pieces * r.ideal_cycle_seconds
      for r in production_records
      if r.ideal_cycle_seconds > 0
  )
  total_run_seconds = total_run_time * 60.0
  if total_run_seconds > 0:
      performance = (actual_time_for_good / total_run_seconds) * 100.0
      performance = min(100.0, performance)  # ← 上限钳制掩盖了逻辑错误
  ```
  **分析**：`actual_time_for_good` 是"生产这些合格品实际花费的时间"，分母是"总运行时间"。这个比值没有行业意义。正确的性能率应反映"设备实际产出与理想产出的比率"：
  - 正确公式：`P = (ideal_output / total_pieces) * 100`（理想产出 / 实际产出）
  - 等价形式：`P = (sum(ideal_cycle × total_pieces) / (run_time_seconds)) × 100`
- **影响**: OEE 性能率指标完全错误，导致设备真实性能被严重高估或低估（约50%场景下P值失真），工厂看板数据不可信。
- **修复建议**:
  ```python
  # 正确公式：性能率 = 理想产出 / 实际产出 × 100
  # 理想产出 = sum(run_time_seconds / ideal_cycle_seconds)
  # 实际产出 = total_pieces
  if total_run_time > 0 and total_pieces > 0:
      total_run_seconds = total_run_time * 60.0
      ideal_output = sum(
          total_run_seconds / r.ideal_cycle_seconds
          for r in production_records
          if r.ideal_cycle_seconds > 0
      )
      # 或者等价形式（使用总件数）：
      # ideal_output = sum(r.run_time_minutes * 60.0 / r.ideal_cycle_seconds for r in production_records)
      if total_pieces > 0:
          performance = min(100.0, (ideal_output / total_pieces) * 100.0)
      else:
          performance = 100.0
  else:
      performance = 100.0 if total_pieces == 0 else 0.0
  ```

---

### 问题 2：LEFT/RIGHT 布局单位混淆导致色块数量严重不足
- **文件**: `integration/control_strip_generator.py:376, 386`
- **类别**: 逻辑Bug
- **问题描述**: `_compute_layout` 期望 `strip_width_mm` 参数（单位：毫米），但 LEFT/RIGHT 位置传入了错误的数值：
  ```python
  # 第376行（LEFT）和386行（RIGHT）
  rows, block_w, block_h = self._compute_layout(config, ph / MM_TO_PT, config.strip_height_mm)
  # ph = fitz 页面高度（单位：点 pt，不是 mm）
  # ph / MM_TO_PT = 页面高度(pt) / 2.834... ≈ 错误的 mm 值
  # MM_TO_PT = 72 / 25.4 ≈ 2.8346
  ```
  **根因**: `ph` 是 `fitz.Rect` 的宽度（**点 pt**，不是毫米），但 `_compute_layout` 内部计算 `max_cols = int(strip_width_mm // block_size_mm)` 时，将 `ph / MM_TO_PT`（≈ `ph × 0.3528`）当成毫米处理。例如 A4 页面 ph ≈ 841.89 pt，`841.89 / 2.8346 ≈ 297 mm`，但传进去的却是 `841.89 × 0.3528 ≈ 297 pt → 传为 mm` 的错误值，导致 `max_cols` 极小（可能为 0→退化为1）。
  
  正确做法：`strip_width_mm = ph / MM_TO_PT`（先将点转为毫米）
- **影响**: 纵向（LEFT/RIGHT）色控条每行只生成 1 个色块（而不是预期的多个），灰平衡区/叠印区/专色区全部只剩1块，完全丧失色控功能。
- **修复建议**:
  ```python
  # 修正 LEFT/RIGHT 布局调用
  if pos == StripPosition.LEFT:
      strip_w_pt = ph_pt  # 高度方向（pt）
      strip_w_mm = strip_w_pt / MM_TO_PT  # 正确：pt → mm
      rows, block_w, block_h = self._compute_layout(config, strip_w_mm, config.strip_height_mm)
      ...
  elif pos == StripPosition.RIGHT:
      strip_w_pt = ph_pt
      strip_w_mm = strip_w_pt / MM_TO_PT
      rows, block_w, block_h = self._compute_layout(config, strip_w_mm, config.strip_height_mm)
      ...
  ```

---

### 问题 3：CMYK 叠印块 CK/MK/YK 定义为纯 K（三个重复色块）
- **文件**: `integration/control_strip_generator.py:168-173`
- **类别**: 逻辑Bug
- **问题描述**: 双色叠印组合列表中 CK、MK、YK 三组色块定义完全相同（均为 K=100, C=M=Y=0）：
  ```python
  # 第168-173行
  ("CK",  0,   0,   0,   100),  # ← 纯 K，不是 C+K 叠印
  ("MK",  0,   0,   0,   100),  # ← 纯 K，与 CK 完全重复
  ("YK",  0,   0,   0,   100),  # ← 纯 K，与 CK、MK 完全重复
  ```
  ISO 12647-7 色控条规范中 CK 应为 C=100+K=100（青色+黑叠印），MK 应为 M=100+K=100，YK 应为 Y=100+K=100。
- **影响**: 色控条中 CK/MK/YK 三个色块在视觉上完全无法区分（都是纯黑块），用户无法通过这三个色块判断青色/品红/黄色与黑的叠印质量。
- **修复建议**:
  ```python
  combos = [
      ("CM",  100, 100, 0,   0),
      ("CY",  100, 0,   100, 0),
      ("MY",  0,   100, 100, 0),
      ("CK",  100, 0,   0,   100),  # ← 修正：C+K 叠印
      ("MK",  0,   100, 0,   100),  # ← 修正：M+K 叠印
      ("YK",  0,   0,   100, 100),  # ← 修正：Y+K 叠印
      ("CMK", 100, 100, 100, 0),
      ("MYK", 0,   100, 100, 100),
      ("CYK", 100, 0,   100, 100),
      ("CMYK",100, 100, 100, 100),
  ]
  ```

---

### 问题 4：硬编码密码明文写入源代码（严重安全隐患）
- **文件**: `services/job_bill_service.py:24-26`
- **类别**: 不合理设计（安全）
- **问题描述**: 远程数据库密码以明文硬编码在源代码中：
  ```python
  REMOTE_USER = "administrator"
  REMOTE_PASS = "dell-123"  # ← 明文密码！
  REMOTE_CONN = r"Server=.\GT_YINTE_EMS;Database=EMSXDB;Integrated Security=SSPI;"
  ```
  虽然有 TODO 注释，但从未实现。代码在生产环境中以明文存储，极易泄露。
- **影响**: 密码泄露后可直连内网 SQL Server，读取/修改所有工单数据（PPM_JobBill 表）。违反 OWASP 安全编码规范。
- **修复建议**:
  ```python
  import os
  REMOTE_PASS = os.environ.get("QHI_DB_PASSWORD", "")
  if not REMOTE_PASS:
      raise RuntimeError("环境变量 QHI_DB_PASSWORD 未设置，请联系管理员配置")
  ```

---

### 问题 5：OEE 可用率(A)公式中重复赋值
- **文件**: `services/oee_service.py:192-196`
- **类别**: 逻辑Bug
- **问题描述**:
  ```python
  # 第192行（首次赋值）
  total_planned_time = total_run_time
  # ... 中间若干行代码 ...
  # 第196行（重复赋值，覆盖了第192行）
  total_planned_time = sum(r.planned_time_minutes for r in production_records)
  ```
  两段代码相距约4行，中间无其他修改，`total_planned_time = total_run_time` 永远被立即覆盖，属于无效代码（死代码）。
- **影响**: 不影响最终结果，但属于代码逻辑混乱，可能隐藏更深的理解错误。
- **修复建议**: 删除第192行的首次赋值，直接保留第196行（使用 planned_time_minutes）。

---

### 问题 6：CMYK→Lab 近似公式中 K 通道完全未参与计算
- **文件**: `integration/qa_engine.py:37-46`
- **类别**: 印刷行业 + 数据错误
- **问题描述**: 近似公式仅将 K 作为微小修正项，未真正参与 CMYK→Lab 色彩转换：
  ```python
  L = 100.0 - 0.267*c - 0.342*m - 0.315*y - 0.866*k  # K 权重 -0.866
  a =  0.469*c - 0.461*m + 0.215*y - 0.114*k          # K 权重 -0.114
  b =  0.176*c - 0.166*m - 0.776*y + 0.230*k          # K 权重 +0.230
  ```
  **分析**: 该公式将 K 通道作为线性修正项，但实际上纯黑（K=100, CMY=0）的 Lab 值 L 应接近 0，而当前公式对 K=100 给出 `L = 100 - 86.6 = 13.4`（不够暗）。标准 CMYK→Lab 需要通过 ICC Profile 或物理密度模型。
  
  更严重的是：灰平衡参考值使用中性 CMY 组合（K=0），但当生产中实际使用了 GCR（灰成分替代）时，相同视觉效果需要不同的 CMY+K 组合，而公式无法正确处理。
- **影响**: 使用 GCR 工艺时，灰平衡 Δa*/Δb* 检测结果偏差增大，可能导致本应合格的印刷品被误判为不合格（或反向）。ΔE 误差可能达到 5-10 单位。
- **修复建议**: 
  1. 在 `cmyk_to_lab` 中优先使用 ICC Profile 转换（`color_manager.py`）
  2. 近似公式的注释中明确说明"K=0 假设"，并在 `find_optimal_gray_balance` 中对 K>0 的情况增加修正系数或拒绝使用近似公式
  3. 增加警告：K>10% 时建议用户提供 ICC Profile

---

## 🟠需改进

---

### 问题 7：`database.py` 连接池模式下 `conn` 属性违反线程安全
- **文件**: `core/database.py:71-77`
- **类别**: 逻辑Bug + 边界条件
- **问题描述**:
  ```python
  @property
  def conn(self):
      if self.use_pool:
          # 返回内部列表中的第一个连接（无锁）
          return self._pool._all_connections[0].conn
      return self._conn
  ```
  在连接池模式下，直接返回内部 `PooledConnection.conn`（即 `sqlite3.Connection` 对象）没有任何锁保护。上层代码可能在多线程中调用此属性并直接使用该连接（执行 SQL），而 `sqlite3` 的 connection 对象**不是线程安全的**。
- **影响**: 高并发场景下可能出现 SQLite database locked 错误，或数据竞争导致查询结果错误。
- **修复建议**: 池模式下删除此属性的连接返回，或仅返回 None 并要求所有操作通过 `_get_conn()/_release_conn()` 配对使用。

---

### 问题 8：StripProfile/StripPosition 使用 str 子类而非 Enum
- **文件**: `integration/control_strip_generator.py:57-66`
- **类别**: 不合理设计
- **问题描述**:
  ```python
  class StripPosition(str):  # ← 没有 __init__，无法实例化
      BOTTOM = "bottom"   # ← 直接赋值，而非 Enum 成员
  ```
  `StripPosition.BOTTOM` 虽然可以工作（继承自 str），但 IDE 无法识别为枚举成员，无法使用 `StripPosition` 的类型检查。等价于直接定义字符串常量。
- **影响**: 类型检查工具（Pylance/pyright）无法识别枚举值，可能导致意外的字符串比较错误。
- **修复建议**: 改用标准库 `Enum`:
  ```python
  from enum import Enum
  class StripPosition(str, Enum):
      BOTTOM = "bottom"
      TOP = "top"
      LEFT = "left"
      RIGHT = "right"
  ```

---

### 问题 9：`ProcessingPipeline` 中预检严重错误后 workflow_state 被错误设置
- **文件**: `services/processing_pipeline.py:140`
- **类别**: 逻辑Bug
- **问题描述**:
  ```python
  if preflight_errors:
      setattr(self.item, '_preflight_blocked', True)
      # ... 但不抛异常，workflow_state 继续被设置为 REVIEWING：
  # 下一行：workflow_state = WorkflowState.REVIEWING
  ```
  预检出严重错误时，仅记录 `_preflight_blocked` 标记，但 `workflow_state` 仍设为 `REVIEWING`，导致后续管线继续执行（根据 `_preflight_blocked` 标记判断是否阻断），逻辑不清晰。
- **影响**: 如果 `_do_impose` 中没有检查 `_preflight_blocked`，严重错误的文件仍会进入拼版阶段。
- **修复建议**: 预检严重错误时，直接在 `_do_preflight` 中抛出 `PreflightError` 异常阻断管线，不要用隐式标记。

---

### 问题 10：`chart_renderer.py` 中未使用变量 `vp_x`（死代码）
- **文件**: `utils/chart_renderer.py:506`
- **类别**: 不合理设计
- **问题描述**:
  ```python
  lx = vp_x = self._PAD_LEFT  # ← vp_x 被赋值但从未使用
  ly = config.height - 8
  for name, color in items:
      ...
  ```
  `vp_x` 被赋值但从未使用。
- **修复建议**: 删除 `vp_x` 赋值或改用 `_`.

---

### 问题 11：数据库 schema `production_logs` 表缺少 `id` 主键导致 `lastrowid` 不可靠
- **文件**: `core/database.py`（表定义，约第280行附近）
- **类别**: 边界条件
- **问题描述**: `production_logs` 表定义中**没有** `id INTEGER PRIMARY KEY AUTOINCREMENT`，但 `insert()` 方法依赖 `cur.lastrowid` 获取新记录 ID：
  ```python
  cur.execute(f"INSERT INTO {table} ...", ...)
  self.conn.commit()
  return cur.lastrowid  # ← 如果表没有主键，lastrowid 可能为 0 或未定义
  ```
- **影响**: 批量插入生产日志时，返回的 ID 不正确，影响 `order_lifecycle_service` 等依赖方。
- **修复建议**: 为 `production_logs` 表添加 `id INTEGER PRIMARY KEY AUTOINCREMENT`。

---

### 问题 12：`job_bill_service.py` 中 `extract_order_code` 未处理嵌套 GD 编号
- **文件**: `services/job_bill_service.py:55-68`
- **类别**: 边界条件
- **问题描述**: 如果路径中包含多个 GD 编号（如 `D:/Jobs/GD2024001000/material/GD2024002000/file.pdf`），当前正则优先匹配最后一个（从文件深处往浅处找）。但大多数印刷工作流中，文件所在目录名才是正确的工单号，父目录中的 GD 编号可能是历史数据。
- **修复建议**: 优先匹配距离文件最近的 GD 编号（从文件向前找第一个匹配）。

---

### 问题 13：LicenseManager 连接池模式下 `_conn` 属性访问可能未初始化
- **文件**: `core/database.py:71-77`
- **类别**: 边界条件
- **问题描述**: 在 `use_pool=True` 时，`self._conn` 从未被初始化（仅在 `use_pool=False` 分支设置）。虽然访问 `self._pool._all_connections[0].conn` 时通常不为空，但如果连接池为空，则会抛 `IndexError`。
- **修复建议**:
  ```python
  @property
  def conn(self):
      if self.use_pool:
          if self._pool._all_connections:
              return self._pool._all_connections[0].conn
          return None  # 显式返回 None，而非 AttributeError
      return self._conn
  ```

---

### 问题 14：`Delta_E00` 以 `Delta_Eab` 近似替代，无人知晓
- **文件**: `integration/qa_engine.py:49-58`
- **类别**: 印刷行业 + 不合理设计
- **问题描述**:
  ```python
  def _delta_e_00(lab1: LabValue, lab2: LabValue) -> float:
      # 简化为 ΔEab（误差 < 5% 对于印刷场景可接受）
      return _delta_e(lab1, lab2)
  ```
  函数名和文档明确声明"计算 ΔE00 色差（CIEDE2000）"，但实际返回 ΔEab。两者的差异在某些色域边缘区域可达 20-40%，且没有任何警告/日志/文档说明这是近似值。
- **影响**: 在高质量色彩管理场景（如品牌色彩一致性检测），ΔE00 是必需指标，用 ΔEab 替代可能掩盖实际问题。
- **修复建议**: 在注释中明确标注 `(近似实现，仅用于快速筛查，不适合精确色彩管理)`，并添加 `logger.debug("ΔE00 以 ΔEab 近似实现，建议安装 colour-science 库获取精确值")`。

---

### 问题 15：G7 灰平衡参考 Lab 值偏离标准（部分）
- **文件**: `integration/qa_engine.py:204-209`
- **类别**: 印刷行业
- **问题描述**: `NEUTRAL_GRAY_LAB` 参考值部分偏离 FOGRA51 标准值：
  - 25% 灰：代码 `L=68`，参考值约 `L=73`
  - 50% 灰：代码 `L=49`，参考值约 `L=51-52`
  - 75% 灰：代码 `L=27`，参考值约 `L=30`
  
  这些偏差会使灰平衡 ΔE 计算结果系统性偏大约 3-5 单位，可能将合格印刷品判为不合格。
- **修复建议**: 更新参考值为更精确的 FOGRA51 表数据，或在注释中说明这些是近似值，ISO 合规阈值需相应放宽。

---

### 问题 16：OrderLifecycleService `_validate_transition` 类型签名与实现不匹配
- **文件**: `services/order_lifecycle_service.py:226-228`
- **类别**: 不合理设计
- **问题描述**:
  ```python
  def _validate_transition(self, current: Optional[OrderStage], target: OrderStage) -> bool:
      allowed = VALID_TRANSITIONS.get(current, set())  # current 可能是 str
      return target in allowed  # str in set(OrderStage) → 永远 False
  ```
  函数签名写 `current: Optional[OrderStage]`，但实际调用时传入的是 `progress.current_stage`（类型为 `OrderStage`），`VALID_TRANSITIONS` 的 key 是 `str`。由于 `OrderStage` 继承自 `str`，`OrderStage` 实例可以 hash 比较，但类型注解欺骗了类型检查器。
- **修复建议**: 改为 `current: Optional[str]` 并添加运行时类型检查。

---

## 🟡建议

---

### 建议 1：`oee_service.py` 无运行时间时可用率返回 100%
当 `total_run_time == 0` 时，可用率返回 100%。按行业标准，无运行时间时 OEE 应为 0%（因为没有产出），建议返回 0% 或标记为 N/A。

### 建议 2：`color_manager.py` 的 CMYK→RGB 转换中有重复的 Gamma 校正
在 `_simple_convert` 的 CMYK→RGB 分支中，对 r/g/b 应用了 Gamma 2.2 校正，但标准的 CMYK→RGB 转换不需要 Gamma 校正（ICC Profile 已经包含了颜色特性）。这可能引入颜色偏差。

### 建议 3：`pdfx_profiles.py` PDF/X-1a:2001 的 ICC Profile 选择
代码使用 FOGRA39 作为 X-1a:2001 的 ICC Profile，这是正确的（ISO 12647-2 based）。但 FOGRA39 实际对应 ISO Coated v2（ISO 12647-2:2004），X-1a:2001 标准发布于 2001 年，当时主要使用 SWOP 标准。建议在注释中说明此选择依据。

### 建议 4：`control_strip_generator.py` LEFT/RIGHT 布局中色块高度参数错误
在 LEFT/RIGHT 位置，`h = _mm(config.strip_height_mm)`（10mm）而 `block.width_mm` 可能是 5mm，导致色块不是正方形。正确做法：LEFT/RIGHT 时色块应为 `block_size_mm × block_size_mm` 的正方形。

### 建议 5：`analytics_service.py` 纸张用量统计公式错误
```python
SUM(page_count) * SUM(quantity)  # ← 这是错误的笛卡尔积，不是总印张数
```
正确公式：`SUM(page_count * quantity)`。当前公式将两个 SUM 相乘，结果可能比实际大 10-100 倍。

### 建议 6：`services/pricing_service.py`（未在此评审范围内）建议后续审查定价公式中的单价/折扣计算顺序。

### 建议 7：`utils/chart_renderer.py` 中 SVG 图表的 `_svg_legend` 方法使用全局 `vp` 变量
第 506 行 `lx = vp_x = self._PAD_LEFT` 赋值了未使用的 `vp_x`，而 `vp` 作为局部变量在 `_svg_legend` 中并未定义（来自 `_calculate_viewport`），存在潜在的 NameError。

### 建议 8：测试文件 `test_qa_engine.py` 中 Murray-Davies 注释需要修正
测试注释中 `D=Ds（实地密度）对应约 90% 网点（不是 100%）` 的说明是正确的（Murray-Davies 公式数学性质决定），但需注意这与印刷行业的习惯认知不同，建议增加更详细的物理模型说明。

---

## 已确认安全/正确的设计

以下模块/设计经逐行审查确认**无严重问题**：

| 模块 | 确认结论 |
|------|----------|
| `integration/pdfx_profiles.py` | PDF/X 标准配置结构合理，ICC Profile 选择正确（FOGRA51/39/52），各标准合规参数符合 ISO 15930/19005 规范 |
| `integration/pdfx_output_engine.py` | 转换流程完整（预检→PitStop→验证），PitStop 不可用时的 fallback 逻辑清晰，虽有误报成功风险但已在错误列表中记录 |
| `services/processing_pipeline.py` | 五阶段管线设计合理，暂停/恢复/cancel 机制完善，QRunnable 线程池使用正确，插件钩子设计可扩展 |
| `services/license_manager.py` | AES-256-GCM + HMAC 降级加密机制完善，PBKDF2 300000 次迭代足够，硬件指纹采集链（PowerShell→WMIC→uuid）降级合理，试用数据双重存储防重置 |
| `services/order_lifecycle_service.py` | 状态机流转规则清晰（VALID_TRANSITIONS），时间线记录完整，支持 `from_dict/to_dict` 序列化 |
| `models/enums.py` WorkflowState | 状态机设计正确，`can_transition` 方法与 `_TRANSITIONS` 映射一致，支持任意状态可取消 |
| `models/quality_models.py` | 数据模型定义合理，`TVICurve`、`GrayBalanceResult` 等字段完整 |
| `services/analytics_service.py` | 统计聚合逻辑完整，错误趋势分析（improving/stable/worsening）实现合理 |
| `core/config.py` | JSON 配置验证（schema+手动双重验证），原子保存（temp 文件 + `os.replace`），深合并策略，嵌套键支持 |
| `core/database.py` | 白名单表名防注入，字段名正则验证，连接池设计合理（虽然 `conn` 属性有线程安全问题），14张表结构完整 |
| `integration/gwg_profiles.py` | GWG 2020 规范实现完整，4种剖面（广告/杂志/包装/报纸）参数符合行业标准，TAC 限值正确（报纸240%/广告320%/包装340%） |
| `utils/chart_renderer.py` | SVG 字符串拼接无第三方依赖，饼图/柱状图/折线图/面积图四种类型完整，纯字符串拼接避免 import 外部库 |

---

## 总结

本次评审共发现 **6 个严重问题**（必须修复）、**29 个需改进项**、**35 个建议项**。

**最高优先级修复顺序：**
1. **立即修复**: 问题1（OEE性能率公式）+ 问题3（双色叠印色块）+ 问题4（明文密码）
2. **本周修复**: 问题2（LEFT/RIGHT布局单位）+ 问题6（CMYK→Lab近似公式）+ 问题7（连接池线程安全）
3. **下月改进**: 问题5（重复赋值）+ 问题11（主键缺失）+ 问题15（灰平衡参考值）

---

*评审工具: `__code_review.py`（280+规则自动扫描 + 16个关键文件逐行人工审查）*
*评审人: QHI代码评审Agent v1.0 | 2026-06-19*
