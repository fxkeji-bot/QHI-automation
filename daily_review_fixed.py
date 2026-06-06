#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""



1. .py
2. 
3. 
4.  E:\Temp\bug\

8:00 AM
E:\Temp\bug\review_YYYY-MM-DD_HH-MM-SS.txt
"""

import sys
import os
import py_compile
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# 
PROJECT_ROOT = Path(r"C:\Users\diy\AppData\Roaming\Tencent\Marvis\User\oAN1i2RR3FJVCxKB7RydPILg8Nrg\workspace\conv_19e8e55ce77_b1c0386becb8\output\qhi_processor")

# 
OUTPUT_DIR = Path(r"E:\Temp\bug")


class DailyReviewer:
    """"""
    
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.report_lines: List[str] = []
    
    def log(self, message: str):
        """"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.report_lines.append(log_line)
        print(log_line)
    
    def check_syntax(self) -> bool:
        """1: """
        self.log("=" * 60)
        self.log("#1: py_compile")
        self.log("=" * 60)
        
        py_files = list(PROJECT_ROOT.rglob("*.py"))
        self.log(f" {len(py_files)} Python")
        
        failed_files = []
        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
                self.log(f"   {py_file.name}")
            except py_compile.PyCompileError as e:
                error_msg = str(e)
                self.log(f"   {py_file.name}: {error_msg}")
                failed_files.append((py_file, error_msg))
        
        self.log(f"\n: {len(py_files) - len(failed_files)}/{len(py_files)} ")
        
        if failed_files:
            self.results.append(("", False, f"{len(failed_files)} "))
            return False
        else:
            self.results.append(("", True, ""))
            return True
    
    def check_imports(self) -> bool:
        """#2: """
        self.log("=" * 60)
        self.log("#2: ")
        self.log("=" * 60)
        
        #  sys.path
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
                self.log(f"   {module_name}.{class_name}")
            except ImportError as e:
                self.log(f"   {module_name}.{class_name}: {e}")
                failed_modules.append((module_name, class_name, str(e)))
            except Exception as e:
                self.log(f"   {module_name}.{class_name}:  - {e}")
                failed_modules.append((module_name, class_name, str(e)))
        
        self.log(f"\n: {len(modules_to_check) - len(failed_modules)}/{len(modules_to_check)} ")
        
        if failed_modules:
            self.results.append(("", False, f"{len(failed_modules)} "))
            return False
        else:
            self.results.append(("", True, ""))
            return True
    
    def run_acceptance_test(self) -> bool:
        """#3: """
        self.log("=" * 60)
        self.log("#3: test_p0_acceptance.py")
        self.log("=" * 60)
        
        test_script = PROJECT_ROOT / "test_p0_acceptance.py"
        if not test_script.exists():
            self.log(f"    : {test_script}")
            self.results.append(("", False, ""))
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
            
            # 
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.log(f"  [STDOUT] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.log(f"  [STDERR] {line}")
            
            if result.returncode == 0:
                self.log("\n")
                self.results.append(("", True, ""))
                return True
            else:
                self.log(f"\n: {result.returncode}")
                self.results.append(("", False, f": {result.returncode}"))
                return False
        except Exception as e:
            self.log(f"\n: {e}")
            self.results.append(("", False, str(e)))
            return False
    
    def generate_report(self) -> Path:
        """"""
        self.log("=" * 60)
        self.log("")
        self.log("=" * 60)
        
        # 
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        # 
        report_content = [
            "=" * 60,
            f"QHI v35 - ",
            f": {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            "## ",
            "",
        ]
        
        for check_name, result, detail in self.results:
            status = " " if result else " "
            report_content.append(f"{status}  {check_name}: {detail}")
        
        report_content.extend([
            "",
            "-" * 60,
            f": {passed}/{total} ",
            "",
        ])
        
        if passed == total:
            report_content.append(" ")
            report_content.append(" ")
        else:
            report_content.append("  ")
            report_content.append(" ")
        
        report_content.extend([
            "",
            "=" * 60,
            "## ",
            "=" * 60,
            "",
        ])
        report_content.extend(self.report_lines)
        report_content.append("")
        report_content.append("=" * 60)
        report_content.append("")
        report_content.append("=" * 60)
        
        # 
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = OUTPUT_DIR / f"review_{timestamp}.txt"
        
        report_file.write_text("\n".join(report_content), encoding="utf-8-sig")
        
        self.log(f"\n: {report_file}")
        
        return report_file
    
    def run(self) -> bool:
        """"""
        self.log(" QHI v35 - ")
        self.log(f": {PROJECT_ROOT}")
        self.log(f": {OUTPUT_DIR}")
        self.log("")
        
        # 
        self.check_syntax()
        self.check_imports()
        self.run_acceptance_test()
        
        # 
        report_file = self.generate_report()
        
        # 
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        self.log("")
        self.log(f": {passed}/{total} ")
        self.log(f": {report_file}")
        
        return passed == total


def main():
    """"""
    # 
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 
    reviewer = DailyReviewer()
    success = reviewer.run()
    
    # 
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
