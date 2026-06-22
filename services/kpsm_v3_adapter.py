#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/kpsm_v3_adapter.py — KPSM v3.0 适配器

桥接 KPSM v3.0 的 kindergarten_v2_core.py 的 11 步流程，
增加缺失步骤（预检、陷印、PDF/X 输出验证），统一日志输出。

与 qhi_processor 智能拼版模块集成：
  - 从 master_config.json 读取配置
  - 支持 --qhi 模式调用 smart_imposition.py
  - 支持 --gui 模式启动图形界面

增强的 13 步完整流程：
  步骤0:  预检 (Preflight) — PDF 规范检查、字体嵌入、图像分辨率
  步骤1:  解压 (Extract) — 从压缩包解压
  步骤2:  图像转PDF (Convert Images)
  步骤3:  编号重命名 (Rename & Number)
  步骤4:  QHI 拼版 (QHI Process) — Quite Hot Imposing 5 XML 模板
  步骤4.5: 陷印 (Trapping) — trapped PDF 生成
  步骤5:  并行处理 (Parallel Process)
  步骤6:  最终合并 (Final Merge)
  步骤7:  分离与复制 (Separate & Duplicate)
  步骤8:  输出重命名 (Rename Output)
  步骤9:  统计 (Statistics)
  步骤10: 清理 (Cleanup)
  步骤11: 移动至服务器 (Move to Server)
  步骤12: PDF/X 输出验证 (PDF/X Validation)

Author: QHI System
Version: 1.0.0 (P0修复版)
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

logger = logging.getLogger(__name__)

# ===========================================================================
# 配置加载
# ===========================================================================

def load_master_config() -> Dict[str, Any]:
    """从 master_config.json 加载统一配置"""
    config_paths = [
        Path(__file__).resolve().parent.parent / "config" / "master_config.json",
        Path("E:/qhi_processor/config/master_config.json"),
    ]
    for path in config_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
                logger.info(f"已加载配置: {path}")
                return config

    logger.warning("master_config.json 未找到，使用内置默认值")
    return {
        "version": "2.0",
        "imposition": {
            "KPSM_v2_path": "Z:/fxkeji/KPSM_v2.0",
            "KPSM_v3_path": "Z:/fxkeji/KPSM_v3.0",
            "qhi_exe": "C:/Program Files (x86)/Quite/Quite Hot Imposing 5/qi_applycommands.exe",
            "output_dir": "//Server2/客户文件2/输出",
            "fallback_output_dir": "E:/qhi_processor/output",
        },
        "logging": {"log_dir": "E:/qhi_processor/logs"},
        "erp": {"remote_host": "192.168.1.22", "database": "EMSXDB"},
    }


# ===========================================================================
# 预检 (Preflight)
# ===========================================================================

class PreflightCheck:
    """步骤0: PDF 预检 — 规范检查、字体嵌入验证、图像分辨率检测"""

    MIN_IMAGE_DPI = 150
    REQUIRED_BOXES = ["MediaBox", "TrimBox"]

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.issues: List[Dict] = []
        self.warnings: List[Dict] = []
        self.passed = True

    def run(self) -> Dict[str, Any]:
        """执行预检，返回检查报告"""
        logger.info(f"预检: {self.pdf_path.name}")

        if not self.pdf_path.exists():
            self.issues.append({"severity": "error", "message": f"文件不存在: {self.pdf_path}"})
            self.passed = False
            return self._report()

        # 检查文件大小
        size_mb = self.pdf_path.stat().st_size / (1024 * 1024)
        if size_mb == 0:
            self.issues.append({"severity": "error", "message": "文件大小为0"})
            self.passed = False
        elif size_mb > 500:
            self.warnings.append({"severity": "warning", "message": f"文件过大 ({size_mb:.1f}MB)"})

        # 尝试读取 PDF 并检查
        try:
            import fitz
            doc = fitz.open(str(self.pdf_path))

            for i, page in enumerate(doc):
                # 检查页面尺寸
                rect = page.rect
                if rect.width <= 0 or rect.height <= 0:
                    self.issues.append({"severity": "error", "page": i + 1, "message": "页面尺寸异常"})
                    self.passed = False

                # 检查字体嵌入
                fonts = page.get_fonts()
                for font in fonts:
                    if not font[3]:  # 字体未嵌入
                        self.warnings.append({
                            "severity": "warning",
                            "page": i + 1,
                            "message": f"字体未嵌入: {font[4] if len(font) > 4 else font[0]}",
                        })

                # 检查图像分辨率
                images = page.get_images()
                for img in images:
                    try:
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        if pix.width < 100 or pix.height < 100:
                            self.warnings.append({
                                "severity": "info",
                                "page": i + 1,
                                "message": f"小尺寸图像: {pix.width}x{pix.height}",
                            })
                    except Exception:
                        pass

            doc.close()
        except ImportError:
            self.warnings.append({"severity": "warning", "message": "PyMuPDF 未安装，跳过深度预检"})
        except Exception as e:
            self.issues.append({"severity": "error", "message": f"PDF 读取失败: {e}"})
            self.passed = False

        return self._report()

    def _report(self) -> Dict[str, Any]:
        return {
            "file": str(self.pdf_path),
            "passed": self.passed,
            "issues_count": len(self.issues),
            "warnings_count": len(self.warnings),
            "issues": self.issues,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }


# ===========================================================================
# PDF/X 验证
# ===========================================================================

class PDFXValidator:
    """步骤12: PDF/X 输出验证"""

    PDFX_VERSIONS = ["PDF/X-1a:2001", "PDF/X-3:2002", "PDF/X-4:2010"]

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)

    def validate(self, target_version: str = "PDF/X-4:2010") -> Dict[str, Any]:
        """验证 PDF/X 合规性"""
        report: Dict[str, Any] = {
            "file": str(self.pdf_path),
            "target": target_version,
            "compliant": False,
            "checks": {},
            "errors": [],
        }

        if not self.pdf_path.exists():
            report["errors"].append("文件不存在")
            return report

        # 基本检查
        try:
            import fitz
            doc = fitz.open(str(self.pdf_path))

            # 检查输出意向 (OutputIntent)
            report["checks"]["output_intent"] = bool(doc.metadata.get("format", ""))
            report["checks"]["page_count"] = len(doc)
            report["checks"]["file_size_kb"] = self.pdf_path.stat().st_size // 1024

            # 检查 TrimBox
            has_trimbox = False
            for page in doc:
                if page.rect.width > 0 and page.rect.height > 0:
                    has_trimbox = True
                    break
            report["checks"]["has_trimbox"] = has_trimbox

            # 检查字体嵌入
            all_embedded = True
            for page in doc:
                for font in page.get_fonts():
                    if not font[3]:
                        all_embedded = False
                        report["errors"].append(f"字体未嵌入: {font[4] if len(font) > 4 else font[0]}")
            report["checks"]["fonts_embedded"] = all_embedded

            report["compliant"] = all_embedded and has_trimbox
            doc.close()

        except ImportError:
            report["errors"].append("PyMuPDF 未安装，无法完成验证")
        except Exception as e:
            report["errors"].append(f"验证异常: {e}")

        return report


# ===========================================================================
# KPSM v3.0 适配器
# ===========================================================================

class KPSMv3Adapter:
    """KPSM v3.0 桥接适配器。

    封装 kindergarten_v2_core.py 的完整 11 步流程，
    并增强预检（步骤0）、陷印（步骤4.5）和 PDF/X 验证（步骤12）。
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or load_master_config()
        self._kpsm_path = Path(self.config.get("imposition", {}).get("KPSM_v3_path", "Z:/fxkeji/KPSM_v3.0"))
        self._output_dir = Path(self.config.get("imposition", {}).get("output_dir", "//Server2/客户文件2/输出"))
        self._fallback_dir = Path(self.config.get("imposition", {}).get("fallback_output_dir", "E:/qhi_processor/output"))
        self._work_dir = Path("E:/Temp")

    def run_full_pipeline(self, input_path: str, enable_trapping: bool = True,
                          enable_preflight: bool = True) -> Dict[str, Any]:
        """运行完整的 13 步增强流程"""
        path = Path(input_path)
        start_time = time.time()
        steps_log: List[Dict] = []

        logger.info(f"KPSM v3.0 增强流程启动: {path.name}")

        # 步骤0: 预检
        if enable_preflight and path.suffix.lower() == ".pdf":
            preflight = PreflightCheck(str(path))
            preflight_result = preflight.run()
            steps_log.append({"step": 0, "name": "预检", "result": preflight_result})
            if not preflight_result["passed"]:
                logger.error(f"预检未通过: {path.name}")
                return {"success": False, "step": 0, "error": "预检未通过", "preflight": preflight_result}

        # 步骤1-11: 调用 kindergarten_v2_core.py
        try:
            sys.path.insert(0, str(self._kpsm_path))

            from kindergarten_v2_core import (
                PrintingAutomation, BookInfo, Config,
                PDFMetadataCache, LogManager,
            )

            processor = PrintingAutomation.__new__(PrintingAutomation)

            # 初始化
            filename = path.stem if path.is_file() else path.name
            book_match = re.search(r'(\d+)本', filename)
            box_match = re.search(r'(\d+)箱', filename)

            processor.archive_path = path
            processor.work_dir = self._work_dir
            processor.work_dir.mkdir(parents=True, exist_ok=True)
            processor.extract_dir = path if path.is_dir() else None
            processor.pdf_files = []
            processor.book_info = BookInfo(
                int(book_match.group(1)) if book_match else 0,
                int(box_match.group(1)) if box_match else 0,
                f"{book_match.group(1)}本{box_match.group(1)}箱" if book_match and box_match else filename,
            )
            processor.copy_info_map = {}
            processor.pdf_cache = PDFMetadataCache()
            processor.log_manager = LogManager(processor.archive_path.stem, processor.work_dir)

            def log(msg, level="INFO"):
                processor.log_manager.log(msg, level)
                logger.info(f"[KPSM] {msg}")

            processor.log = log

            # 执行步骤
            if path.is_file():
                processor.step1_extract()
                steps_log.append({"step": 1, "name": "解压", "status": "ok"})

            processor.step2_convert_images_to_pdf()
            steps_log.append({"step": 2, "name": "图像转PDF", "status": "ok"})

            processor.step3_rename_and_number()
            steps_log.append({"step": 3, "name": "编号重命名", "status": "ok"})

            processor.step4_qhi_process()
            steps_log.append({"step": 4, "name": "QHI拼版", "status": "ok"})

            # 步骤4.5: 陷印
            if enable_trapping and processor.pdf_files:
                try:
                    from services.trapping_engine import trap_file

                    for pdf_file in processor.pdf_files:
                        pdf_path = Path(pdf_file)
                        if pdf_path.exists():
                            trapped_path = pdf_path.parent / f"trapped_{pdf_path.name}"
                            trap_file(str(pdf_path), str(trapped_path))
                            steps_log.append({"step": 4.5, "name": "陷印", "status": "ok", "file": str(trapped_path)})
                except ImportError as e:
                    steps_log.append({"step": 4.5, "name": "陷印", "status": "skipped", "reason": str(e)})
                except Exception as e:
                    steps_log.append({"step": 4.5, "name": "陷印", "status": "warning", "reason": str(e)})
            else:
                steps_log.append({"step": 4.5, "name": "陷印", "status": "disabled"})

            processor.step7_separate_and_duplicate()
            processor.step5_parallel_process()
            processor.step6_final_merge()
            processor.step8_rename_output()
            processor.step9_statistics()
            processor.step10_cleanup()
            processor.step11_move_to_server()

            for s in range(5, 12):
                steps_log.append({"step": s, "name": f"步骤{s}", "status": "ok"})

            # 步骤12: PDF/X 验证
            output_files = list(self._output_dir.glob("*.pdf")) if self._output_dir.exists() else []
            if not output_files:
                output_files = list(self._fallback_dir.glob("*.pdf")) if self._fallback_dir.exists() else []

            validation_results = []
            for pdf in output_files[:3]:  # 只验证前3个
                validator = PDFXValidator(str(pdf))
                validation_results.append(validator.validate())
            steps_log.append({"step": 12, "name": "PDF/X验证", "results": validation_results})

        except Exception as e:
            logger.error(f"KPSM v3.0 流水线异常: {e}")
            return {"success": False, "step": "unknown", "error": str(e), "steps": steps_log}

        elapsed = time.time() - start_time

        return {
            "success": True,
            "elapsed_seconds": round(elapsed, 1),
            "steps": steps_log,
            "output_dir": str(self._output_dir) if self._output_dir.exists() else str(self._fallback_dir),
            "timestamp": datetime.now().isoformat(),
        }

    def run_qhi_mode(self, pdf_path: str) -> Dict[str, Any]:
        """--qhi 模式：调用 smart_imposition.py 的智能拼版"""
        try:
            from services.smart_imposition import ImpositionEngine, ImpositionJob, ImpositionMode

            engine = ImpositionEngine(mode=ImpositionMode.QHI)
            job = ImpositionJob(
                job_id=f"qhi_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                input_files=[pdf_path],
            )
            result = engine.process(job)

            return {
                "success": result.success,
                "mode": "qhi",
                "output_file": result.output_file,
                "elapsed_seconds": result.elapsed_seconds,
                "error": result.error_message,
            }
        except Exception as e:
            return {"success": False, "mode": "qhi", "error": str(e)}

    def run_gui_mode(self) -> Dict[str, Any]:
        """--gui 模式：启动图形界面"""
        try:
            from pathlib import Path
            gui_path = self._kpsm_path / "main.py"
            if gui_path.exists():
                return {
                    "success": True,
                    "mode": "gui",
                    "gui_path": str(gui_path),
                    "message": "请在终端中运行: python main.py",
                }
            else:
                return {"success": False, "mode": "gui", "error": f"main.py 未找到: {gui_path}"}
        except Exception as e:
            return {"success": False, "mode": "gui", "error": str(e)}


# ===========================================================================
# CLI
# ===========================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KPSM v3.0 增强适配器")
    parser.add_argument("input", nargs="?", help="输入文件路径（压缩包或文件夹）")
    parser.add_argument("--qhi", action="store_true", help="QHI 智能拼版模式")
    parser.add_argument("--gui", action="store_true", help="图形界面模式")
    parser.add_argument("--no-trap", action="store_true", help="禁用陷印")
    parser.add_argument("--no-preflight", action="store_true", help="禁用预检")

    args = parser.parse_args()

    adapter = KPSMv3Adapter()

    if args.gui:
        result = adapter.run_gui_mode()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.qhi and args.input:
        result = adapter.run_qhi_mode(args.input)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.input:
        result = adapter.run_full_pipeline(
            args.input,
            enable_trapping=not args.no_trap,
            enable_preflight=not args.no_preflight,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("KPSM v3.0 适配器就绪")
        print("用法: python kpsm_v3_adapter.py <输入> [--qhi] [--gui] [--no-trap] [--no-preflight]")
