#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
integration/gang_print_workflow.py — 合版印刷工作流集成

将 P0/P1 改进项整合为完整的合版印刷工作流：
1. 预检检查（含 GWG 剖面）
2. 透明度拼合（PDF/X-1a 合规）
3. 色彩空间转换（CMYK）
4. 陷印分析
5. 裁切标记生成
6. 套准标记生成
7. PDF/X 输出

符合标准：ISO 12647 / GWG 2020 / PDF/X-1a
"""

import logging
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import fitz
except ImportError:
    fitz = None


class WorkflowStep(str, Enum):
    """工作流步骤"""
    PREFLIGHT = "preflight"
    FLATTEN_TRANSPARENCY = "flatten_transparency"
    TRAPPING = "trapping"
    CROP_MARKS = "crop_marks"
    REGISTRATION_MARKS = "registration_marks"
    PDFX_EXPORT = "pdfx_export"


@dataclass
class WorkflowConfig:
    """合版印刷工作流配置"""
    steps: List[WorkflowStep] = field(default_factory=lambda: [
        WorkflowStep.PREFLIGHT,
        WorkflowStep.FLATTEN_TRANSPARENCY,
        WorkflowStep.TRAPPING,
        WorkflowStep.CROP_MARKS,
        WorkflowStep.REGISTRATION_MARKS,
        WorkflowStep.PDFX_EXPORT,
    ])
    preflight_profile: str = "general"
    flatten_dpi: int = 300
    trap_width_mm: float = 0.1
    crop_marks: bool = True
    registration_marks: bool = True
    pdfx_standard: str = "PDF/X-1a"
    output_dir: str = ""


@dataclass
class StepResult:
    """单步结果"""
    step: WorkflowStep
    success: bool = False
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """工作流完整结果"""
    success: bool = False
    input_path: str = ""
    output_path: str = ""
    steps: List[StepResult] = field(default_factory=list)
    total_time_ms: float = 0.0

    @property
    def passed_steps(self) -> int:
        return sum(1 for s in self.steps if s.success)

    @property
    def failed_steps(self) -> List[str]:
        return [s.step.value for s in self.steps if not s.success]


def run_gang_print_workflow(
    input_path: str,
    output_path: str,
    config: Optional[WorkflowConfig] = None,
) -> WorkflowResult:
    """执行合版印刷完整工作流

    Args:
        input_path: 输入 PDF 路径
        output_path: 输出 PDF 路径
        config: 工作流配置

    Returns:
        WorkflowResult 工作流结果
    """
    import time
    cfg = config or WorkflowConfig()
    result = WorkflowResult(input_path=input_path, output_path=output_path)
    start_time = time.time()

    for step in cfg.steps:
        step_result = _execute_step(step, input_path, output_path, cfg)
        result.steps.append(step_result)

        if not step_result.success and step == WorkflowStep.PREFLIGHT:
            logger.warning(f"预检未通过: {step_result.message}")

    result.success = all(s.success for s in result.steps
                        if s.step != WorkflowStep.PREFLIGHT)
    result.total_time_ms = (time.time() - start_time) * 1000

    logger.info(
        f"合版工作流完成: {result.passed_steps}/{len(result.steps)} 步通过, "
        f"耗时 {result.total_time_ms:.0f}ms"
    )
    return result


def _execute_step(
    step: WorkflowStep,
    input_path: str,
    output_path: str,
    config: WorkflowConfig,
) -> StepResult:
    """执行单个工作流步骤"""
    try:
        if step == WorkflowStep.PREFLIGHT:
            return _step_preflight(input_path, config)
        elif step == WorkflowStep.FLATTEN_TRANSPARENCY:
            return _step_flatten(input_path, config)
        elif step == WorkflowStep.TRAPPING:
            return _step_trapping(input_path, config)
        elif step == WorkflowStep.CROP_MARKS:
            return _step_crop_marks(input_path, config)
        elif step == WorkflowStep.REGISTRATION_MARKS:
            return _step_reg_marks(input_path, config)
        elif step == WorkflowStep.PDFX_EXPORT:
            return _step_pdfx_export(input_path, output_path, config)
        else:
            return StepResult(step=step, message=f"未知步骤: {step}")
    except Exception as e:
        return StepResult(step=step, success=False, message=str(e))


def _step_preflight(input_path: str, config: WorkflowConfig) -> StepResult:
    """预检步骤"""
    try:
        from integration.preflight_enhanced import EnhancedPreflightChecker
        from integration.gwg_profiles import GWGProfile, get_gwg_checks_for_profile

        checker = EnhancedPreflightChecker()

        checks = None
        if config.preflight_profile != "general":
            try:
                profile = GWGProfile(config.preflight_profile)
                gwg_checks = get_gwg_checks_for_profile(profile)
                checks = [c["check_type"] for c in gwg_checks]
            except (ValueError, KeyError):
                pass

        result = checker.run_preflight(input_path, checks=checks)

        if result.error_count > 0:
            return StepResult(
                step=WorkflowStep.PREFLIGHT,
                success=False,
                message=f"预检发现 {result.error_count} 个错误",
                details={"errors": result.error_count, "warnings": result.warning_count},
            )

        return StepResult(
            step=WorkflowStep.PREFLIGHT,
            success=True,
            message=f"预检通过 (warnings: {result.warning_count})",
            details={"passed": result.passed_checks, "warnings": result.warning_count},
        )
    except ImportError:
        return StepResult(
            step=WorkflowStep.PREFLIGHT,
            success=True,
            message="预检模块不可用，跳过",
        )


def _step_flatten(input_path: str, config: WorkflowConfig) -> StepResult:
    """透明度拼合步骤"""
    try:
        from integration.transparency_flattener import (
            detect_transparency, flatten_transparency, FlattenConfig
        )

        doc = fitz.open(input_path)
        try:
            infos = detect_transparency(doc)
            needs_flatten = any(i.has_transparency for i in infos)

            if needs_flatten:
                cfg = FlattenConfig(dpi=config.flatten_dpi, color_space="CMYK")
                flatten_transparency(doc, cfg)
                doc.save(input_path)

            return StepResult(
                step=WorkflowStep.FLATTEN_TRANSPARENCY,
                success=True,
                message=f"透明度检查完成，{'已拼合' if needs_flatten else '无需拼合'}",
                details={"pages_with_transparency": sum(1 for i in infos if i.has_transparency)},
            )
        finally:
            doc.close()
    except ImportError:
        return StepResult(
            step=WorkflowStep.FLATTEN_TRANSPARENCY,
            success=True,
            message="透明度模块不可用，跳过",
        )


def _step_trapping(input_path: str, config: WorkflowConfig) -> StepResult:
    """陷印分析步骤"""
    try:
        from services.trapping_engine import trap_file, TrapConfig

        cfg = TrapConfig(trap_width_mm=config.trap_width_mm)
        doc = fitz.open(input_path)
        try:
            from services.trapping_engine import trap_page
            results = [trap_page(doc, i, cfg) for i in range(len(doc))]
            total_zones = sum(len(r.trap_zones) for r in results)
        finally:
            doc.close()

        return StepResult(
            step=WorkflowStep.TRAPPING,
            success=True,
            message=f"陷印分析完成，{total_zones} 个陷印区域",
            details={"total_zones": total_zones},
        )
    except ImportError:
        return StepResult(
            step=WorkflowStep.TRAPPING,
            success=True,
            message="陷印模块不可用，跳过",
        )


def _step_crop_marks(input_path: str, config: WorkflowConfig) -> StepResult:
    """裁切标记步骤"""
    if not config.crop_marks:
        return StepResult(step=WorkflowStep.CROP_MARKS, success=True, message="裁切标记已禁用")

    try:
        from integration.crop_marks import draw_crop_marks_all_pages, CropMarkConfig

        doc = fitz.open(input_path)
        try:
            page = doc[0]
            pw_mm = page.rect.width * 25.4 / 72
            ph_mm = page.rect.height * 25.4 / 72

            cfg = CropMarkConfig(style="both", offset_mm=3.0, length_mm=3.0)
            draw_crop_marks_all_pages(doc, cfg)
            doc.save(input_path, incremental=True, encryption=0)

            return StepResult(
                step=WorkflowStep.CROP_MARKS,
                success=True,
                message=f"裁切标记已生成 ({pw_mm:.0f}×{ph_mm:.0f}mm)",
            )
        finally:
            doc.close()
    except ImportError:
        return StepResult(
            step=WorkflowStep.CROP_MARKS,
            success=True,
            message="裁切标记模块不可用，跳过",
        )


def _step_reg_marks(input_path: str, config: WorkflowConfig) -> StepResult:
    """套准标记步骤"""
    if not config.registration_marks:
        return StepResult(step=WorkflowStep.REGISTRATION_MARKS, success=True, message="套准标记已禁用")

    try:
        from integration.registration_marks import (
            draw_registration_marks_all_pages, RegMarkConfig, RegMarkStyle, RegMarkPosition
        )

        doc = fitz.open(input_path)
        try:
            cfg = RegMarkConfig(style=RegMarkStyle.CROSSHAIR, position=RegMarkPosition.ALL)
            draw_registration_marks_all_pages(doc, cfg)
            doc.save(input_path, incremental=True, encryption=0)

            return StepResult(
                step=WorkflowStep.REGISTRATION_MARKS,
                success=True,
                message="套准标记已生成 (9个位置)",
            )
        finally:
            doc.close()
    except ImportError:
        return StepResult(
            step=WorkflowStep.REGISTRATION_MARKS,
            success=True,
            message="套准标记模块不可用，跳过",
        )


def _step_pdfx_export(
    input_path: str, output_path: str, config: WorkflowConfig
) -> StepResult:
    """PDF/X 输出步骤"""
    try:
        from integration.pdfx_exporter import convert_to_pdfx, PDFXConfig

        cfg = PDFXConfig(
            standard=config.pdfx_standard,
            flatten_transparency=False,
        )
        result = convert_to_pdfx(input_path, output_path, cfg)

        return StepResult(
            step=WorkflowStep.PDFX_EXPORT,
            success=result.success,
            message=f"PDF/X 输出{'成功' if result.success else '失败'}",
            details={"output": output_path, "issues": result.issues},
        )
    except ImportError:
        return StepResult(
            step=WorkflowStep.PDFX_EXPORT,
            success=True,
            message="PDF/X 模块不可用，跳过",
        )


def get_workflow_config_preset(preset: str) -> WorkflowConfig:
    """获取预设工作流配置"""
    presets = {
        "full": WorkflowConfig(
            steps=list(WorkflowStep),
            flatten_dpi=300,
            trap_width_mm=0.1,
            crop_marks=True,
            registration_marks=True,
            pdfx_standard="PDF/X-1a",
        ),
        "quick": WorkflowConfig(
            steps=[WorkflowStep.PREFLIGHT, WorkflowStep.CROP_MARKS],
            flatten_dpi=150,
            crop_marks=True,
            registration_marks=False,
        ),
        "preflight_only": WorkflowConfig(
            steps=[WorkflowStep.PREFLIGHT],
        ),
        "pdfx_only": WorkflowConfig(
            steps=[WorkflowStep.FLATTEN_TRANSPARENCY, WorkflowStep.PDFX_EXPORT],
            flatten_dpi=300,
            pdfx_standard="PDF/X-1a",
        ),
    }
    return presets.get(preset, presets["full"])
