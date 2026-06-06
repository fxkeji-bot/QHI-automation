#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日自动审查脚本

功能：
1. 语法检查（所有.py文件）
2. 导入检查（关键模块）
3. 运行验收测试
4. 生成审查报告并保存到 E:\Temp\bug\

调度：每天8:00 AM自动运行
输出：E:\Temp\bug\review_YYYY-MM-DD_HH-MM-SS.txt
"""

import sys
import os
import py_compile
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# 项目根目录
PROJECT_ROOT = Path(r"C:\Users\diy\AppData\Roaming\Tencent\Marvis\User\oAN1i2RR3FJVCxKB7RydPILg8Nrg\workspace\conv_19e8e55ce77_b1c0386becb8\output\qhi_processor")

# 输出目录
OUTPUT_DIR = Path(r"E:\Temp\bug")


class DailyReviewer:
    """每日审查器"""
    
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.report_lines: List[str] = []
    
    def log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.report_lines.append(log_line)
        print(log_line)
    
    def check_syntax(self) -> bool:
        """检查1: 语法检查"""
        self.log("=" * 60)
        self.log("检查#1: 语法检查（py_compile）")
        self.log("=" * 60)
        
        py_files = list(PROJECT_ROOT.rglob("*.py"))
        self.log(f"扫描到 {len(py_files)} 个Python文件")
        
        failed_files = []
        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
                self.log(f"  ✅ {py_file.name}")
            except py_compile.PyCompileError as e:
                error_msg = str(e)
                self.log(f"  ❌ {py_file.name}: {error_msg}")
                failed_files.append((py_file, error_msg))
        
        self.log(f"\n语法检查完成: {len(py_files) - len(failed_files)}/{len(py_files)} 通过")
        
        if failed_files:
            self.results.append(("语法检查", False, f"{len(failed_files)} 个文件失败"))
            return False
        else:
            self.results.append(("语法检查", True, "全部通过"))
            return True
    
    def check_imports(self) -> bool:
        """检查#2: 导入检查"""
        self.log("=" * 60)
        self.log("检查#2: 导入检查（关键模块）")
        self.log("=" * 60)
        
        # 添加项目根目录到 sys.path
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        
        modules_to_check = [
            ("core.database", "Database"),
            ("models.metadata", "MetadataManager"),
            ("services.variable_service", "VariableManager"),
            ("services.rule_engine", "RuleEngine"),
            ("integration.action_executor", "ActionExecutor"),
            ("integration.smart_processor", "SmartProcessor"),
            ("utils.file_utils", "InfoExtractor"),
            ("utils.price_calculator", "DigitalPricingEngine"),
            ("utils.i18n", "I18nEngine"),
        ]
        
        failed_modules = []
        for module_name, class_name in modules_to_check:
            try:
                module = __import__(module_name, fromlist=[class_name])
                cls = getattr(module, class_name)
                self.log(f"  ✅ {module_name}.{class_name}")
            except ImportError as e:
                self.log(f"  ❌ {module_name}.{class_name}: {e}")
                failed_modules.append((module_name, class_name, str(e)))
            except Exception as e:
                self.log(f"  ❌ {module_name}.{class_name}: 未预期错误 - {e}")
                failed_modules.append((module_name, class_name, str(e)))
        
        self.log(f"\n导入检查完成: {len(modules_to_check) - len(failed_modules)}/{len(modules_to_check)} 通过")
        
        if failed_modules:
            self.results.append(("导入检查", False, f"{len(failed_modules)} 个模块失败"))
            return False
        else:
            self.results.append(("导入检查", True, "全部通过"))
            return True
    
    def run_acceptance_test(self) -> bool:
        """检查#3: 运行验收测试"""
        self.log("=" * 60)
        self.log("检查#3: 运行验收测试（test_p0_acceptance.py）")
        self.log("=" * 60)
        
        test_script = PROJECT_ROOT / "test_p0_acceptance.py"
        if not test_script.exists():
            self.log(f"  ⚠️  验收测试脚本不存在: {test_script}")
            self.results.append(("验收测试", False, "测试脚本不存在"))
            return False
        
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, str(test_script)],
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
                timeout=60
            )
            
            # 记录输出
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.log(f"  [STDOUT] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.log(f"  [STDERR] {line}")
            
            if result.returncode == 0:
                self.log("\n验收测试通过")
                self.results.append(("验收测试", True, "全部通过"))
                return True
            else:
                self.log(f"\n验收测试失败（返回码: {result.returncode}）")
                self.results.append(("验收测试", False, f"返回码: {result.returncode}"))
                return False
        except Exception as e:
            self.log(f"\n验收测试执行失败: {e}")
            self.results.append(("验收测试", False, str(e)))
            return False
    
    def generate_report(self) -> Path:
        """生成审查报告"""
        self.log("=" * 60)
        self.log("生成审查报告")
        self.log("=" * 60)
        
        # 统计
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        # 生成报告内容
        report_content = [
            "=" * 60,
            f"QHI拼版处理器 v35 - 每日自动审查报告",
            f"审查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "## 检查结果",
            "",
        ]
        
        for check_name, result, detail in self.results:
            status = "✅ 通过" if result else "❌ 失败"
            report_content.append(f"{status}  {check_name}: {detail}")
        
        report_content.extend([
            "",
            "-" * 60,
            f"总计: {passed}/{total} 通过",
            "",
        ])
        
        if passed == total:
            report_content.append("🎉 所有检查通过！项目状态良好。")
            report_content.append("✅ 可以进行生产部署。")
        else:
            report_content.append("⚠️  部分检查失败！请查看详细日志。")
            report_content.append("❌ 建议修复失败项后再部署。")
        
        report_content.extend([
            "",
            "=" * 60,
            "## 详细日志",
            "=" * 60,
            "",
        ])
        report_content.extend(self.report_lines)
        report_content.append("")
        report_content.append("=" * 60)
        report_content.append("报告结束")
        report_content.append("=" * 60)
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = OUTPUT_DIR / f"review_{timestamp}.txt"
        
        report_file.write_text("\n".join(report_content), encoding="utf-8-sig")
        
        self.log(f"\n报告已保存: {report_file}")
        
        return report_file
    
    def run(self) -> bool:
        """运行完整审查"""
        self.log("🔧 QHI拼版处理器 v35 - 每日自动审查")
        self.log(f"项目目录: {PROJECT_ROOT}")
        self.log(f"输出目录: {OUTPUT_DIR}")
        self.log("")
        
        # 执行所有检查
        self.check_syntax()
        self.check_imports()
        self.run_acceptance_test()
        
        # 生成报告
        report_file = self.generate_report()
        
        # 返回总体结果
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        self.log("")
        self.log(f"审查完成: {passed}/{total} 通过")
        self.log(f"报告文件: {report_file}")
        
        return passed == total


def main():
    """主函数"""
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 运行审查
    reviewer = DailyReviewer()
    success = reviewer.run()
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
