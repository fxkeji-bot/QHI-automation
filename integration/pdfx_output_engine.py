#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/pdfx_output_engine.py - PDF/X 标准输出发动机

将任意 PDF 转换为 PDF/X-1a:2001、PDF/X-3:2002、PDF/X-4、PDF/A、PDF/UA 等
标准格式的完整引擎，基于 Enfocus PitStop Server 执行。

典型流程：
  1. 预检源文件（PreflightEnhanced），记录初始问题列表
  2. 根据目标标准生成 PitStop 变量参数（_build_pitstop_params）
  3. 调用 pitstop_service.run_with_variables() 执行转换 Action List
  4. 验证输出文件（PreflightEnhanced），返回结果

集成点：
  - integration.pitstop_service.PitStopService
  - integration.preflight_enhanced.PreflightEnhanced
  - integration.pdfx_profiles.{PdfxStandard, PdfxProfileConfig, get_pdfx_profile}
"""
from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple, Any

from utils.logger import get_logger

# ── 延迟导入（避免循环依赖）────────────────────────────────────────────────────
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_parent))

from integration.pdfx_profiles import (
    PdfxStandard,
    PdfxProfileConfig,
    get_pdfx_profile,
)
from integration.pitstop_service import PitStopService
from integration.preflight_enhanced import EnhancedPreflightChecker as PreflightEnhanced, PreflightResult

logger = get_logger(__name__)


# ── 结果数据结构 ─────────────────────────────────────────────────────────────

class PdfxResult:
    """PDF/X 转换结果。

    Attributes:
        success: 转换是否成功。
        standard: 目标 PDF/X 标准。
        input_file: 源 PDF 路径。
        output_file: 输出 PDF 路径。
        violations_fixed: 自动修复的问题数量。
        warnings: 警告信息列表。
        errors: 错误信息列表。
        log_path: 详细日志文件路径。
        elapsed_seconds: 转换耗时（秒）。
    """

    def __init__(
        self,
        success: bool,
        standard: PdfxStandard,
        input_file: str,
        output_file: str,
        violations_fixed: int = 0,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        log_path: str = "",
        elapsed_seconds: float = 0.0,
    ):
        self.success = success
        self.standard = standard
        self.input_file = input_file
        self.output_file = output_file
        self.violations_fixed = violations_fixed
        self.warnings: List[str] = warnings or []
        self.errors: List[str] = errors or []
        self.log_path = log_path
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "standard": self.standard.value,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "violations_fixed": self.violations_fixed,
            "warnings": self.warnings,
            "errors": self.errors,
            "log_path": self.log_path,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }

    def __repr__(self) -> str:
        status = "成功" if self.success else "失败"
        return (
            f"PdfxResult({status}, standard={self.standard.value}, "
            f"violations_fixed={self.violations_fixed}, "
            f"elapsed={self.elapsed_seconds:.1f}s)"
        )


class ValidationResult:
    """PDF/X 标准验证结果。

    Attributes:
        is_compliant: 是否符合目标标准。
        standard: 验证使用的标准。
        checks_passed: 通过的检查项数量。
        checks_failed: 失败的检查项数量。
        violations: 问题列表（字典格式）。
    """

    def __init__(
        self,
        is_compliant: bool,
        standard: PdfxStandard,
        checks_passed: int = 0,
        checks_failed: int = 0,
        violations: Optional[List[Dict]] = None,
    ):
        self.is_compliant = is_compliant
        self.standard = standard
        self.checks_passed = checks_passed
        self.checks_failed = checks_failed
        self.violations: List[Dict] = violations or []

    def to_dict(self) -> Dict:
        return {
            "is_compliant": self.is_compliant,
            "standard": self.standard.value,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "violations": self.violations,
        }

    def __repr__(self) -> str:
        status = "合规" if self.is_compliant else "不合规"
        return (
            f"ValidationResult({status}, "
            f"passed={self.checks_passed}, failed={self.checks_failed})"
        )


# ── 核心引擎 ─────────────────────────────────────────────────────────────────

class PdfxOutputEngine:
    """PDF/X 标准输出发动机。

    基于 Enfocus PitStop Server 和 PreflightEnhanced，将普通 PDF
    转换为符合 PDF/X、PDF/A、PDF/UA 等标准的输出文件。

    支持：
      - 单文件转换 / 批量转换
      - 6 种标准（PDF/X-1a/3/4, PDF/A-1b/2b/3b, PDF/UA-1）
      - 自动 ICC Profile 嵌入
      - 前后预检验证
      - 详细日志记录

    Usage:
        engine = PdfxOutputEngine()
        result = engine.convert_to_pdfx("input.pdf", "output.pdf", PdfxStandard.X_4)

        results = engine.batch_convert(
            files=["a.pdf", "b.pdf"],
            output_dir="output/",
            profile=PdfxStandard.X_3_2002,
        )
    """

    # 默认 Action List 名称（需在 PitStop 中预置，或在 resources/ 下提供 .eal）
    DEFAULT_ACTION_LIST = "pdfx_conversion.eal"

    def __init__(self, pitstop_service: Optional[PitStopService] = None):
        """初始化 PDF/X 输出发动机。

        Args:
            pitstop_service: PitStopService 实例。None 则自动创建（自动检测 CLI/Server）。
        """
        self._pitstop = pitstop_service or PitStopService()

    # ── 公共属性 ─────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """检查 PitStop 是否可用（CLI 或 Server 模式）。"""
        return self._pitstop.is_available

    # ── 核心转换方法 ─────────────────────────────────────────────────────────

    def convert_to_pdfx(
        self,
        input_pdf: str,
        output_pdf: str,
        profile: PdfxStandard = PdfxStandard.X_4,
        icc_profile_path: Optional[str] = None,
        conditions: Optional[Dict[str, str]] = None,
    ) -> PdfxResult:
        """将普通 PDF 转换为指定 PDF/X 标准格式。

        完整流程：
          1. 验证输入文件存在
          2. 获取目标标准配置（PdfxProfileConfig）
          3. 用 PreflightEnhanced 检查源文件问题（before check）
          4. 构建 PitStop 变量参数并执行 Action List
          5. 验证输出文件是否符合目标标准（after check）
          6. 返回 PdfxResult

        Args:
            input_pdf: 源 PDF 文件路径。
            output_pdf: 输出 PDF 文件路径。
            profile: 目标 PDF/X 标准（默认 PDF/X-4）。
            icc_profile_path: 可选 ICC Profile 文件路径（覆盖配置中的 output_intent）。
            conditions: 可选额外 PitStop/EVS 变量（字典）。

        Returns:
            PdfxResult: 转换结果，包含成功状态、修复数量、警告/错误信息。
        """
        start_time = time.time()
        warnings: List[str] = []
        errors: List[str] = []
        violations_fixed = 0
        log_path = ""

        # Step 1: 验证输入
        if not os.path.exists(input_pdf):
            errors.append(f"输入文件不存在: {input_pdf}")
            return PdfxResult(
                success=False,
                standard=profile,
                input_file=input_pdf,
                output_file="",
                errors=errors,
                elapsed_seconds=time.time() - start_time,
            )

        # Step 2: 获取配置
        config = get_pdfx_profile(profile)

        # 允许 ICC Profile 路径覆盖
        if icc_profile_path and os.path.exists(icc_profile_path):
            config.output_intent = os.path.basename(icc_profile_path)
            config.extra_params["ICCProfilePath"] = icc_profile_path

        # 额外条件覆盖
        if conditions:
            config.extra_params.update(conditions)

        logger.info(
            "开始 PDF/X 转换: %s → %s (标准: %s)",
            Path(input_pdf).name,
            profile.value,
            config.output_intent,
        )

        # Step 3: 预检源文件（记录初始问题）
        preflight_issues_before: List[Dict] = []
        try:
            checker = PreflightEnhanced()
            checker.pdfx_standard = config.compliance
            checker.max_ink_coverage = config.max_ink_coverage
            checker.min_dpi = config.min_dpi
            checker.required_bleed_mm = config.require_bleed

            pre_result: PreflightResult = checker.run_preflight(input_pdf)
            for issue in pre_result.issues:
                preflight_issues_before.append(issue.to_dict())
            if not pre_result.passed:
                warnings.append(f"源文件预检发现问题: {pre_result.summary}")
        except Exception as e:
            warnings.append(f"预检步骤跳过（原因: {e}）")
            logger.warning("预检步骤失败: %s", e)

        # Step 4: 生成 PitStop 变量参数
        pitstop_vars = self._build_pitstop_params(config)

        # Step 5: 执行转换
        if self._pitstop.is_available:
            try:
                # 使用 run_with_variables 注入 ICC/Compliance 等变量
                ok, pitstop_log = self._pitstop.run_with_variables(
                    input_pdf=input_pdf,
                    action_list=self.DEFAULT_ACTION_LIST,
                    output_pdf=output_pdf,
                    variables=pitstop_vars,
                )

                # 解析 PitStop 日志
                if not ok:
                    status = pitstop_log.get("status", "error")
                    pitstop_errors = pitstop_log.get("errors", [])
                    errors.extend(pitstop_errors if isinstance(pitstop_errors, list) else [str(pitstop_errors)])
                    if status == "unavailable":
                        errors.append("PitStop 服务不可用")
                else:
                    violations_fixed = pitstop_log.get("fixes_applied", 0)
                    status = pitstop_log.get("status", "passed")
                    corrections = pitstop_log.get("corrections", [])
                    if corrections:
                        warnings.extend(corrections[:10])  # 最多记录10条修正

                    # 保存日志
                    if pitstop_log.get("raw_output"):
                        log_path = self._save_log(
                            input_pdf,
                            pitstop_log,
                            f"pdfx_{profile.value.replace(':', '_').replace('/', '_')}",
                        )

                logger.info(
                    "PitStop 执行完成: status=%s, fixes=%d",
                    status,
                    violations_fixed,
                )

            except Exception as e:
                errors.append(f"PitStop 执行异常: {e}")
                logger.error("PitStop 执行异常: %s", e)
        else:
            # PitStop 不可用时，复制文件并记录警告（不抛异常）
            errors.append("PitStop 不可用，文件已复制但未进行 PDF/X 转换")
            logger.warning("PitStop 不可用，使用 fallback 复制模式")
            try:
                import shutil
                os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
                shutil.copy2(input_pdf, output_pdf)
            except Exception as copy_err:
                errors.append(f"文件复制失败: {copy_err}")

        # Step 6: 验证输出（如果输出文件存在）
        output_exists = os.path.exists(output_pdf)
        if output_exists and not errors:
            try:
                val_result = self.validate_output(output_pdf, profile)
                if not val_result.is_compliant:
                    warnings.append(
                        f"输出文件验证未通过: {val_result.checks_failed} 项检查失败"
                    )
                    for v in val_result.violations[:5]:
                        warnings.append(f"  - {v.get('message', str(v))}")
            except Exception as e:
                warnings.append(f"输出验证步骤跳过（原因: {e}）")

        elapsed = time.time() - start_time
        result = PdfxResult(
            success=output_exists and not errors,
            standard=profile,
            input_file=input_pdf,
            output_file=output_pdf if output_exists else "",
            violations_fixed=violations_fixed,
            warnings=warnings,
            errors=errors,
            log_path=log_path,
            elapsed_seconds=elapsed,
        )

        logger.info(
            "PDF/X 转换完成: %s, violations_fixed=%d, elapsed=%.2fs",
            "成功" if result.success else "失败",
            violations_fixed,
            elapsed,
        )
        return result

    def batch_convert(
        self,
        files: List[str],
        output_dir: str,
        profile: PdfxStandard = PdfxStandard.X_4,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[PdfxResult]:
        """批量将多个 PDF 文件转换为指定 PDF/X 标准。

        Args:
            files: 源 PDF 文件路径列表。
            output_dir: 输出目录（自动创建）。
            profile: 目标 PDF/X 标准。
            progress_callback: 进度回调，签名为 (current_index, total, filename)。

        Returns:
            List[PdfxResult]: 每个文件的转换结果列表。
        """
        if not files:
            return []

        # 确保输出目录存在
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results: List[PdfxResult] = []
        total = len(files)

        logger.info("开始批量 PDF/X 转换: 共 %d 个文件, 标准=%s", total, profile.value)

        for idx, input_path in enumerate(files, start=1):
            filename = Path(input_path).name
            output_path = str(out_dir / f"{Path(input_path).stem}_x{Path(input_path).suffix}")

            if progress_callback:
                try:
                    progress_callback(idx, total, filename)
                except Exception as cb_err:
                    logger.warning("进度回调异常: %s", cb_err)

            result = self.convert_to_pdfx(input_path, output_path, profile)
            results.append(result)

            logger.info(
                "[%d/%d] %s → %s",
                idx,
                total,
                filename,
                "成功" if result.success else "失败",
            )

        success_count = sum(1 for r in results if r.success)
        logger.info(
            "批量转换完成: %d/%d 成功",
            success_count,
            total,
        )
        return results

    def validate_output(
        self,
        pdf_path: str,
        profile: PdfxStandard,
    ) -> ValidationResult:
        """验证 PDF 文件是否符合指定 PDF/X 标准。

        使用 PreflightEnhanced 执行合规性检查。

        Args:
            pdf_path: PDF 文件路径。
            profile: 目标 PDF/X 标准。

        Returns:
            ValidationResult: 验证结果。
        """
        if not os.path.exists(pdf_path):
            return ValidationResult(
                is_compliant=False,
                standard=profile,
                checks_failed=1,
                violations=[{"message": f"文件不存在: {pdf_path}"}],
            )

        try:
            config = get_pdfx_profile(profile)
            checker = PreflightEnhanced()
            checker.pdfx_standard = config.compliance
            checker.max_ink_coverage = config.max_ink_coverage
            checker.min_dpi = config.min_dpi
            checker.required_bleed_mm = config.require_bleed

            pre_result: PreflightResult = checker.run_preflight(pdf_path)

            # 将 PreflightResult 映射为 ValidationResult
            violations = [issue.to_dict() for issue in pre_result.issues]
            # 只统计 ERROR 和 CRITICAL 为失败
            failed_count = pre_result.error_count + pre_result.critical_count
            # 排除 INFO 级别（PDF/X 未声明本身不是错误）
            is_compliant = failed_count == 0

            return ValidationResult(
                is_compliant=is_compliant,
                standard=profile,
                checks_passed=pre_result.passed_checks,
                checks_failed=failed_count,
                violations=violations,
            )

        except Exception as e:
            logger.error("输出验证异常: %s", e)
            return ValidationResult(
                is_compliant=False,
                standard=profile,
                checks_failed=1,
                violations=[{"message": f"验证异常: {e}"}],
            )

    # ── 内部工具方法 ─────────────────────────────────────────────────────────

    def _build_pitstop_params(self, config: PdfxProfileConfig) -> Dict[str, str]:
        """根据配置构建 PitStop/EVS 变量字典。

        这些变量在 PitStop Action List 中通过 $var(name)$ 形式引用。

        Args:
            config: PDF/X 配置文件。

        Returns:
            Dict[str, str]: 变量名→值的字典。
        """
        vars_: Dict[str, str] = {
            # 输出意图
            "OutputIntent": config.output_intent,
            "ICCProfile": config.output_intent,
            # 合规标准
            "Compliance": config.compliance,
            "PDFXStandard": config.compliance,
            # 条件标识符
            "OutputConditionIdentifier": config.icc_condition,
            "RegistryName": config.registry_name,
            # 图像质量
            "MinDPI": str(config.min_dpi),
            "MaxInkCoverage": str(config.max_ink_coverage),
            # 出血位
            "RequireBleed": str(config.require_bleed),
            # 色彩转换策略
            "ConvertRGBToCMYK": "1" if config.convert_rgb_to_cmyk else "0",
            "ConvertSpotToCMYK": "1" if config.convert_spot_to_cmyk else "0",
        }

        # 透明度扁平化（PDF/X-1a 必须开启）
        if config.remove_transparency:
            vars_["FlattenTransparency"] = "1"
            vars_["RemoveTransparency"] = "1"
        else:
            vars_["FlattenTransparency"] = "0"
            vars_["RemoveTransparency"] = "0"

        # 嵌入 ICC Profile
        vars_["EmbedICC"] = "1" if config.embed_icc else "0"

        # 合并额外参数
        vars_.update(config.extra_params)

        return vars_

    def _generate_action_list_config(self, config: PdfxProfileConfig) -> str:
        """生成 PitStop 兼容的转换参数说明（供调试/文档使用）。

        返回人类可读的参数摘要，非实际 PitStop 调用参数。

        Args:
            config: PDF/X 配置文件。

        Returns:
            str: 参数摘要字符串。
        """
        lines = [
            f"PDF/X Standard: {config.compliance}",
            f"Output Intent: {config.output_intent} ({config.icc_condition})",
            f"Registry: {config.registry_name}",
            f"ICC Embed: {config.embed_icc}",
            f"RGB→CMYK: {config.convert_rgb_to_cmyk}",
            f"Spot→CMYK: {config.convert_spot_to_cmyk}",
            f"Flatten Transparency: {config.remove_transparency}",
            f"Max Ink Coverage: {config.max_ink_coverage}%",
            f"Min Image DPI: {config.min_dpi}",
            f"Required Bleed: {config.require_bleed}mm",
        ]
        return "\n".join(lines)

    def _save_log(
        self,
        input_pdf: str,
        pitstop_log: Dict,
        prefix: str = "pdfx",
    ) -> str:
        """将 PitStop 日志保存到文件。

        Args:
            input_pdf: 源文件路径（用于命名）。
            pitstop_log: PitStop 返回的日志字典。
            prefix: 日志文件名前缀。

        Returns:
            str: 日志文件路径。
        """
        try:
            from datetime import datetime
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = Path(input_pdf).stem
            log_path = str(log_dir / f"{prefix}_{base_name}_{timestamp}.json")

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(pitstop_log, f, indent=2, ensure_ascii=False)

            return log_path
        except Exception as e:
            logger.warning("保存日志失败: %s", e)
            return ""
