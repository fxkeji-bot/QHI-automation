#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration/color_manager.py - 色彩管理核心模块

提供:
- ICC Profile管理（加载、解析、验证）
- 色彩空间转换（CMYK ↔ RGB ↔ Lab）
- 专色处理（Pantone → CMYK近似值）
- 色彩空间检查（PDF/X合规）
- 设备Profile匹配
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from pathlib import Path
from dataclasses import dataclass, field
import struct

from utils.logger import get_logger
from models.color_models import (
    ICCProfile, SpotColor, ColorValue, ColorCheckResult,
    ColorProfileMatch, DeviceColorCapability,
    ColorSpace, ProfileType, RenderingIntent,
    SpotColorFamily, PANTONE_COLORS,
    get_pantone_color, search_pantone
)

logger = get_logger(__name__)


class ColorManager:
    """色彩管理器"""
    
    def __init__(self, profile_dir: str = None, log_callback: Callable = None):
        """
        初始化色彩管理器
        
        Args:
            profile_dir: ICC Profile目录
            log_callback: 日志回调函数
        """
        self.profile_dir = profile_dir
        self.log = log_callback or logger.info
        
        # Profile存储
        self._profiles: Dict[str, ICCProfile] = {}
        self._profile_cache: Dict[str, Any] = {}  # 文件路径 -> PIL ImageCms profile
        
        # 专色数据库
        self._spot_colors: Dict[str, SpotColor] = dict(PANTONE_COLORS)
        
        # 检查依赖
        self._check_dependencies()
        
        # 加载Profile目录
        if profile_dir and os.path.exists(profile_dir):
            self.load_profiles_from_dir(profile_dir)
        
        self.log("色彩管理器初始化完成")
    
    def _check_dependencies(self):
        """检查依赖库"""
        try:
            from PIL import ImageCms
            self._cms_available = True
            self.log("Pillow ImageCms 已加载")
        except ImportError:
            self._cms_available = False
            self.log("Pillow ImageCms 未安装，部分功能受限")
    
    # ==================== ICC Profile管理 ====================
    
    def load_profile(self, file_path: str) -> Optional[ICCProfile]:
        """
        加载ICC Profile
        
        Args:
            file_path: ICC Profile文件路径
            
        Returns:
            ICCProfile实例
        """
        if not os.path.exists(file_path):
            self.log(f"Profile文件不存在: {file_path}")
            return None
        
        try:
            # 解析ICC文件头
            profile_info = self._parse_icc_header(file_path)
            
            # 创建Profile对象
            profile = ICCProfile(
                name=profile_info.get("description", Path(file_path).stem),
                file_path=file_path,
                file_size=os.path.getsize(file_path),
                color_space=profile_info.get("color_space", "CMYK"),
                pcs=profile_info.get("pcs", "Lab"),
                manufacturer=profile_info.get("manufacturer", ""),
                copyright=profile_info.get("copyright", ""),
            )
            
            # 尝试加载到PIL
            if self._cms_available:
                try:
                    from PIL import ImageCms
                    cms_profile = ImageCms.getOpenProfile(file_path)
                    self._profile_cache[file_path] = cms_profile
                except Exception as e:
                    self.log(f"PIL加载Profile失败: {e}")
            
            self._profiles[profile.profile_id] = profile
            self.log(f"已加载Profile: {profile.name} ({profile.color_space})")
            return profile
            
        except Exception as e:
            self.log(f"加载Profile失败: {file_path}, {e}")
            return None
    
    def _parse_icc_header(self, file_path: str) -> Dict[str, Any]:
        """解析ICC文件头"""
        info = {}
        
        try:
            with open(file_path, 'rb') as f:
                # 读取文件头（128字节）
                header = f.read(128)
                
                if len(header) < 128:
                    return info
                
                # 解析头部字段
                # 偏移0-3: Profile大小
                profile_size = struct.unpack('>I', header[0:4])[0]
                
                # 偏移4-7: Profile类型 (0x61637370 = 'acsp')
                profile_type = header[4:8].decode('ascii', errors='ignore')
                
                # 偏移8-11: 预留
                # 偏移12-15: 版本
                version = f"{header[12]}.{header[13] >> 4}.{header[13] & 0x0F}"
                
                # 偏移16-19: Profile类
                profile_class = header[16:20].decode('ascii', errors='ignore')
                
                # 偏移20-23: 色彩空间
                color_space = header[20:24].decode('ascii', errors='ignore').strip('\x00')
                
                # 偏移24-27: PCS
                pcs = header[24:28].decode('ascii', errors='ignore').strip('\x00')
                
                # 偏移28-39: 创建日期时间
                # 偏移40-43: 平台
                # 偏移44-47: 副文件格式
                # 偏移48-51: 主文件格式
                
                # 偏移52-55: 设备制造商
                manufacturer = header[52:56].decode('ascii', errors='ignore').strip('\x00')
                
                # 偏移56-59: 设备模型
                model = header[56:60].decode('ascii', errors='ignore').strip('\x00')
                
                # 偏移60-63: 屏幕可见性
                # 偏移64-67: 字节顺序
                # 偏移68-71: 照明条件
                # 偏移72-75: 荧光体色彩空间
                # 偏移76-79: 色彩外观意图
                # 偏移80-83: 红色色彩矩阵列
                # 偏移84-87: 绿色色彩矩阵列
                # 偏移88-91: 蓝色色彩矩阵列
                
                # 偏移92-95: 创建日期
                # 偏移96-99: 墨量限制
                # 偏移100-103: 底色去除限制
                # 偏移104-107: 底色去除
                # 偏移108-111: 照明条件
                # 偏移112-115: 荧光体
                # 偏移116-119: 色温
                
                # 偏移120-127: 设备名称（如果有的话）
                
                # 映射色彩空间名称
                cs_map = {
                    'RGB ': 'RGB',
                    'CMYK': 'CMYK',
                    'GRAY': 'GRAY',
                    'Lab ': 'Lab',
                    'XYZ ': 'XYZ',
                }
                
                info = {
                    "profile_size": profile_size,
                    "profile_type": profile_type,
                    "version": version,
                    "profile_class": profile_class,
                    "color_space": cs_map.get(color_space, color_space),
                    "pcs": pcs,
                    "manufacturer": manufacturer,
                    "model": model,
                }
                
        except Exception as e:
            self.log(f"解析ICC头失败: {e}")
        
        return info
    
    def load_profiles_from_dir(self, directory: str) -> List[ICCProfile]:
        """
        从目录加载所有ICC Profile
        
        Args:
            directory: 目录路径
            
        Returns:
            加载的Profile列表
        """
        profiles = []
        
        if not os.path.exists(directory):
            return profiles
        
        for filename in os.listdir(directory):
            if filename.lower().endswith(('.icc', '.icm')):
                file_path = os.path.join(directory, filename)
                profile = self.load_profile(file_path)
                if profile:
                    profiles.append(profile)
        
        self.log(f"从目录加载 {len(profiles)} 个Profile: {directory}")
        return profiles
    
    def get_profile(self, profile_id: str) -> Optional[ICCProfile]:
        """获取Profile"""
        return self._profiles.get(profile_id)
    
    def list_profiles(self) -> List[Dict]:
        """列出所有Profile"""
        return [
            {
                "profile_id": p.profile_id,
                "name": p.name,
                "color_space": p.color_space,
                "profile_type": p.profile_type,
                "file_path": p.file_path,
            }
            for p in self._profiles.values()
        ]
    
    def match_profiles(
        self,
        source_space: str,
        target_space: str,
        device_type: str = "",
    ) -> Optional[ColorProfileMatch]:
        """
        匹配最佳Profile组合
        
        Args:
            source_space: 源色彩空间
            target_space: 目标色彩空间
            device_type: 设备类型
            
        Returns:
            匹配结果
        """
        # 查找可用的转换路径
        candidates = []
        
        for profile in self._profiles.values():
            if profile.color_space == source_space:
                # 源Profile匹配
                candidates.append(profile)
        
        if not candidates:
            return ColorProfileMatch(
                source_profile="",
                target_profile="",
                conversion_path="无匹配Profile",
                quality_score=0,
                warnings=[f"未找到 {source_space} Profile"],
            )
        
        # 选择最佳匹配（简化逻辑）
        best = candidates[0]
        
        return ColorProfileMatch(
            source_profile=best.profile_id,
            target_profile=f"自动匹配-{target_space}",
            conversion_path=f"{source_space} → {target_space}",
            quality_score=75.0,
            recommendations=["建议使用设备制造商提供的官方Profile"],
        )
    
    # ==================== 色彩空间转换 ====================
    
    def convert_color(
        self,
        color: ColorValue,
        target_space: str,
        source_profile: str = None,
        target_profile: str = None,
        rendering_intent: int = RenderingIntent.RELATIVE_COLORIMETRIC.value,
    ) -> Optional[ColorValue]:
        """
        转换色彩空间
        
        Args:
            color: 源色彩值
            target_space: 目标色彩空间
            source_profile: 源Profile路径
            target_profile: 目标Profile路径
            rendering_intent: 渲染意图
            
        Returns:
            转换后的色彩值
        """
        if color.space == target_space:
            return color
        
        # 简单转换（无Profile）
        if not source_profile and not target_profile:
            return self._simple_convert(color, target_space)
        
        # 使用ICC Profile转换
        if self._cms_available and source_profile and target_profile:
            return self._icc_convert(color, target_space, source_profile, target_profile, rendering_intent)
        
        # 回退到简单转换
        return self._simple_convert(color, target_space)
    
    def _simple_convert(self, color: ColorValue, target_space: str) -> Optional[ColorValue]:
        """
        简单色彩转换（无Profile，使用标准公式）
        
        RGB→CMYK 使用 ISO 12647-2 标准的 Neugebauer 简化公式，
        并应用 GCR (Gray Component Replacement) 生成更准确的黑版。
        
        Args:
            color: 源色彩值
            target_space: 目标色彩空间
            
        Returns:
            转换后的色彩值
        """
        if color.space == target_space:
            return color
        
        # RGB -> CMYK（ISO 12647-2 简化公式 + GCR）
        if color.space == ColorSpace.RGB.value and target_space == ColorSpace.CMYK.value:
            if len(color.values) == 3:
                r, g, b = [v / 255.0 for v in color.values]
                
                # 计算 CMY
                c = 1 - r
                m = 1 - g
                y = 1 - b
                
                # GCR (Gray Component Replacement) - 中等黑版生成
                k = min(c, m, y)
                
                # 黑版限制：最大 95%，避免纯黑
                k = min(k, 0.95)
                
                if k >= 0.95:
                    return ColorValue(space=ColorSpace.CMYK.value, values=(0, 0, 0, 95))
                
                # UCR (Under Color Removal) - 底色去除
                # 当 k 较高时，减少 CMY 以避免总墨量过高
                ucr_factor = max(0, 1 - k * 0.3)
                
                c = (c - k * ucr_factor) / (1 - k * ucr_factor) * 100 if k * ucr_factor < 1 else 0
                m = (m - k * ucr_factor) / (1 - k * ucr_factor) * 100 if k * ucr_factor < 1 else 0
                y = (y - k * ucr_factor) / (1 - k * ucr_factor) * 100 if k * ucr_factor < 1 else 0
                
                # 限制总墨量 (TAC) 不超过 320%
                total = c + m + y + k * 100
                if total > 320:
                    scale = 320 / total
                    c *= scale
                    m *= scale
                    y *= scale
                
                return ColorValue(
                    space=ColorSpace.CMYK.value,
                    values=(round(c), round(m), round(y), round(k * 100))
                )
        
        # CMYK -> RGB（标准公式）
        if color.space == ColorSpace.CMYK.value and target_space == ColorSpace.RGB.value:
            if len(color.values) == 4:
                c, m, y, k = [v / 100.0 for v in color.values]
                r = (1 - c) * (1 - k)
                gamma = 2.2  # Gamma 校正
                r = r ** (1 / gamma) if r > 0 else 0
                g = (1 - m) * (1 - k)
                g = g ** (1 / gamma) if g > 0 else 0
                b = (1 - y) * (1 - k)
                b = b ** (1 / gamma) if b > 0 else 0
                return ColorValue(
                    space=ColorSpace.RGB.value,
                    values=(round(r * 255), round(g * 255), round(b * 255)),
                )
        
        # RGB -> GRAY（ITU-R BT.601 标准）
        if color.space == ColorSpace.RGB.value and target_space == ColorSpace.GRAY.value:
            if len(color.values) == 3:
                r, g, b = [v / 255.0 for v in color.values]
                # ITU-R BT.601 亮度权重
                gray = 0.299 * r + 0.587 * g + 0.114 * b
                return ColorValue(space=ColorSpace.GRAY.value, values=(round(gray * 100),))
        
        # CMYK -> GRAY
        if color.space == ColorSpace.CMYK.value and target_space == ColorSpace.GRAY.value:
            if len(color.values) == 4:
                c, m, y, k = color.values
                # 使用 K 通道作为灰度基础
                gray = k + min(c, m, y) * 0.3
                return ColorValue(space=ColorSpace.GRAY.value, values=(round(min(gray, 100)),))
        
        # GRAY -> RGB
        if color.space == ColorSpace.GRAY.value and target_space == ColorSpace.RGB.value:
            if len(color.values) == 1:
                v = round(color.values[0] * 2.55)
                return ColorValue(space=ColorSpace.RGB.value, values=(v, v, v))
        
        self.log(f"不支持的转换: {color.space} -> {target_space}")
        return None
    
    def _icc_convert(
        self,
        color: ColorValue,
        target_space: str,
        source_profile_path: str,
        target_profile_path: str,
        rendering_intent: int,
    ) -> Optional[ColorValue]:
        """
        使用ICC Profile转换色彩
        
        Args:
            color: 源色彩值
            target_space: 目标色彩空间
            source_profile_path: 源Profile路径
            target_profile_path: 目标Profile路径
            rendering_intent: 渲染意图
            
        Returns:
            转换后的色彩值
        """
        if not self._cms_available:
            return self._simple_convert(color, target_space)
        
        try:
            from PIL import ImageCms
            
            # 获取或加载Profile
            src_profile = self._profile_cache.get(source_profile_path)
            if not src_profile:
                src_profile = ImageCms.getOpenProfile(source_profile_path)
            
            dst_profile = self._profile_cache.get(target_profile_path)
            if not dst_profile:
                dst_profile = ImageCms.getOpenProfile(target_profile_path)
            
            # 创建转换变换
            transform = ImageCms.buildTransform(
                src_profile,
                dst_profile,
                "RGB" if color.space == "RGB" else color.space,
                "RGB" if target_space == "RGB" else target_space,
                renderingIntent=rendering_intent,
            )
            
            # 执行转换
            if color.space == ColorSpace.RGB.value:
                # 转换为像素数据
                from PIL import Image
                img = Image.new("RGB", (1, 1), tuple(int(v) for v in color.values))
                img = ImageCms.applyTransform(img, transform)
                new_values = img.getpixel((0, 0))
                return ColorValue(space=target_space, values=new_values)
            
            # 其他色彩空间的转换需要更多处理
            return self._simple_convert(color, target_space)
            
        except Exception as e:
            self.log(f"ICC转换失败: {e}")
            return self._simple_convert(color, target_space)
    
    # ==================== 专色处理 ====================
    
    def get_spot_color(self, name: str) -> Optional[SpotColor]:
        """
        获取专色
        
        Args:
            name: 专色名称（如 "185 C"）
            
        Returns:
            SpotColor实例
        """
        # 先从自定义数据库查找
        color = self._spot_colors.get(name)
        if color:
            return color
        
        # 尝试从Pantone数据库查找
        return get_pantone_color(name)
    
    def search_spot_colors(self, keyword: str) -> List[SpotColor]:
        """搜索专色"""
        results = []
        keyword_lower = keyword.lower()
        
        # 搜索自定义数据库
        for name, color in self._spot_colors.items():
            if keyword_lower in name.lower() or keyword_lower in color.name.lower():
                results.append(color)
        
        # 搜索Pantone数据库
        pantone_results = search_pantone(keyword)
        for color in pantone_results:
            if color not in results:
                results.append(color)
        
        return results
    
    def add_spot_color(self, color: SpotColor):
        """添加专色到数据库"""
        self._spot_colors[color.name] = color
    
    def spot_to_cmyk(self, spot_name: str) -> Optional[Tuple[float, float, float, float]]:
        """
        专色转CMYK
        
        Args:
            spot_name: 专色名称
            
        Returns:
            CMYK值 (C, M, Y, K) 百分比
        """
        color = self.get_spot_color(spot_name)
        if color:
            return color.cmyk_approx
        return None
    
    def spot_to_rgb(self, spot_name: str) -> Optional[Tuple[int, int, int]]:
        """
        专色转RGB
        
        Args:
            spot_name: 专色名称
            
        Returns:
            RGB值
        """
        color = self.get_spot_color(spot_name)
        if color:
            return color.rgb_approx
        return None
    
    def find_nearest_pantone(self, cmyk: Tuple[float, float, float, float]) -> Optional[SpotColor]:
        """
        查找最接近的Pantone色
        
        Args:
            cmyk: CMYK值
            
        Returns:
            最接近的SpotColor
        """
        best_match = None
        best_distance = float('inf')
        
        c, m, y, k = cmyk
        
        for name, color in PANTONE_COLORS.items():
            pc, pm, py, pk = color.cmyk_approx
            distance = ((c - pc) ** 2 + (m - pm) ** 2 + (y - py) ** 2 + (k - pk) ** 2) ** 0.5
            
            if distance < best_distance:
                best_distance = distance
                best_match = color
        
        return best_match
    
    # ==================== 色彩空间检查 ====================
    
    def check_color_space(
        self,
        file_path: str = None,
        color_spaces: List[str] = None,
    ) -> List[ColorCheckResult]:
        """
        检查色彩空间合规性
        
        Args:
            file_path: PDF文件路径（可选）
            color_spaces: 使用的色彩空间列表
            
        Returns:
            检查结果列表
        """
        results = []
        
        # PDF/X检查：必须有输出意图
        if file_path and file_path.lower().endswith('.pdf'):
            # 检查是否包含CMYK内容
            has_cmyk = any("CMYK" in cs.upper() for cs in (color_spaces or []))
            has_rgb = any("RGB" in cs.upper() for cs in (color_spaces or []))
            
            # PDF/X-1a: 只能有CMYK + 专色
            if has_rgb:
                results.append(ColorCheckResult(
                    check_type="pdfx_color_space",
                    passed=False,
                    severity="error",
                    message="PDF/X-1a不允许RGB色彩空间",
                    details={"found": "RGB", "required": "CMYK"},
                ))
            
            # 检查是否使用了灰色
            has_gray = any("GRAY" in cs.upper() for cs in (color_spaces or []))
            if has_gray:
                results.append(ColorCheckResult(
                    check_type="pdfx_color_space",
                    passed=True,
                    severity="warning",
                    message="检测到灰度色彩空间，建议使用CMYK(K)",
                    details={"found": "GRAY"},
                ))
        
        # 通用检查
        if not color_spaces:
            results.append(ColorCheckResult(
                check_type="color_space_info",
                passed=True,
                severity="info",
                message="未检测到色彩空间信息",
            ))
        
        return results
    
    def check_ink_coverage(
        self,
        cmyk_values: List[Tuple[float, float, float, float]],
        max_total: float = 320.0,
        max_per_channel: float = 100.0,
    ) -> List[ColorCheckResult]:
        """
        检查墨量
        
        Args:
            cmyk_values: CMYK值列表
            max_total: 最大总墨量百分比
            max_per_channel: 单通道最大百分比
            
        Returns:
            检查结果列表
        """
        results = []
        
        for i, (c, m, y, k) in enumerate(cmyk_values):
            total = c + m + y + k
            
            # 总墨量检查
            if total > max_total:
                results.append(ColorCheckResult(
                    check_type="ink_coverage_total",
                    passed=False,
                    severity="warning",
                    message=f"总墨量 {total:.1f}% 超过限制 {max_total}%",
                    details={
                        "total": total,
                        "limit": max_total,
                        "cmyk": [c, m, y, k],
                    },
                    object_index=i,
                ))
            
            # 单通道检查
            for channel, value in [("C", c), ("M", m), ("Y", y), ("K", k)]:
                if value > max_per_channel:
                    results.append(ColorCheckResult(
                        check_type="ink_coverage_channel",
                        passed=False,
                        severity="error",
                        message=f"{channel}通道墨量 {value:.1f}% 超过限制 {max_per_channel}%",
                        details={
                            "channel": channel,
                            "value": value,
                            "limit": max_per_channel,
                        },
                        object_index=i,
                    ))
        
        return results
    
    def check_gamut(
        self,
        lab_values: List[Tuple[float, float, float]],
        device_gamut: Dict[str, float] = None,
    ) -> List[ColorCheckResult]:
        """
        检查色域
        
        Args:
            lab_values: Lab值列表
            device_gamut: 设备色域范围 {"L_min": ..., "L_max": ..., "a_min": ..., ...}
            
        Returns:
            检查结果列表
        """
        results = []
        
        # 默认sRGB色域范围
        if not device_gamut:
            device_gamut = {
                "L_min": 0, "L_max": 100,
                "a_min": -86, "a_max": 98,
                "b_min": -108, "b_max": 95,
            }
        
        for i, (l, a, b) in enumerate(lab_values):
            out_of_gamut = []
            
            if l < device_gamut["L_min"] or l > device_gamut["L_max"]:
                out_of_gamut.append(f"L={l:.1f}")
            if a < device_gamut["a_min"] or a > device_gamut["a_max"]:
                out_of_gamut.append(f"a={a:.1f}")
            if b < device_gamut["b_min"] or b > device_gamut["b_max"]:
                out_of_gamut.append(f"b={b:.1f}")
            
            if out_of_gamut:
                results.append(ColorCheckResult(
                    check_type="gamut_warning",
                    passed=False,
                    severity="warning",
                    message=f"色域外颜色: {', '.join(out_of_gamut)}",
                    details={
                        "lab": [l, a, b],
                        "gamut": device_gamut,
                    },
                    object_index=i,
                ))
        
        return results
    
    # ==================== 设备管理 ====================
    
    def get_device_capability(self, device_id: str = "default") -> DeviceColorCapability:
        """获取设备色彩能力"""
        return DeviceColorCapability(
            device_id=device_id,
            device_name="默认设备",
            supported_spaces=["CMYK", "RGB"],
            supported_intents=[0, 1, 2, 3],
            max_ink_coverage=320.0,
            min_ink_coverage=5.0,
            total_ink_limit=320.0,
            gcr_level="medium",
        )
