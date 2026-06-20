# 热文件夹监控与JDF集成接入指南

**版本**: v1.0  
**日期**: 2026-06-20  
**适用设备**: Océ VarioPrint 6000, HP Indigo 12000/7900

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    QHI 拼版处理器                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              HotFolderService                        │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │
│  │  │ 文件监控  │→│ JDF生成   │→│ 作业提交  │       │   │
│  │  └───────────┘  └───────────┘  └───────────┘       │   │
│  └─────────────────────────────────────────────────────┘   │
│                           ↓                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              打印机热文件夹                          │   │
│  │  \\Server2\客户文件2\out\oce6000\                    │   │
│  │  \\Server2\客户文件2\out\hp12000\                    │   │
│  │  \\Server2\客户文件2\out\hp7900\                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    数字印刷机                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Océ 6000    │  │ HP12000     │  │ HP7900      │         │
│  │ 192.168.1.210│  │ 192.168.1.100│  │ 192.168.1.101│         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、配置说明

### 2.1 热文件夹配置

在QHI主界面 → 系统设置 → 监控目录 中添加：

| 监控目录 | 打印机IP | 自动打印 | 说明 |
|----------|----------|----------|------|
| \\Server2\客户文件2\out | 192.168.1.210 | ✅ | Océ VarioPrint 6000 |
| \\Server2\客户文件2\out\hp12000 | 192.168.1.100 | ✅ | HP Indigo 12000 |
| \\Server2\客户文件2\out\hp7900 | 192.168.1.101 | ✅ | HP Indigo 7900 |

### 2.2 打印机参数

| 设备 | IP地址 | 最大纸张 | 速度 | 接口 |
|------|--------|----------|------|------|
| Océ VarioPrint 6000 | 192.168.1.210 | 330×488mm | 130ppm | JDF/JMF/热文件夹 |
| HP Indigo 12000 | 192.168.1.100 | 750×530mm | 12000sph | JDF/JMF |
| HP Indigo 7900 | 192.168.1.101 | 464×320mm | 7900sph | JDF/JMF |

---

## 三、代码实现

### 3.1 热文件夹服务

```python
from services.hot_folder_service import HotFolderService

# 创建服务
service = HotFolderService()

# 添加监控目录
service.add_monitor(
    folder_path=r"\\Server2\客户文件2\out",
    printer_ip="192.168.1.210",
    auto_print=True,
    file_pattern="*.pdf",
    stable_minutes=2
)

# 启动监控
service.start()

# 获取统计
stats = service.get_stats()
print(f"监控: {stats['monitors']}, 作业: {stats['total_jobs']}")
```

### 3.2 JDF工作传票生成

```python
from integration.jdf_handler import JDFHandler

handler = JDFHandler()

# 生成JDF
jdf = handler.create_ticket(
    job_id="JOB001",
    file_path=r"\\Server2\客户文件2\out\test.pdf",
    paper_type="A4",
    weight_gsm=157,
    quantity=100
)

# 保存JDF文件
with open(r"\\Server2\客户文件2\out\oce6000\JOB001.jdf", 'w') as f:
    f.write(jdf)
```

### 3.3 Océ打印机集成

```python
from integration.oce_varioprint import OceIntegration

oce = OceIntegration()

# 发现打印机
printers = oce.discover_printers()
for p in printers:
    print(f"  {p['name']}: {p['status']}")

# 检查状态
status = oce.check_printer_status("192.168.1.210")
print(f"Océ 6000: {status['status']}")
```

---

## 四、工作流程

1. **文件监控**: QHI监控热文件夹，检测新PDF文件
2. **稳定性检查**: 等待文件稳定（默认2分钟）
3. **预检**: 自动检查文件质量（DPI、色彩、出血等）
4. **JDF生成**: 根据文件信息生成JDF工作传票
5. **作业提交**: 将文件和JDF提交到打印机热文件夹
6. **状态跟踪**: 通过JMF接收印刷状态反馈

---

## 五、部署检查清单

- [ ] 打印机IP地址配置正确
- [ ] 热文件夹路径可访问
- [ ] 打印机Web接口可访问
- [ ] JDF格式符合CIP4标准
- [ ] 文件监控间隔合理（建议2-5分钟）
- [ ] 错误处理和日志记录完善

---

**编制**: MiMo Code Agent
**日期**: 2026-06-20
