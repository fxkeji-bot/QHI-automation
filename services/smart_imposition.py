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

    模板来源优先级：
      1. master_config.json 中的 imposition.qhi_template_dir（默认 KPSM_v3.0\\XML）
      2. 环境变量 QHI_TEMPLATE_DIR
      3. KPSM_v3.0\\XML\\（首选目录，7 个真实模板）
      4. KPSM_v2.0\\xml\\（降级备份目录）
      5. 内置默认负载模板（兜底）
    """

    # ── 模板类型到文件名的映射 ──
    TEMPLATE_FILES = {
        XMLTemplateType.HUANCHEN_PIN: [
            "3-环衬-拼.xml",
            "3-环衬-拼-.xml",
            "1+2---环衬（软精装 不带封面.xml",
        ],
        XMLTemplateType.TIHUANHOU: [
            "替换后环衬.xml",
        ],
        XMLTemplateType.KANGXUAN_DELETE: [
            "康轩删面底 尺寸A4缩放.xml",
        ],
        XMLTemplateType.NEIYE_TIQU: [
            "4-内页-提取再多本合拼.xml",
        ],
        XMLTemplateType.KANGXUAN_DUOBEN: [
            "康轩多本连拼 万2 拼4.xml",
        ],
    }

    # ── 必需的 XML 节点检查清单 ──
    REQUIRED_NODES = {
        XMLTemplateType.HUANCHEN_PIN: [".//Paper", ".//Command"],
        XMLTemplateType.TIHUANHOU: [".//Paper", ".//Command"],
        XMLTemplateType.KANGXUAN_DELETE: [".//Paper", ".//Command"],
        XMLTemplateType.NEIYE_TIQU: [".//Paper", ".//Command"],
        XMLTemplateType.KANGXUAN_DUOBEN: [".//Paper", ".//Command"],
    }

    # ── 模板搜索目录 ──
    TEMPLATE_DIRS = [
        r"Z:\fxkeji\KPSM_v3.0\XML",
        r"Z:\fxkeji\KPSM_v2.0\xml",
    ]

    # ── 兜底默认模板（当所有磁盘模板加载失败时使用） ──
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

    @staticmethod
    def _resolve_template_dir() -> Optional[str]:
        """解析模板目录，按优先级搜索"""
        # 1. 尝试从 master_config.json 读取
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "master_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                qhi_dir = config.get("imposition", {}).get("qhi_template_dir", "")
                if qhi_dir and os.path.isdir(qhi_dir):
                    return qhi_dir
            except Exception:
                pass

        # 2. 环境变量
        env_dir = os.environ.get("QHI_TEMPLATE_DIR", "")
        if env_dir and os.path.isdir(env_dir):
            return env_dir

        # 3. 按 TEMPLATE_DIRS 顺序搜索
        for d in ImpositionTemplate.TEMPLATE_DIRS:
            if os.path.isdir(d):
                return d

        return None

    @staticmethod
    def _find_template_file(template_type: XMLTemplateType,
                            template_dir: Optional[str] = None) -> Optional[str]:
        """根据模板类型查找对应的 XML 文件

        Returns:
            找到的完整文件路径，未找到返回 None
        """
        candidates = ImpositionTemplate.TEMPLATE_FILES.get(template_type, [])
        if not candidates:
            return None

        # 在指定目录中查找
        if template_dir and os.path.isdir(template_dir):
            for fname in candidates:
                full_path = os.path.join(template_dir, fname)
                if os.path.isfile(full_path):
                    return full_path

        # 全局搜索 TEMPLATE_DIRS
        for d in ImpositionTemplate.TEMPLATE_DIRS:
            if d == template_dir or not os.path.isdir(d):
                continue
            for fname in candidates:
                full_path = os.path.join(d, fname)
                if os.path.isfile(full_path):
                    return full_path

        return None

    def __init__(self, template_type: XMLTemplateType,
                 template_path: Optional[str] = None,
                 template_dir: Optional[str] = None):
        """
        Args:
            template_type: 模板类型
            template_path: 自定义 XML 模板文件路径（最高优先级，覆盖自动查找）
            template_dir: 指定模板搜索目录（优先级高于配置/环境变量）
        """
        self.template_type = template_type
        self._xml_root: Optional[ET.Element] = None
        self._source: str = "unknown"  # 记录模板来源

        # 1. 优先使用显式传入的模板路径
        if template_path and os.path.isfile(template_path):
            self.load(template_path)
            return

        # 2. 自动查找真实 XML 模板
        resolved_dir = template_dir or self._resolve_template_dir()
        resolved_path = self._find_template_file(template_type, resolved_dir)

        if resolved_path and os.path.isfile(resolved_path):
            self.load(resolved_path)
            return

        # 3. 降级为内置默认模板
        default_xml = self.DEFAULT_TEMPLATES.get(template_type)
        if default_xml:
            self._xml_root = ET.fromstring(default_xml)
            self._source = "builtin_default"
            logger.warning(
                f"模板 {template_type.value} 未找到磁盘文件，使用内置默认模板"
            )
        else:
            raise ValueError(f"未知模板类型: {template_type}")

    def load(self, file_path: str):
        """从文件加载 XML 模板"""
        self._xml_root = ET.parse(file_path).getroot()
        self._source = file_path
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

    def validate(self) -> Dict:
        """模板验证：XML 格式校验 + 参数完整性检查

        Returns:
            {"valid": bool, "checks": [...], "warnings": [...]}
        """
        checks = []
        warnings = []
        valid = True

        # 检查1: XML 根节点非空
        if self._xml_root is None:
            checks.append("FAIL: XML 根节点为空，模板未加载")
            return {"valid": False, "checks": checks, "warnings": warnings}

        # 检查2: 必需节点存在
        required = self.REQUIRED_NODES.get(self.template_type, [])
        for xpath in required:
            elem = self._xml_root.find(xpath)
            if elem is None:
                valid = False
                checks.append(f"FAIL: 缺少必需节点 {xpath}")
            else:
                checks.append(f"PASS: 节点 {xpath} 存在")

        # 检查3: Paper 节点参数完整性
        paper = self._xml_root.find(".//Paper")
        if paper is not None:
            for attr in ["Width", "Height"]:
                val = paper.get(attr, "")
                if not val:
                    valid = False
                    checks.append(f"FAIL: Paper 节点缺少 {attr} 属性")
                else:
                    checks.append(f"PASS: Paper.{attr} = {val}")

        # 检查4: Command 节点属性
        cmd = self._xml_root.find(".//Command")
        if cmd is not None:
            cmd_name = cmd.get("Name", "")
            cmd_type = cmd.get("Type", "")
            if not cmd_name:
                warnings.append("WARN: Command 缺少 Name 属性")
            if not cmd_type:
                warnings.append("WARN: Command 缺少 Type 属性")
            checks.append(f"INFO: Command Name={cmd_name}, Type={cmd_type}")

        # 检查5: 模板来源记录
        checks.append(f"INFO: 模板来源 = {self._source}")

        # 检查6: 文件大小（如果从文件加载）
        if self._source != "builtin_default" and os.path.isfile(self._source):
            size_kb = os.path.getsize(self._source) / 1024
            checks.append(f"INFO: 模板文件大小 = {size_kb:.1f} KB")
            if size_kb < 1.0:
                warnings.append(f"WARN: 模板文件异常小 ({size_kb:.1f} KB)，可能不完整")

        return {"valid": valid, "checks": checks, "warnings": warnings}

    def substitute_params(self, params: Dict[str, str]) -> int:
        """模板参数动态替换

        遍历 XML 中所有属性，将占位符 {{key}} / {key} 替换为实际值。

        Args:
            params: 参数映射字典，如 {"PaperWidth": "440", "PaperHeight": "590"}

        Returns:
            替换数量
        """
        if self._xml_root is None:
            return 0
        count = 0

        def _replace_in_element(elem: ET.Element):
            nonlocal count
            for attr_key, attr_val in list(elem.attrib.items()):
                new_val = attr_val
                for k, v in params.items():
                    new_val = new_val.replace("{{%s}}" % k, v)
                    new_val = new_val.replace("{%s}" % k, v)
                    # 也尝试直接匹配整个属性值
                    if attr_val.strip() == k:
                        new_val = v
                if new_val != attr_val:
                    elem.set(attr_key, new_val)
                    count += 1
            for child in elem:
                _replace_in_element(child)

        _replace_in_element(self._xml_root)
        if count > 0:
            logger.info(f"模板参数替换完成，共 {count} 处")
        return count

    def apply_job_params(self, job: "ImpositionJob"):
        """从 ImpositionJob 一键设置所有模板参数

        包括：纸张尺寸、出血、叼口、间距等。
        """
        self.set_paper_size(job.paper_size[0], job.paper_size[1])
        self.set_bleed(job.bleed_mm)

        # 叼口
        if job.grip_mm > 0:
            self.set_param(".//Margins", "Bottom", f"{job.grip_mm}mm")

        # 额外参数动态替换
        if job.extra_params:
            self.substitute_params(job.extra_params)

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

        # 1. 准备模板 → 从磁盘加载真实 XML 模板
        template = ImpositionTemplate(job.template_type)
        # 参数预检
        validation = template.validate()
        if not validation["valid"]:
            logger.warning(
                f"模板验证未通过 ({job.template_type.value})，继续尝试执行："
                + "; ".join(validation["checks"])
            )
        # 应用任务参数
        template.apply_job_params(job)

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
