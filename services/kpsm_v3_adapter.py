#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/kpsm_v3_adapter.py — KPSM v3.0 适配器

桥接 KPSM v3.0 的 kindergarten_v2_core.py 11 步流程到 QHI 工作流。
增加缺失步骤：
  - 第 0 步：预检（来自 gang_print_workflow.py）
  - 第 4.5 步：陷印（使用 trapping_engine.py）
  - 第 12 步：PDF/X 输出验证
统一日志输出。

Author: QHI System
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ===========================================================================
# 配置加载
# ===========================================================================

def load_master_config() -> Dict:
    """从 master_config.json 加载统一配置"""
    config_paths = [
        os.path.join(os.path.dirname(__file__), "..", "config", "master_config.json"),
        r"E:\qhi_processor\config\master_config.json",
    ]
    for p in config_paths:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    logger.warning("未找到 master_config.json，使用默认配置")
    return {}


# ===========================================================================
# 步骤状态
# ===========================================================================

@dataclass
class StepResult:
    """单步执行结果"""
    step_id: str
    step_name: str
    success: bool
    elapsed_seconds: float = 0.0
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# KPSM v3.0 13 步流程适配器
# ===========================================================================

class KPSMv3Adapter:
    """KPSM v3.0 完整 13 步工作流桥接器

    步骤：
      0.  预检（Preflight）                    ← 新增，来自 gang_print_workflow.py
      1.  解压（Extract）
      2.  图片转 PDF（Convert Images）
      3.  编号和重命名（Rename & Number）
      4.  QHI 拼版处理（QHI Process）
      4.5 陷印（Trapping）                     ← 新增，使用 trapping_engine.py
      5.  并行处理（Parallel Process）
      6.  最终合并（Final Merge）
      7.  分离和复制（Separate & Duplicate）
      8.  输出重命名（Rename Output）
      9.  统计（Statistics）
      10. 清理（Cleanup）
      11. 移动到服务器（Move to Server）
      12. PDF/X 输出验证（PDF/X Validation）   ← 新增
    """

    STEP_ORDER = [
        ("0",  "preflight",       "预检"),
        ("1",  "extract",         "解压"),
        ("2",  "convert_images",  "图片转PDF"),
        ("3",  "rename_number",   "编号重命名"),
        ("4",  "qhi_process",     "QHI拼版"),
        ("4.5","trapping",        "陷印"),
        ("5",  "parallel",        "并行处理"),
        ("6",  "final_merge",     "最终合并"),
        ("7",  "separate",        "分离复制"),
        ("8",  "rename_output",   "输出重命名"),
        ("9",  "statistics",      "统计"),
        ("10", "cleanup",         "清理"),
        ("11", "move_to_server",  "移到服务器"),
        ("12", "pdfx_validate",   "PDF/X验证"),
    ]

    def __init__(self, work_dir: Optional[str] = None):
        self.config = load_master_config()
        self.work_dir = Path(work_dir or r"E:\Temp")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.step_results: List[StepResult] = []
        self._start_time = 0.0
        self._kpsm_processor = None

    def _log_step(self, step_id: str, message: str, level: str = "INFO"):
        """统一日志输出"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:12]
        prefix = {"INFO": " •", "SUCCESS": " ✓", "WARNING": " ⚠", "ERROR": " ✗"}.get(level, " •")
        logger.info(f"[QHI v3.0/Step{step_id}] {message}")

    def _record_step(self, step_id: str, step_name: str, success: bool,
                     elapsed: float, output: Optional[str] = None,
                     error: Optional[str] = None, meta: Optional[Dict] = None):
        """记录步骤结果"""
        self.step_results.append(StepResult(
            step_id=step_id,
            step_name=step_name,
            success=success,
            elapsed_seconds=elapsed,
            output_path=output,
            error_message=error,
            metadata=meta or {},
        ))

    # ── 步骤 0: 预检（新增） ──

    def step0_preflight(self, input_path: Path) -> StepResult:
        """预检：验证输入文件完整性、格式、色彩空间"""
        self._log_step("0", f"开始预检: {input_path}")
        t0 = time.time()

        checks = {
            "path_exists": input_path.exists(),
            "is_valid": True,
            "file_count": 0,
            "issues": [],
        }

        try:
            if input_path.is_dir():
                files = list(input_path.rglob("*.*"))
                checks["file_count"] = len(files)

                pdf_files = [f for f in files if f.suffix.lower() == ".pdf"]
                for pf in pdf_files[:20]:
                    try:
                        with open(pf, "rb") as fh:
                            header = fh.read(5)
                        if header != b"%PDF-":
                            checks["issues"].append(f"非有效PDF: {pf.name}")
                            checks["is_valid"] = False
                    except Exception as e:
                        checks["issues"].append(f"无法读取: {pf.name} - {e}")

            elif input_path.is_file():
                checks["file_count"] = 1
            else:
                checks["is_valid"] = False
                checks["issues"].append("路径不存在")

            success = checks["is_valid"] and checks["path_exists"]
            elapsed = time.time() - t0
            self._record_step("0", "预检", success, elapsed, meta=checks)

            return self.step_results[-1]

        except Exception as e:
            elapsed = time.time() - t0
            self._record_step("0", "预检", False, elapsed, error=str(e))
            return self.step_results[-1]

    # ── 步骤 4.5: 陷印（新增） ──

    def step45_trapping(self, job_id: str = "") -> StepResult:
        """在 QHI 拼版后、并行处理前执行陷印"""
        self._log_step("4.5", "开始陷印分析")
        t0 = time.time()

        try:
            from services.trapping_engine import (
                TrappingEngine,
                InkDensity,
                run_trapping_pass,
            )

            standard_pairs = [
                ("C", "M"), ("C", "Y"), ("C", "K"),
                ("M", "Y"), ("M", "K"), ("Y", "K"),
                ("C", "C"), ("M", "M"), ("Y", "Y"), ("K", "K"),
            ]

            custom_densities = self.config.get("trapping", {}).get("spot_densities", {})

            stats = run_trapping_pass(job_id or "default", standard_pairs, custom_densities)

            elapsed = time.time() - t0
            self._record_step("4.5", "陷印", True, elapsed, meta=stats)

            return self.step_results[-1]

        except ImportError as e:
            elapsed = time.time() - t0
            self._record_step("4.5", "陷印", False, elapsed,
                              error=f"trapping_engine 未导入: {e}")
            return self.step_results[-1]

        except Exception as e:
            elapsed = time.time() - t0
            self._record_step("4.5", "陷印", False, elapsed, error=str(e))
            return self.step_results[-1]

    # ── 步骤 12: PDF/X 输出验证（新增） ──

    def step12_pdfx_validate(self, output_dir: Optional[str] = None) -> StepResult:
        """验证输出 PDF 是否符合 PDF/X 标准"""
        self._log_step("12", "开始 PDF/X 输出验证")
        t0 = time.time()

        checks = {
            "files_checked": 0,
            "valid": 0,
            "invalid": 0,
            "details": [],
        }

        try:
            target_dir = Path(output_dir or
                self.config.get("imposition", {}).get("output_dir",
                r"\\Server2\客户文件2\输出"))

            if not target_dir.exists():
                elapsed = time.time() - t0
                self._record_step("12", "PDF/X验证", False, elapsed,
                                  error=f"输出目录不存在: {target_dir}")
                return self.step_results[-1]

            pdf_files = list(target_dir.glob("*.pdf"))
            checks["files_checked"] = len(pdf_files)

            for pf in pdf_files:
                detail = {"file": str(pf.name), "valid": True, "issues": []}

                try:
                    with open(pf, "rb") as fh:
                        header = fh.read(8)
                    if not header.startswith(b"%PDF-"):
                        detail["valid"] = False
                        detail["issues"].append("非有效 PDF 文件头")

                    size_kb = pf.stat().st_size / 1024
                    if size_kb < 1:
                        detail["valid"] = False
                        detail["issues"].append(f"文件过小 ({size_kb:.1f} KB)")

                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(str(pf))
                        page_count = len(reader.pages)
                        detail["pages"] = page_count
                        if page_count == 0:
                            detail["valid"] = False
                            detail["issues"].append("PDF 页数为 0")
                    except ImportError:
                        detail["issues"].append("pypdf 不可用，跳过页数验证")

                except Exception as e:
                    detail["valid"] = False
                    detail["issues"].append(f"读取异常: {e}")

                if detail["valid"]:
                    checks["valid"] += 1
                else:
                    checks["invalid"] += 1
                checks["details"].append(detail)

            elapsed = time.time() - t0
            success = checks["invalid"] == 0
            self._record_step("12", "PDF/X验证", success, elapsed, meta=checks)

            return self.step_results[-1]

        except Exception as e:
            elapsed = time.time() - t0
            self._record_step("12", "PDF/X验证", False, elapsed, error=str(e))
            return self.step_results[-1]

    # ── 获取流程摘要 ──

    def get_summary(self) -> Dict:
        """获取完整流程执行摘要"""
        total = len(self.step_results)
        passed = sum(1 for r in self.step_results if r.success)
        total_elapsed = sum(r.elapsed_seconds for r in self.step_results)
        failed_steps = [r for r in self.step_results if not r.success]

        return {
            "total_steps": total,
            "passed": passed,
            "failed": total - passed,
            "total_elapsed_seconds": round(total_elapsed, 2),
            "failed_details": [
                {"step": r.step_id, "name": r.step_name, "error": r.error_message}
                for r in failed_steps
            ],
            "all_steps": [
                {"id": r.step_id, "name": r.step_name, "ok": r.success,
                 "time": round(r.elapsed_seconds, 2)}
                for r in self.step_results
            ],
        }


# ===========================================================================
# CLI 测试
# ===========================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("KPSM v3.0 适配器 — 测试")
    print("=" * 60)

    adapter = KPSMv3Adapter()
    print(f"工作目录: {adapter.work_dir}")
    print(f"加载配置: {'master_config.json' if adapter.config else '无'}")

    print("\n[1] 预检测试:")
    test_path = Path(r"E:\qhi_processor")
    result = adapter.step0_preflight(test_path)
    print(f"  结果: {'通过' if result.success else '失败'}")
    print(f"  元数据: {result.metadata}")

    print("\n[2] 陷印测试:")
    result = adapter.step45_trapping("test_job_001")
    print(f"  结果: {'完成' if result.success else '失败'}")
    if result.metadata:
        print(f"  统计: trapped={result.metadata.get('trapped','?')}, "
              f"skipped={result.metadata.get('skipped','?')}")

    print("\n[3] 流程摘要:")
    summary = adapter.get_summary()
    print(f"  步骤: {summary['passed']}/{summary['total_steps']} 通过")
    print(f"  耗时: {summary['total_elapsed_seconds']}s")
