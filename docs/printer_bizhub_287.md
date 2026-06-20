# Konica Minolta bizhub 287 — QHI 机队设备档案

**设备 ID**: `bizhub_287`
**添加日期**: 2026-06-20
**状态**: 已接入

---

## 一、基本信息

| 项目 | 值 |
|------|-----|
| 品牌 | Konica Minolta |
| 型号 | bizhub 287 |
| 类型 | A3 黑白多功能复合机 |
| IP 地址 | 192.168.1.32 |
| 主机名 | bizhub-287 |
| Web 管理 | PageScope Web Connection (端口 80) |
| SNMP | v1 / v2c / v3 (Community: `public`) |
| OpenAPI | 支持（KM SDK） |

## 二、技术规格

| 项目 | 规格 |
|------|------|
| A4 打印速度 | 28 ppm |
| A3 打印速度 | 14 ppm |
| 打印分辨率 | 1800 dpi (等效) × 600 dpi |
| 扫描分辨率 | 600 × 600 dpi |
| 最大月印量 | 30,000 页 |
| 推荐月印量 | 2,000 ~ 5,000 页 |
| 预热时间 | ≤ 20 秒 |
| 首页输出 | 5.3 秒（黑白） |
| 纸张容量（标准） | 纸盒 1+2: 500×2 + 旁路: 100 张 |
| 幅面 | A6 ~ SRA3 (320 × 450 mm) |
| 纸张重量 | 60 ~ 300 g/m² |

## 三、工作流协议

| 协议 | 支持 | 备注 |
|------|------|------|
| LPR | ✓ | 端口 515，队列名 `PRINT` |
| IPP | ✓ | IPP 1.1 / IPP over SSL |
| SMB | ✓ | 扫描到 SMB（可能需启用 SMB v1） |
| 热文件夹 | △ | 需 KM Printer Driver Utility（PC 端软件） |
| SNMP | ✓ | v1/v2c/v3，Printer-MIB + KM 私有 MIB |
| OpenAPI | ✓ | KM 嵌入式 SDK |
| Web 服务器 | ✓ | PageScope Web Connection (HTTP:80) |

## 四、在 QHI 中的角色

- **编号**: QHI 机队 4 号设备
- **接入方式**: LPR 直投（因 bizhub 287 无原生 SMB 热文件夹）
- **监控方式**: Ping + HTTP (PageScope) + SNMP
- **适用场景**: 小批量黑白打印、内部文档、打样校样

## 五、模块对应

| 模块 | 文件 |
|------|------|
| 设备服务 | `services/bizhub_service.py` |
| 调度器配置 | `services/hotfolder_dispatcher.py` (PRINTER_CONFIG) |
| 机队监控 | `services/fleet_monitor.py` |
| 看板数据 | `docs/qhi_tracker/order_data.json` |

## 六、变更记录

| 日期 | 内容 |
|------|------|
| 2026-06-20 | 新建档案，bizhub 287 接入 QHI 机队 |
