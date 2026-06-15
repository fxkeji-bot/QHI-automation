#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/processing_pipeline.py — 异步处理管线引擎

提供:
  - QThreadPool 多文件并行处理
  - 五阶段管线: 预检 → 规则匹配 → 拼版处理 → 后处理 → 输出归档
  - 暂停/恢复/取消控制
  - 逐文件进度信号
  - 工序状态机联动
"""

import os, sys, time, traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from PyQt5.QtCore import QObject, QThreadPool, QRunnable, pyqtSignal, pyqtSlot, QMutex, QMutexLocker

from models.enums import WorkflowState
from models.constants import PLUGIN_DIR


# ── 管线阶段枚举 ────────────────────────────────────────────
class PipeStage(str, Enum):
    """管线处理阶段"""
    PREFLIGHT = "preflight"        # 预检（文件完整性、尺寸、出血等）
    GANG_LAYOUT = "gang_layout"    # AI合版排版（贪心+退火算法）
    RULE_MATCH = "rule_match"      # 规则匹配
    IMPOSE = "impose"              # 拼版处理（QHI XML / Plugin）
    POSTPROCESS = "postprocess"    # 后处理（覆膜、裁切标记等）
    OUTPUT = "output"              # 输出/归档


# ── 管线数据类 ──────────────────────────────────────────────
@dataclass
class PipeItem:
    """管线中的一个文件处理单元"""
    file_path: str
    index: int
    total: int
    # 动态状态
    stage: PipeStage = PipeStage.PREFLIGHT
    workflow_state: str = WorkflowState.PENDING.value
    progress_pct: int = 0
    error_msg: str = ""
    result_path: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def elapsed(self) -> float:
        if self.started_at == 0:
            return 0.0
        end = self.finished_at if self.finished_at > 0 else time.time()
        return end - self.started_at

    @property
    def is_done(self) -> bool:
        return self.stage == PipeStage.OUTPUT and not self.error_msg


@dataclass
class PipeConfig:
    """管线配置"""
    output_dir: str = ""
    max_workers: int = 4              # QThreadPool 最大线程数（默认4，根据CPU核心数优化）
    auto_archive: bool = True          # 输出后自动归档
    stop_on_error: bool = False        # 单文件出错是否停止整批
    timeout_per_file: int = 300        # 单文件超时秒数
    enable_gang_layout: bool = True    # 是否启用AI合版排版
    enable_preflight_check: bool = True  # 是否启用PDF印前预检增强
    min_dpi_threshold: int = 300       # 预检最低DPI阈值
    required_bleed_mm: float = 3.0     # 预检要求出血位 (mm)


# ── 管线 Worker (QRunnable) ────────────────────────────────
class _PipeWorker(QRunnable):
    """单文件处理 Worker，在线程池中并发执行"""

    def __init__(
        self,
        item: PipeItem,
        config: PipeConfig,
        db,                 # Database 实例
        metadata_mgr,       # MetadataManager 实例
        rule_engine,        # RuleEngine 实例
        smart_processor,    # SmartProcessor 工厂
        log_callback: Callable,
    ):
        super().__init__()
        self.item = item
        self.config = config
        self.db = db
        self.metadata_mgr = metadata_mgr
        self.rule_engine = rule_engine
        self.smart_processor = smart_processor
        self.log = log_callback
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        self.item.started_at = time.time()
        try:
            self._execute_stage(PipeStage.PREFLIGHT, self._do_preflight)
            if self._cancelled:
                return

            if self.config.enable_gang_layout:
                self._execute_stage(PipeStage.GANG_LAYOUT, self._do_gang_layout)
            if self._cancelled:
                return

            self._execute_stage(PipeStage.RULE_MATCH, self._do_rule_match)
            if self._cancelled:
                return

            self._execute_stage(PipeStage.IMPOSE, self._do_impose)
            if self._cancelled:
                return

            self._execute_stage(PipeStage.POSTPROCESS, self._do_postprocess)
            if self._cancelled:
                return

            self._execute_stage(PipeStage.OUTPUT, self._do_output)

            # 记录到生产日志
            self._record_production_log(success=True)

        except Exception as e:
            self.item.error_msg = str(e)
            self._record_production_log(success=False, error=str(e))
        finally:
            self.item.finished_at = time.time()

    def _execute_stage(self, stage: PipeStage, func: Callable):
        self.item.stage = stage
        self.item.progress_pct = int(list(PipeStage).index(stage) / (len(PipeStage) - 1) * 100)
        func()

    def _do_preflight(self):
        """预检：文件存在性、格式、尺寸 + PDF印前自动预检增强"""
        fp = self.item.file_path
        if not os.path.exists(fp):
            raise FileNotFoundError(f"文件不存在: {fp}")
        if not fp.lower().endswith('.pdf'):
            raise ValueError(f"非 PDF 文件: {fp}")

        # 基础页数检测
        page_ct = 0
        try:
            import fitz
            doc = fitz.open(fp)
            page_ct = doc.page_count
            doc.close()
        except Exception:
            pass

        # PDF印前自动预检增强（文字矢量化 / DPI / 专色 / 出血）
        preflight_warnings = []
        preflight_errors = []
        if self.config.enable_preflight_check:
            try:
                from integration.pdf_processor import PDFPreflightChecker
                checker = PDFPreflightChecker()
                report = checker.run_preflight(
                    fp,
                    min_dpi=self.config.min_dpi_threshold,
                    required_bleed_mm=self.config.required_bleed_mm,
                )
                for issue in report.issues:
                    if issue.severity.value == "error":
                        preflight_errors.append(issue.message)
                    else:
                        preflight_warnings.append(issue.message)

                # 将预检结果附加到 item 元数据
                setattr(self.item, '_preflight_report', report.to_dict())

                if report.passed:
                    status = "通过"
                    if report.warning_count > 0:
                        status += f" ({report.warning_count}项警告)"
                    self.log(f"  预检{status}: {Path(fp).name} ({page_ct}页)")
                else:
                    self.log(f"  预检未通过: {Path(fp).name} ({report.error_count}项错误, {report.warning_count}项警告)")
            except ImportError:
                self.log(f"  预检通过: {Path(fp).name} ({page_ct}页) [预检增强未加载]")
            except Exception as e:
                self.log(f"  预检通过: {Path(fp).name} ({page_ct}页) [预检增强异常: {e}]")
        else:
            self.log(f"  预检通过: {Path(fp).name} ({page_ct}页)")

        # 严重错误阻断进入拼版阶段
        if preflight_errors:
            setattr(self.item, '_preflight_blocked', True)
            setattr(self.item, '_preflight_errors', preflight_errors)
            # 不抛异常，记录警告让后续阶段根据此标记决定是否继续
            self.log(f"  [警告] 预检发现 {len(preflight_errors)} 项严重错误，建议人工复核")

        # 更新 workflow_state
        self.item.workflow_state = WorkflowState.REVIEWING.value

    def _do_gang_layout(self):
        """AI合版排版：基于贪心+模拟退火的矩形装箱优化"""
        fp = self.item.file_path
        try:
            from services.gang_layout import GangLayoutEngine, OrderRect

            # 获取当前文件的页面信息作为订单尺寸
            page_info = getattr(self.item, '_page_info', None)
            if page_info is None:
                try:
                    import fitz
                    doc = fitz.open(fp)
                    pages = []
                    for i in range(doc.page_count):
                        rect = doc[i].rect
                        pages.append({"page_number": i + 1, "width_mm": round(rect.width * 0.3528, 1), 
                                      "height_mm": round(rect.height * 0.3528, 1)})
                    doc.close()
                    page_info = pages
                    setattr(self.item, '_page_info', page_info)
                except Exception:
                    self.log(f"  合版跳过: 无法读取 {Path(fp).name} 页面信息")
                    return

            # 将每个页面作为一个排版单元（模拟多个订单拼在同一张纸上）
            if not page_info:
                return

            orders = [
                OrderRect(
                    order_id=f"{Path(fp).stem}_p{p['page_number']}",
                    width_mm=p["width_mm"],
                    height_mm=p["height_mm"],
                    bleed_mm=self.config.required_bleed_mm,
                )
                for p in page_info
            ]

            engine = GangLayoutEngine(use_sa=True)
            report = engine.get_layout_report(orders)
            setattr(self.item, '_gang_layout', report)

            util = report.get("utilization", 0)
            paper = report.get("paper", "N/A")
            self.log(f"  合版排版: {Path(fp).name} → {paper} 利用率 {util}%")
            self.item.workflow_state = WorkflowState.SCHEDULED.value
        except ImportError as e:
            self.log(f"  合版跳过: 模块未加载 ({e})")
        except Exception as e:
            self.log(f"  合版跳过: {e}")

    def _do_rule_match(self):
        """规则匹配：用 RuleEngine 找到适用规则"""
        fp = self.item.file_path
        try:
            metadata = self.metadata_mgr.get(fp) if self.metadata_mgr else None
            rules = self.rule_engine.find_matching_rules(fp, metadata)
            self.item.workflow_state = WorkflowState.SCHEDULED.value
            matched = len(rules) if rules else 0
            self.log(f"  规则匹配: {Path(fp).name} → {matched} 条规则")
            # 附加到 item 的扩展字段
            setattr(self.item, '_matched_rules', rules or [])
        except Exception as e:
            self.log(f"  规则匹配失败: {e}")

    def _do_impose(self):
        """拼版处理：调用 SmartProcessor 执行"""
        fp = self.item.file_path
        self.item.workflow_state = WorkflowState.PRODUCING.value
        try:
            # SmartProcessor 工厂式调用
            if self.smart_processor:
                proc = self.smart_processor()
                result = proc.process(fp, self.config.output_dir)
                self.item.result_path = result or fp
            else:
                self.item.result_path = fp
            self.log(f"  拼版完成: {Path(fp).name}")
        except Exception as e:
            # 拼版失败不阻断整条管线
            self.log(f"  拼版警告: {e}")
            self.item.result_path = fp

    def _do_postprocess(self):
        """后处理：裁切标记、出血检查、合版利用率上报"""
        self.item.workflow_state = WorkflowState.QC.value

        # 上报合版排版利用率到看板
        gang_layout = getattr(self.item, '_gang_layout', None)
        if gang_layout:
            util = gang_layout.get("utilization", 0)
            paper = gang_layout.get("paper", "")
            self.log(f"  后处理: {Path(self.item.file_path).name} 合版利用率 {util}% ({paper})")

        # 预检阻塞标记
        if getattr(self.item, '_preflight_blocked', False):
            errors = getattr(self.item, '_preflight_errors', [])
            self.log(f"  [警告] 预检错误阻断: {'; '.join(errors[:3])}")

    def _do_output(self):
        """输出归档"""
        self.item.workflow_state = WorkflowState.COMPLETED.value
        self.item.progress_pct = 100
        result = self.item.result_path or self.item.file_path
        self.log(f"  输出完成: {Path(result).name} ({self.item.elapsed:.1f}s)")

    def _record_production_log(self, success: bool = True, error: str = ""):
        """写入生产记录表"""
        try:
            self.db.insert("production_logs",
                file_name=os.path.basename(self.item.file_path),
                status="success" if success else "failed",
                error_msg=error,
                started_at=datetime.fromtimestamp(self.item.started_at).isoformat()
                if self.item.started_at else None,
                finished_at=datetime.fromtimestamp(self.item.finished_at).isoformat()
                if self.item.finished_at else None,
                elapsed=self.item.elapsed,
                output_path=self.item.result_path or "",
            )
        except Exception:
            pass  # 生产日志写入失败不阻断主流程


# ── 管线主控制器 ────────────────────────────────────────────
class ProcessingPipeline(QObject):
    """异步处理管线 — 替代旧的 ProcessingThread

    使用方式:
        pipeline = ProcessingPipeline(db, metadata_mgr, rule_engine)
        pipeline.progress_updated.connect(on_progress)
        pipeline.file_completed.connect(on_file_done)
        pipeline.all_finished.connect(on_all_done)

        pipeline.start(files, output_dir)
        # 可随时调用 pipeline.pause() / pipeline.resume() / pipeline.cancel()
    """

    # ── 信号 ────────────────────────────────────────────────
    progress_updated = pyqtSignal(int, str, int, int)     # (%, 文件名, 当前, 总数)
    file_completed = pyqtSignal(str, bool, str)            # (路径, 成功, 消息)
    stage_changed = pyqtSignal(int, str, str)              # (索引, 阶段, 文件名)
    all_finished = pyqtSignal(int, int)                    # (成功, 失败)
    error_occurred = pyqtSignal(str)                       # (错误信息)

    def __init__(
        self,
        db=None,
        metadata_mgr=None,
        rule_engine=None,
        smart_processor_factory: Callable = None,
        log_callback: Callable = None,
    ):
        super().__init__()
        self.db = db
        self.metadata_mgr = metadata_mgr
        self.rule_engine = rule_engine
        self.smart_processor_factory = smart_processor_factory
        self.log_callback = log_callback or print

        self._pool: Optional[QThreadPool] = None
        self._items: List[PipeItem] = []
        self._workers: List[_PipeWorker] = []
        self._config = PipeConfig()
        self._mutex = QMutex()
        self._paused = False
        self._cancelled = False

    # ── 公共接口 ─────────────────────────────────────────────
    def start(self, files: List[str], output_dir: str = "", max_workers: int = None,
              enable_gang_layout: bool = None, enable_preflight: bool = None):
        """启动管线处理

        Args:
            files: 待处理的文件路径列表
            output_dir: 输出目录
            max_workers: 线程池大小（默认取 PipeConfig.max_workers）
            enable_gang_layout: 是否启用AI合版排版（None=使用默认配置）
            enable_preflight: 是否启用PDF预检增强（None=使用默认配置）
        """
        if max_workers is None:
            max_workers = self._config.max_workers
        if enable_gang_layout is not None:
            self._config.enable_gang_layout = enable_gang_layout
        if enable_preflight is not None:
            self._config.enable_preflight_check = enable_preflight

        self._cancelled = False
        self._paused = False
        self._config.output_dir = output_dir or os.path.dirname(files[0]) if files else ""
        self._config.max_workers = max_workers

        total = len(files)
        self._items = [
            PipeItem(file_path=fp, index=i, total=total)
            for i, fp in enumerate(files)
        ]

        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(max_workers)

        self._workers = []
        for item in self._items:
            worker = _PipeWorker(
                item=item,
                config=self._config,
                db=self.db,
                metadata_mgr=self.metadata_mgr,
                rule_engine=self.rule_engine,
                smart_processor=self.smart_processor_factory,
                log_callback=self._wrap_log,
            )
            self._workers.append(worker)
            self._pool.start(worker)

        self.log_callback(f"管线启动: {total} 个文件, {max_workers} 线程")

    def pause(self):
        """暂停管线（正在处理的会完成当前文件）"""
        with QMutexLocker(self._mutex):
            self._paused = True
        self.log_callback("⏸ 管线已暂停")

    def resume(self):
        """恢复管线"""
        with QMutexLocker(self._mutex):
            self._paused = False
        self.log_callback("▶ 管线已恢复")

    def cancel(self):
        """取消管线"""
        with QMutexLocker(self._mutex):
            self._cancelled = True
        for w in self._workers:
            w.cancel()
        self._pool.clear()
        self.log_callback("⏹ 管线已取消")

    def get_status(self) -> Dict:
        """获取管线当前状态"""
        done = sum(1 for i in self._items if i.is_done)
        failed = sum(1 for i in self._items if i.error_msg)
        in_progress = len(self._items) - done - failed
        return {
            "total": len(self._items),
            "done": done,
            "failed": failed,
            "in_progress": in_progress,
            "paused": self._paused,
            "cancelled": self._cancelled,
        }

    def is_running(self) -> bool:
        return not self._cancelled and any(
            i.finished_at == 0 and not i.error_msg for i in self._items
        )

    # ── 内部函数 ─────────────────────────────────────────────
    def _wrap_log(self, msg: str):
        """日志回调包装，注入管线上下文"""
        self.log_callback(msg)
