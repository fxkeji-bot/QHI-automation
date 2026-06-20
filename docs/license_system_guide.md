---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: bc2a160e8b5d7cb83c2c331399e3f700_72adad9a6bcc11f18805525400d9a7a1
    ReservedCode1: L+o5w3l7pnOEmRxYEulsQv7AfsdH0Q48I2usHIjVRSptFmAEH4Urd/eVZiDfu/qq/U+GMz1g0E4fj4uDPVzQuAmAjPqVw5yY6qkC1pOIjS4SaKW+Ix7K/8uMSbF05OdDv8boHfqf++hEJLNs+UucILA2QV1ho1dIv/6sX89sGvW5bDf2uCvUVNWwp50=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: bc2a160e8b5d7cb83c2c331399e3f700_72adad9a6bcc11f18805525400d9a7a1
    ReservedCode2: L+o5w3l7pnOEmRxYEulsQv7AfsdH0Q48I2usHIjVRSptFmAEH4Urd/eVZiDfu/qq/U+GMz1g0E4fj4uDPVzQuAmAjPqVw5yY6qkC1pOIjS4SaKW+Ix7K/8uMSbF05OdDv8boHfqf++hEJLNs+UucILA2QV1ho1dIv/6sX89sGvW5bDf2uCvUVNWwp50=
---

# QHI 拼版处理器 — 授权系统使用说明

> 版本: v2.0  
> 最后更新: 2026-06-19

---

## 1. 概述

QHI 授权系统基于**机器码绑定 + 加密 License** 机制，防止未授权使用和源代码泄露。

### 核心特性

| 特性 | 说明 |
|------|------|
| **硬件指纹绑定** | 采集 CPU ID / 主板序列号 / 硬盘序列号 / 网卡 MAC，生成唯一机器码 |
| **AES-256-GCM 加密** | License 文件加密存储，防篡改；自动降级 HMAC-SHA256 |
| **功能位掩码** | 按位控制 PDFX / Trapping / Imposition / JDF / Color 五大模块开关 |
| **试用模式** | 首次启动自动 7 天/50 次启动试用 |
| **防篡改校验** | 核心模块文件散列监控，异常时记录日志告警 |
| **CLI 管理工具** | 命令行签发 License、查询状态、显示机器码 |

---

## 2. 功能权限位

| 位 | 常量 | 值 | 模块 |
|----|------|-----|------|
| 0 | `BIT_PDFX` | 1 | PDF/X 输出 |
| 1 | `BIT_TRAPPING` | 2 | 陷印引擎 |
| 2 | `BIT_IMPOSITION` | 4 | 拼版模块 |
| 3 | `BIT_JDF` | 8 | JDF 工作流 |
| 4 | `BIT_COLOR` | 16 | 色彩管理 |

**全部功能**: `31` (1+2+4+8+16)  
**试用期开放**: PDFX + Imposition (值 `5`)

---

## 3. 文件说明

| 文件 | 用途 |
|------|------|
| `services/license_manager.py` | 授权管理核心模块 |
| `config/license.key` | 加密的 License 文件（自动生成） |
| `config/.machine_id` | 机器码缓存 |
| `config/.trial_data` | 试用信息（加密存储） |
| `config/.integrity_baseline` | 文件完整性基准散列 |
| `logs/integrity.log` | 防篡改告警日志 |

---

## 4. 命令行工具

### 4.1 显示机器码

```bash
python services/license_manager.py --show
```

输出示例:
```
机器码: A1B2C3D4E5F6A7B8
状态: trial
剩余天数: 5
```

### 4.2 验证当前 License 状态

```bash
python services/license_manager.py --verify
```

输出 JSON 格式的完整状态信息。

### 4.3 签发 License（管理员）

```bash
python services/license_manager.py --generate \
    --machine-code A1B2C3D4E5F6A7B8 \
    --customer "XX印刷厂" \
    --expiry 2026-12-31 \
    --features 31
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--machine-code` | 是 | 目标机器码（16 位十六进制） |
| `--customer` | 否 | 客户名称 |
| `--expiry` | 是 | 过期日期（YYYY-MM-DD） |
| `--features` | 否 | 功能位掩码，默认 31（全部） |

生成后 License 写入 `config/license.key`。将该文件分发给客户，放置到客户机器的 `E:\qhi_processor\config\license.key` 即可激活。

---

## 5. 集成到代码

### 5.1 启动验证

```python
from services.license_manager import LicenseManager

# 在 main() 开头调用（会在未授权时弹出对话框并退出）
LicenseManager.verify_on_startup()
```

### 5.2 功能权限检查

```python
from services.license_manager import LicenseManager, FeatureBit

if LicenseManager.is_feature_enabled(FeatureBit.BIT_TRAPPING):
    ...  # 陷印功能可用
```

### 5.3 获取机器码

```python
code = LicenseManager.get_machine_code()
```

---

## 6. 安全机制

### 6.1 加密方案

```
version(1B) | salt(16B) | encrypted_data
```

- **首选**: AES-256-GCM（需 `cryptography` 库）
- **降级**: HMAC-SHA256 流加密 + 认证标签
- **密钥派生**: PBKDF2-HMAC-SHA256 (200,000 轮)

### 6.2 防篡改

对以下文件进行 SHA256 散列监控：
- `services/license_manager.py`
- `main.py`
- `core/config.py`

首次运行自动建立基准，后续校验不匹配时写入 `logs/integrity.log`，**不阻止程序运行**（避免误杀）。

### 6.3 机器码稳定性

- WMIC 不可用时（如精简版 Windows），自动降级使用 `uuid.getnode()` + 系统信息
- 机器码写入 `config/.machine_id` 缓存，避免每次重新采集

---

## 7. 环境变量

| 变量 | 说明 |
|------|------|
| `QHI_LICENSE_SECRET` | 自定义加密密钥（生产环境必须设置） |

未设置时使用内置派生密钥，**生产环境务必通过环境变量注入独立密钥**。

---

## 8. 故障排查

| 问题 | 可能原因 | 解决 |
|------|----------|------|
| "设备不匹配" | License 绑定的机器码与当前设备不同 | 获取当前机器码重新签发 |
| "授权文件异常" | License 文件损坏或被篡改 | 删除 `config/license.key` 重新激活 |
| License 生成失败 | 机器码格式不对 | 确认 16 位十六进制，无连字符 |
| 试用无法启动 | 试用过期或次数用完 | 联系管理员获取正式 License |
| 防篡改编造告警 | 核心文件被正常更新 | 删除 `config/.integrity_baseline` 重新建立基准 |
*（内容由AI生成，仅供参考）*
