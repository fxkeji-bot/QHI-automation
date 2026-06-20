#!/usr/bin/env python3
"""测试热文件夹服务"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.hot_folder_service import HotFolderService

service = HotFolderService()

# 添加监控目录
service.add_monitor(r'\\Server2\客户文件2\out', printer_ip='192.168.1.210')

# 获取统计信息
stats = service.get_stats()
print('Hot Folder Service Stats:')
print('  Monitors:', stats['monitors'])
print('  Running:', stats['running'])

# 生成JDF示例
print()
print('=== JDF Generation Test ===')
from pathlib import Path
import hashlib
from datetime import datetime

file_path = Path(r'\\Server2\客户文件2\out\test.pdf')
job_id = f'JDF_{hashlib.md5(str(file_path).encode()).hexdigest()[:12]}'
timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

jdf = f'''<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
     Type="Combined" 
     ID="{job_id}"
     JobPartID="{job_id}_P1">
  <AuditPool>
    <Created Agent="QHI Processor v1.3.0" 
             Timestamp="{timestamp}"/>
  </AuditPool>
  <MediaSheet MediaQuality="A4" Weight="157"/>
  <RunList>
    <FileSpec URL="file:///test.pdf"/>
  </RunList>
  <Component ID="C001" Pieces="1"/>
</JDF>'''

print('JDF Generated:')
print(jdf[:500])
