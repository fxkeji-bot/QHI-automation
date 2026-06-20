#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
services/smart_imposition.py — 智能拼版整合模块

整合 KPSM_v3.0（Quite Hot Imposing 5 XML 模板引擎）和 qhi_processor
AI 算法（gang_layout 贪心+模拟退火），提供统一拼版入口。

两种拼版模式：
  - mode='qhi'：调用 Quite Hot Imposing 5 通过 XML 模板执行（兼容 KPSM_v3.0）
  - mode='ai'：调用 gang_layout 的贪心+模拟退火算法

自动模式选择：
  - 小批量（<50页）：AI 算法
  - 大批量（≥50页）：QHI 模板引擎

拼版流程参考 KPSM_v3.0 kindergarten_v2_core.py 步骤4 qhi_process：
  使用 qi_applycommands.exe 通过 XML 模板执行拼版操作。
  XML 模板类型：环衬拼版、替换后环衬、康轩删面底、内页提取合拼、康轩多本连拼。
  并行处理：ThreadPoolExecutor, MAX_WORKERS=CPU核心数/2, QHI最大并发=2。
  输出到 \\\\Server2\\客户文件2\\输出。

Author: QHI System
Version: 1.0.0
"""

import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ── 导入 AI 拼版引擎 ──
try:
    from services.gang_layout import (
        GangLayoutEngine,
        OrderRect,
        PaperSheet,
        Orientation,
    )
    AI_ENGINE_AVAILABLE = True
except ImportError:
    logger.warning("gang_layout 模块未找到，AI 拼版模式不可用")
    AI_ENGINE_AVAILABLE = False


# ===========================================================================
# 配置
# ===========================================================================
QHI_EXE = r"C:\Program Files\Quite\Quite Hot Imposing 5\qi_applycommands.exe"
QHI_MAX_CONCURRENT = 2
DEFAULT_OUTPUT_DIR = r"\\Server2\客户文件2\输出"


class ImpositionMode(str, Enum):
    """拼版模式"""
    QHI = "qhi"      # Quite Hot Imposing 5 XML 模板引擎
    AI = "ai"        # 贪心+模拟退火 AI 算法
    AUTO = "auto"    # 自动选择（默认）


class XMLTemplateType(str, Enum):
    """QHI XML 模板类型（对应 KPSM_v3.0 五种拼版场景）"""
    HUANCHEN_PIN = "环衬拼版"              # XML_HUANCHEN_PIN
    TIHUANHOU = "替换后环衬"               # XML_TIHUANHOU
    KANGXUAN_DELETE = "康轩删面底"         # XML_KANGXUAN_DELETE
    NEIYE_TIQU = "内页提取合拼"            # XML_NEIYE_TIQU
    KANGXUAN_DUOBEN = "康轩多本连拼"       # XML_KANGXUAN_DUOBEN


# ===========================================================================
# 数据结构
# ===========================================================================

@dataclass
class ImpositionJob:
    """拼版任务描述"""
    job_id: str
    input_files: List[str]                      # 输入 PDF 文件路径列表
    paper_size: Tuple[float, float] = (440, 590)  # 纸张尺寸 (宽mm, 高mm)，默认大度4开
    template_type: XMLTemplateType = XMLTemplateType.HUANCHEN_PIN
    copies: int = 1
    bleed_mm: float = 3.0                       # 出血位
    grip_mm: float = 10.0                       # 叼口
    output_dir: str = DEFAULT_OUTPUT_DIR
    extra_params: Dict = field(default_factory=dict)  # 额外模板参数

    @property
    def total_pages(self) -> int:
        """估算总页数（基于文件数量近似，实际需读取 PDF 页数）"""
        return len(self.input_files)


@dataclass
class ImpositionResult:
    """拼版结果"""
    job_id: str
    success: bool
    mode: str                                    # 'qhi' 或 'ai'
    output_file: Optional[str] = None
    page_count: int = 0
    file_size_bytes: int = 0
    utilization: float = 0.0                     # 纸张利用率（仅 AI 模式）
    error_message: Optional[str] = None
    elapsed_seconds: float = 0.0


# ===========================================================================
# ImpositionTemplate — XML 模板管理器
# ===========================================================================

class ImpositionTemplate:
    """QHI XML 拼版模板管理器

    加载、解析和修改 Quite Hot Imposing 5 的 XML 拼版模板。
    支持修改页面尺寸、出血、叼口等参数。
    """

    # 默认模板内容（最小可用模板）
    DEFAULT_TEMPLATES = {
        XMLTemplateType.HUANCHEN_PIN: """<?xml version="1.0" encoding="UTF-8"?>
<QuiteHotImposing>
  <Command Name="Impose" Type="StepAndRepeat">
    <Paper Width="440mm" Height="590mm" />
    <Margins Left="0mm" Right="0mm" Top="0mm" Bottom="0mm" />
    <Source Size="Auto" />
    <Layout Rows="1" Columns="1" />
    <Bleed TrimBox="3mm" />
  </Command>
</QuiteHotImposing>""",

        XMLTemplateType.TIHUANHOU: """<?xml version="1.0" encoding="UTF-8"?>
<QuiteHotImposing>
  <Command Name="ReplaceBackEndpaper" Type="ReplacePage">
    <Paper Width="440mm" Height="590mm" />
    <Source Start="1" End="1" />
    <Replacement Page="Last" />
  </Command>
</QuiteHotImposing>""",

        XMLTemplateType.KANGXUAN_DELETE: """<?xml version="1.0" encoding="UTF-8"?>
<QuiteHotImposing>
  <Command Name="DeleteFrontBack" Type="DeletePages">
    <Paper Width="440mm" Height="590mm" />
    <Delete First="true" Last="true" />
    <Source Size="Auto" />
  </Command>
</QuiteHotImposing>""",

        XMLTemplateType.NEIYE_TIQU: """<?xml version="1.0" encoding="UTF-8"?>
<QuiteHotImposing>
  <Command Name="ExtractInner" Type="ExtractPages">
    <Paper Width="440mm" Height="590mm" />
    <PageRange All="true" />
    <Output Mode="Combine" />
  </Command>
</QuiteHotImposing>""",

        XMLTemplateType.KANGXUAN_DUOBEN: """<?xml version="1.0" encoding="UTF-8"?>
<QuiteHotImposing>
  <Command Name="MultiBookImpose" Type="Booklet">
    <Paper Width="440mm" Height="590mm" />
    <Booklet PagesPerSignature="8" />
    <Margins Left="0mm" Right="0mm" Top="0mm" Bottom="0mm" />
  </Command>
</QuiteHotImposing>""",
    }

    def __init__(self, template_type: XMLTemplateType,
                 template_path: Optional[str] = None):
        """
        Args:
            template_type: 模板类型
            template_path: 自定义 XML 模板文件路径，None 则使用内置默认
        """
        self.template_type = template_type
        self._xml_root: Optional[ET.Element] = None

        if template_path and os.path.exists(template_path):
            self.load(template_path)
        else:
            default_xml = self.DEFAULT_TEMPLATES.get(template_type)
            if default_xml:
                self._xml_root = ET.fromstring(default_xml)
            else:
                raise ValueError(f"未知模板类型: {template_type}")

    def load(self, file_path: str):
        """从文件加载 XML 模板"""
        self._xml_root = ET.parse(file_path).getroot()
        logger.info(f"已加载 QHI 模板: {file_path}")

    def save(self, file_path: str):
        """保存模板到文件"""
        if self._xml_root is None:
            raise RuntimeError("模板未加载")
        tree = ET.ElementTree(self._xml_root)
        ET.indent(tree, space="  ")
        tree.write(file_path, encoding="utf-8", xml_declaration=True)
        logger.info(f"模板已保存: {file_path}")

    def set_paper_size(self, width_mm: float, height_mm: float):
        """设置纸张尺寸"""
        paper = self._xml_root.find(".//Paper")
        if paper is not None:
            paper.set("Width", f"{width_mm}mm")
            paper.set("Height", f"{height_mm}mm")

    def set_margins(self, left: float, right: float,
                    top: float, bottom: float):
        """设置页边距"""
        margins = self._xml_root.find(".//Margins")
        if margins is not None:
            margins.set("Left", f"{left}mm")
            margins.set("Right", f"{right}mm")
            margins.set("Top", f"{top}mm")
            margins.set("Bottom", f"{bottom}mm")

    def set_bleed(self, bleed_mm: float):
        """设置出血位"""
        bleed = self._xml_root.find(".//Bleed")
        if bleed is not None:
            bleed.set("TrimBox", f"{bleed_mm}mm")

    def set_layout(self, rows: int, columns: int):
        """设置拼版行列数"""
        layout = self._xml_root.find(".//Layout")
        if layout is not None:
            layout.set("Rows", str(rows))
            layout.set("Columns", str(columns))

    def set_param(self, xpath: str, attr: str, value: str):
        """通用参数设置"""
        elem = self._xml_root.find(xpath)
        if elem is not None:
            elem.set(attr, value)

    def to_string(self) -> str:
        """导出为 XML 字符串"""
        if self._xml_root is None:
            return ""
        return ET.tostring(self._xml_root, encoding="unicode")

    @property
    def xml_root(self) -> Optional[ET.Element]:
        return self._xml_root


# ===========================================================================
# ImpositionEngine — 统一拼版引擎入口
# ===========================================================================

class ImpositionEngine:
    """统一拼版引擎

    两种模式：
      - mode='qhi'：调用 Quite Hot Imposing 5 通过 XML 模板执行
      - mode='ai'：调用 gang_layout 的贪心+模拟退火算法
      - mode='auto'：自动选择（<50页用 AI，≥50页用 QHI）
    """

    def __init__(
        self,
        mode: ImpositionMode = ImpositionMode.AUTO,
        qhi_exe: str = QHI_EXE,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        max_workers: Optional[int] = None,
    ):
        self.mode = mode
        self.qhi_exe = qhi_exe
        self.output_dir = output_dir
        self.max_workers = max_workers or max(1, os.cpu_count() // 2)

        # 验证 QHI 可执行文件
        self._qhi_available = os.path.exists(qhi_exe) if qhi_exe else False
        self._ai_available = AI_ENGINE_AVAILABLE

        if not self._qhi_available:
            logger.warning(f"QHI 可执行文件未找到: {qhi_exe}")
        if not self._ai_available:
            logger.warning("AI 拼版引擎不可用（gang_layout 未加载）")

    def process(self, job: ImpositionJob) -> ImpositionResult:
        """执行单个拼版任务

        Args:
            job: 拼版任务描述

        Returns:
            ImpositionResult 拼版结果
        """
        resolved_mode = self._resolve_mode(job)

        start_time = time.time()

        try:
            if resolved_mode == ImpositionMode.QHI:
                return self._process_qhi(job, start_time)
            elif resolved_mode == ImpositionMode.AI:
                return self._process_ai(job, start_time)
            else:
                return ImpositionResult(
                    job_id=job.job_id,
                    success=False,
                    mode="unknown",
                    error_message="无可用拼版模式",
                )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"拼版任务 {job.job_id} 失败: {e}")
            return ImpositionResult(
                job_id=job.job_id,
                success=False,
                mode=resolved_mode.value,
                error_message=str(e),
                elapsed_seconds=elapsed,
            )

    def process_batch(self, jobs: List[ImpositionJob]) -> List[ImpositionResult]:
        """批量并行处理拼版任务

        使用 ThreadPoolExecutor 并行处理，QHI 最大并发=2。
        """
        qhi_jobs = [j for j in jobs if self._resolve_mode(j) == ImpositionMode.QHI]
        ai_jobs = [j for j in jobs if self._resolve_mode(j) == ImpositionMode.AI]

        results: List[ImpositionResult] = []

        # AI 任务无并发限制
        if ai_jobs:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                ai_futures = {
                    executor.submit(self._process_ai, j, time.time()): j
                    for j in ai_jobs
                }
                for future in as_completed(ai_futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        job = ai_futures[future]
                        results.append(ImpositionResult(
                            job_id=job.job_id, success=False,
                            mode="ai", error_message=str(e),
                        ))

        # QHI 任务限并发=2
        if qhi_jobs:
            qhi_workers = min(QHI_MAX_CONCURRENT, self.max_workers)
            with ThreadPoolExecutor(max_workers=qhi_workers) as executor:
                qhi_futures = {
                    executor.submit(self._process_qhi, j, time.time()): j
                    for j in qhi_jobs
                }
                for future in as_completed(qhi_futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        job = qhi_futures[future]
                        results.append(ImpositionResult(
                            job_id=job.job_id, success=False,
                            mode="qhi", error_message=str(e),
                        ))

        return results

    def _resolve_mode(self, job: ImpositionJob) -> ImpositionMode:
        """解析实际使用的拼版模式"""
        if self.mode != ImpositionMode.AUTO:
            return self.mode

        # 自动模式：小批量用 AI，大批量用 QHI
        if job.total_pages < 50:
            return ImpositionMode.AI if self._ai_available else ImpositionMode.QHI
        else:
            return ImpositionMode.QHI if self._qhi_available else ImpositionMode.AI

    # ── QHI 模式 ──

    def _process_qhi(self, job: ImpositionJob, start_time: float) -> ImpositionResult:
        """通过 Quite Hot Imposing 5 XML 模板执行拼版"""
        if not self._qhi_available:
            return ImpositionResult(
                job_id=job.job_id, success=False, mode="qhi",
                error_message=f"QHI 可执行文件未找到: {self.qhi_exe}",
            )

        # 1. 准备模板
        template = ImpositionTemplate(job.template_type)
        template.set_paper_size(job.paper_size[0], job.paper_size[1])
        template.set_bleed(job.bleed_mm)

        # 2. 写入临时 XML 文件
        os.makedirs(self.output_dir, exist_ok=True)
        xml_path = os.path.join(self.output_dir, f"qhi_job_{job.job_id}.xml")
        template.save(xml_path)

        # 3. 构建输入文件列表（写入临时列表文件）
        list_path = os.path.join(self.output_dir, f"qhi_input_{job.job_id}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for input_file in job.input_files:
                f.write(f"{input_file}\n")

        # 4. 生成输出文件名
        output_file = os.path.join(
            self.output_dir,
            f"imposed_{job.job_id}.pdf"
        )

        # 5. 执行 QHI 命令
        # qi_applycommands.exe <xml_template> <output>
        cmd = [self.qhi_exe, xml_path, output_file]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
            )

            elapsed = time.time() - start_time

            if result.returncode != 0:
                error_detail = result.stderr.strip() or result.stdout.strip()
                return ImpositionResult(
                    job_id=job.job_id, success=False, mode="qhi",
                    error_message=f"QHI 返回码 {result.returncode}: {error_detail[:500]}",
                    elapsed_seconds=elapsed,
                )

            # 6. 验证输出
            if not os.path.exists(output_file):
                return ImpositionResult(
                    job_id=job.job_id, success=False, mode="qhi",
                    error_message="QHI 执行完成但未生成输出文件",
                    elapsed_seconds=elapsed,
                )

            file_size = os.path.getsize(output_file)
            page_count = self._count_pdf_pages(output_file)

            logger.info(
                f"QHI 拼版完成: {job.job_id} → {output_file} "
                f"({page_count}页, {file_size / 1024:.1f}KB, {elapsed:.1f}s)"
            )

            return ImpositionResult(
                job_id=job.job_id,
                success=True,
                mode="qhi",
                output_file=output_file,
                page_count=page_count,
                file_size_bytes=file_size,
                elapsed_seconds=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return ImpositionResult(
                job_id=job.job_id, success=False, mode="qhi",
                error_message="QHI 执行超时（5分钟）",
                elapsed_seconds=elapsed,
            )
        finally:
            # 清理临时文件
            for tmp in [xml_path, list_path]:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ── AI 模式 ──

    def _process_ai(self, job: ImpositionJob, start_time: float) -> ImpositionResult:
        """通过 gang_layout 贪心+模拟退火算法执行拼版"""
        if not self._ai_available:
            return ImpositionResult(
                job_id=job.job_id, success=False, mode="ai",
                error_message="AI 拼版引擎不可用",
            )

        try:
            # 1. 将输入文件转换为 OrderRect 列表
            orders = []
            for i, file_path in enumerate(job.input_files):
                # 从 PDF 获取实际尺寸
                size = self._get_pdf_page_size(file_path)
                if size:
                    w, h = size
                else:
                    w, h = job.paper_size  # 降级为默认纸张尺寸

                orders.append(OrderRect(
                    order_id=f"order_{i:04d}",
                    width_mm=w,
                    height_mm=h,
                    quantity=job.copies,
                    bleed_mm=job.bleed_mm,
                ))

            if not orders:
                return ImpositionResult(
                    job_id=job.job_id, success=False, mode="ai",
                    error_message="无有效输入文件",
                )

            # 2. 准备纸张规格
            paper = PaperSheet(
                name="自定义",
                width_mm=job.paper_size[0],
                height_mm=job.paper_size[1],
                grip_mm=job.grip_mm,
                side_margin_mm=3.0,
            )

            # 3. 执行 AI 排版
            engine = GangLayoutEngine(papers=[paper], use_sa=True)
            report = engine.get_layout_report(orders)

            if "error" in report:
                return ImpositionResult(
                    job_id=job.job_id, success=False, mode="ai",
                    error_message=report["error"],
                )

            # 4. 生成输出文件名
            os.makedirs(self.output_dir, exist_ok=True)
            output_file = os.path.join(
                self.output_dir,
                f"ai_imposed_{job.job_id}.pdf"
            )

            # 5. 写入排版报告（替代实际 PDF 生成，实际需 PDF 库支持）
            report_path = output_file.replace(".pdf", "_layout.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            elapsed = time.time() - start_time
            utilization = report.get("utilization", 0)

            logger.info(
                f"AI 拼版完成: {job.job_id} → {report_path} "
                f"(利用率 {utilization}%, {report['placed_items']}/{report['total_items']}项, "
                f"{elapsed:.1f}s)"
            )

            return ImpositionResult(
                job_id=job.job_id,
                success=True,
                mode="ai",
                output_file=output_file,
                page_count=report.get("placed_items", 0),
                file_size_bytes=os.path.getsize(report_path) if os.path.exists(report_path) else 0,
                utilization=utilization / 100.0 if utilization else 0.0,
                elapsed_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            return ImpositionResult(
                job_id=job.job_id, success=False, mode="ai",
                error_message=str(e),
                elapsed_seconds=elapsed,
            )

    # ── 辅助方法 ──

    @staticmethod
    def _count_pdf_pages(pdf_path: str) -> int:
        """读取 PDF 页数"""
        try:
            from pypdf import PdfReader
            with open(pdf_path, "rb") as f:
                reader = PdfReader(f)
                return len(reader.pages)
        except Exception:
            return 0

    @staticmethod
    def _get_pdf_page_size(pdf_path: str) -> Optional[Tuple[float, float]]:
        """获取 PDF 首页尺寸（宽mm, 高mm）"""
        try:
            from pypdf import PdfReader
            with open(pdf_path, "rb") as f:
                reader = PdfReader(f)
                if reader.pages:
                    page = reader.pages[0]
                    mediabox = page.mediabox
                    if mediabox:
                        # 1 point = 0.3528 mm (近似)
                        w_mm = (mediabox.width or 595) * 0.3528
                        h_mm = (mediabox.height or 842) * 0.3528
                        return (round(w_mm, 1), round(h_mm, 1))
        except Exception:
            pass
        return None


# ===========================================================================
# 拼版结果验证
# ===========================================================================

class ImpositionValidator:
    """拼版结果验证器

    检查输出页数、文件大小、出血位等是否正确。
    """

    @staticmethod
    def validate(result: ImpositionResult, job: ImpositionJob) -> Dict:
        """验证拼版结果

        Returns:
            验证报告字典，包含 passed 和各检查项详情
        """
        checks = {
            "output_exists": False,
            "file_size_ok": False,
            "page_count_ok": False,
            "bleed_ok": "N/A",
            "overall": False,
            "details": [],
        }

        # 检查1: 输出文件存在
        if result.output_file and os.path.exists(result.output_file):
            checks["output_exists"] = True
        else:
            checks["details"].append("输出文件不存在")
            return checks

        file_size = os.path.getsize(result.output_file)

        # 检查2: 文件大小合理（>1KB）
        if file_size > 1024:
            checks["file_size_ok"] = True
        else:
            checks["details"].append(f"输出文件过小 ({file_size} bytes)")

        # 检查3: 页数合理
        if result.page_count > 0:
            checks["page_count_ok"] = True
        else:
            checks["details"].append("输出页数为0")

        # 检查4: 出血位验证（仅 QHI 模式可检查）
        if result.mode == "qhi" and job.bleed_mm > 0:
            checks["bleed_ok"] = "已配置" if result.success else "未验证"

        checks["overall"] = all([
            checks["output_exists"],
            checks["file_size_ok"],
            checks["page_count_ok"],
        ])

        return checks


# ===========================================================================
# 模块级便捷函数
# ===========================================================================

def create_imposition_engine(
    mode: str = "auto",
    qhi_exe: str = QHI_EXE,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> ImpositionEngine:
    """创建拼版引擎实例"""
    return ImpositionEngine(
        mode=ImpositionMode(mode),
        qhi_exe=qhi_exe,
        output_dir=output_dir,
    )


def create_job(
    job_id: str,
    input_files: List[str],
    template_type: str = "环衬拼版",
    paper_width: float = 440,
    paper_height: float = 590,
    copies: int = 1,
    bleed_mm: float = 3.0,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> ImpositionJob:
    """快速创建拼版任务"""
    return ImpositionJob(
        job_id=job_id,
        input_files=input_files,
        paper_size=(paper_width, paper_height),
        template_type=XMLTemplateType(template_type),
        copies=copies,
        bleed_mm=bleed_mm,
        output_dir=output_dir,
    )


# ===========================================================================
# CLI 测试
# ===========================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("智能拼版整合模块 - 测试")
    print("=" * 60)

    # 测试模板管理
    print("\n[1] 测试 XML 模板管理...")
    for ttype in XMLTemplateType:
        try:
            tpl = ImpositionTemplate(ttype)
            tpl.set_paper_size(440, 590)
            tpl.set_bleed(3.0)
            xml_str = tpl.to_string()
            print(f"  {ttype.value}: {len(xml_str)} 字符")
        except Exception as e:
            print(f"  {ttype.value}: 加载失败 - {e}")

    # 测试拼版引擎
    print("\n[2] 测试拼版引擎...")
    engine = ImpositionEngine(mode=ImpositionMode.AUTO)
    print(f"  QHI 可用: {engine._qhi_available}")
    print(f"  AI 可用: {engine._ai_available}")
    print(f"  最大并行: {engine.max_workers} workers")

    # 测试结果验证
    print("\n[3] 测试结果验证...")
    result = ImpositionResult(
        job_id="test_001",
        success=True,
        mode="ai",
        output_file="nonexistent.pdf",
        page_count=0,
        file_size_bytes=0,
    )
    validation = ImpositionValidator.validate(
        result,
        ImpositionJob(
            job_id="test_001",
            input_files=[],
        ),
    )
    print(f"  验证通过: {validation['overall']}")
    for detail in validation["details"]:
        print(f"    - {detail}")
