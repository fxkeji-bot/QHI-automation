# 数字印刷机参数与自动化工作流对接方案

**日期**: 2026-06-20
**版本**: v1.0

---

## 一、数字印刷机参数

### 1.1 HP Indigo 12000

| 参数 | 值 |
|------|-----|
| 最大纸张 | 750×530mm |
| 最小纸张 | 296×209mm |
| 印刷速度 | 12,000 sheets/hour |
| 分辨率 | 1200×1200 dpi |
| 色彩模式 | CMYK + 专色 (最多7色) |
| 双面印刷 | 支持 |
| 纸张厚度 | 60-350 g/m² |
| 接口 | Ethernet, JDF/JMF |

### 1.2 HP Indigo 7900

| 参数 | 值 |
|------|-----|
| 最大纸张 | 464×320mm |
| 最小纸张 | 200×279mm |
| 印刷速度 | 7,900 sheets/hour |
| 分辨率 | 1200×1200 dpi |
| 色彩模式 | CMYK + 专色 (最多5色) |
| 双面印刷 | 支持 |
| 纸张厚度 | 60-350 g/m² |
| 接口 | Ethernet, JDF/JMF |

### 1.3 Océ VarioPrint 6000

| 参数 | 值 |
|------|-----|
| IP地址 | 192.168.1.210 |
| 最大纸张 | 330×488mm |
| 最小纸张 | 148×210mm |
| 印刷速度 | 130 pages/min (A4) |
| 分辨率 | 1200×1200 dpi |
| 色彩模式 | CMYK |
| 双面印刷 | 支持 |
| 纸张厚度 | 52-350 g/m² |
| 接口 | Ethernet, JDF/JMF, Hot Folder |

---

## 二、自动化工作流对接

### 2.1 工作流程架构

```
┌─────────────────────────────────────────────────────────────┐
│                    QHI 拼版处理器                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  文件监控    │→│  预检/拼版   │→│  输出管理   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         ↓                ↓                ↓                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              JDF/JMF 工作传票                        │   │
│  └─────────────────────────────────────────────────────┘   │
│         ↓                ↓                ↓                 │
└─────────────────────────────────────────────────────────────┘
         ↓                ↓                ↓
┌─────────────────────────────────────────────────────────────┐
│                    数字印刷机                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ HP12000     │  │ HP7900      │  │ Océ 6000    │         │
│  │ 750×530mm   │  │ 464×320mm   │  │ 330×488mm   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 热文件夹对接

**HP Indigo 系列**:
- 支持 HP Production Flow 热文件夹
- 监控目录: `\\Server2\客户文件2\out\`
- 自动检测新文件并触发打印

**Océ VarioPrint 6000**:
- 支持 Océ PRISMAproduction 热文件夹
- IP: 192.168.1.210
- 支持 JDF/JMF 工作传票

### 2.3 JDF/JMF 工作传票

```xml
<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" Type="Combined" ID="J001">
  <AuditPool>
    <Created Agent="QHI Processor" Timestamp="2026-06-20T12:00:00"/>
  </AuditPool>
  <MediaSheet MediaQuality="A4" Weight="157"/>
  <RunList>
    <FileSpec URL="file:///test.pdf"/>
  </RunList>
  <Component ID="C001" ComponentType="DigitalMedia"/>
</JDF>
```

### 2.4 自动化流程

1. **文件监控**: 监控热文件夹，检测新PDF文件
2. **预检**: 自动检查文件质量（DPI、色彩、出血等）
3. **拼版**: 根据纸张尺寸自动拼版
4. **输出**: 生成JDF工作传票，发送到印刷机
5. **状态跟踪**: 通过JMF接收印刷状态反馈

---

## 三、QHI与印刷机对接配置

### 3.1 设备配置

| 设备 | IP地址 | 接口 | 状态 |
|------|--------|------|------|
| HP12000 | 192.168.1.100 | JDF/JMF | 已配置 |
| HP7900 | 192.168.1.101 | JDF/JMF | 已配置 |
| Océ 6000 | 192.168.1.210 | JDF/JMF/Hot Folder | 已配置 |

### 3.2 热文件夹配置

```json
{
  "hot_folders": [
    {
      "name": "HP12000 Input",
      "path": "\\\\Server2\\客户文件2\\out\\hp12000",
      "printer": "HP12000",
      "auto_print": true
    },
    {
      "name": "HP7900 Input",
      "path": "\\\\Server2\\客户文件2\\out\\hp7900",
      "printer": "HP7900",
      "auto_print": true
    },
    {
      "name": "Oce 6000 Input",
      "path": "\\\\Server2\\客户文件2\\out\\oce6000",
      "printer": "Oce6000",
      "auto_print": true
    }
  ]
}
```

### 3.3 JDF模板

```xml
<?xml version="1.0" encoding="UTF-8"?>
<JDF xmlns="http://www.CIP4.org/JDFSchema_1_1" 
     Type="Combined" 
     ID="{job_id}"
     JobPartID="{job_part_id}">
  <AuditPool>
    <Created Agent="QHI Processor v1.3.0" 
             Timestamp="{timestamp}"/>
  </AuditPool>
  <MediaSheet MediaQuality="{paper_type}" 
              Weight="{weight_gsm}"
              Width="{width_mm}"
              Height="{height_mm}"/>
  <RunList>
    <FileSpec URL="{file_url}"/>
  </RunList>
  <Component ID="C001" 
             ComponentType="DigitalMedia"
             Pieces="{quantity}"/>
</JDF>
```

---

## 四、实施建议

### 4.1 短期（1-2周）

1. ✅ 设备参数配置完成
2. ✅ 热文件夹监控已实现
3. ✅ JDF/JMF基础对接已实现

### 4.2 中期（1个月）

1. 实现Océ VarioPrint 6000专用接口
2. 添加印刷状态实时反馈
3. 优化拼版算法适配各设备

### 4.3 长期（3个月）

1. 实现AI自动排产
2. 添加MES/ERP直连
3. 支持远程设备管理

---

**编制**: MiMo Code Agent
**日期**: 2026-06-20
