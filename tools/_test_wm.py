import sys, os
sys.path.insert(0, r'E:\qhi_processor')

from services.hot_folder_service import HotFolderService
from services.web_monitor import WebMonitor

svc = HotFolderService()
wm = WebMonitor(svc, port=8080)

try:
    wm.start()
    print("WebMonitor started OK on port 8080")
except Exception as e:
    print(f"WebMonitor start FAILED: {e}")

import urllib.request
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8080/api/status', timeout=3)
    print("API response:", resp.read().decode()[:100])
except Exception as e:
    print(f"API request FAILED: {e}")

wm.stop()

# Now test with None service
print()
print("--- Test with None service ---")
wm2 = WebMonitor(None, port=8081)
try:
    wm2.start()
    print("WebMonitor(None) started OK on port 8081")
except Exception as e:
    print(f"WebMonitor(None) FAILED: {e}")

try:
    resp = urllib.request.urlopen('http://127.0.0.1:8081/api/status', timeout=3)
    print("API response:", resp.read().decode()[:100])
except Exception as e:
    print(f"API request FAILED: {e}")

wm2.stop()
