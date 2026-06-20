# HP Indigo DFE 认证配置说明

## 问题
`fleet_monitor.py` 调用 `create_hp_indigo_services()` 时未传入凭据，导致 `/jobs` 和 `/substrates` 端点返回 401。

## 修复内容
已修改 `services/fleet_monitor.py` 的 `FleetMonitor.__init__()` 方法：
1. 从环境变量读取 DFE 用户名/密码
2. 构建 `config` 字典传入 `create_hp_indigo_services(config)`

## 配置方式

### 方法一：环境变量（推荐）

在 Windows 系统中设置环境变量：

```powershell
# HP Indigo 12000 (192.168.1.38)
[Environment]::SetEnvironmentVariable("HP_INDIGO_192_168_1_38_USERNAME", "admin", "Machine")
[Environment]::SetEnvironmentVariable("HP_INDIGO_192_168_1_38_PASSWORD", "your_password", "Machine")

# HP Indigo 7900 (192.168.1.205)
[Environment]::SetEnvironmentVariable("HP_INDIGO_192_168_1_205_USERNAME", "admin", "Machine")
[Environment]::SetEnvironmentVariable("HP_INDIGO_192_168_1_205_PASSWORD", "your_password", "Machine")

# 热文件夹路径（可选）
[Environment]::SetEnvironmentVariable("HP_INDIGO_HOT_FOLDER", "\\192.168.1.38\hotfolder", "Machine")
```

### 方法二：DFE Web UI 创建 API 用户

1. 打开 DFE Web UI（http://192.168.1.38/ 或 http://192.168.1.205/）
2. 进入 **Settings → Users**
3. 创建新用户（如 `qhi_api`），权限：Operator 或 Admin
4. 使用创建的用户名/密码填入上述环境变量

### 方法三：JSESSIONID Cookie（如果已有登录会话）

如果已经在浏览器中登录了 DFE Web UI，可以提取 JSESSIONID cookie：

1. 打开浏览器开发者工具（F12）
2. 进入 **Application → Cookies**
3. 找到 `JSESSIONID` cookie 值
4. 在 `hp_indigo_service.py` 中手动设置 `self._session_cookie = "<JSESSIONID值>"`

> ⚠️ JSESSIONID 会过期，不推荐生产环境使用。

## 验证

配置完成后，运行 fleet_monitor 测试：

```bash
cd E:\qhi_processor
python services\fleet_monitor.py
```

查看日志输出：
- ✅ `HP 12000 轮询成功` — 认证成功
- ❌ `HP 12000 /jobs 需要认证凭据` — 凭据未配置或错误

## 凭据获取途径

如果不知道 DFE 用户名/密码：
1. 联系印刷机操作员或管理员
2. 在 DFE 触控屏 **Settings → Users** 中查看用户列表
3. DFE 默认管理员账号通常在安装时设置

## 当前状态

- ✅ `hp_indigo_service.py` — 认证逻辑已完成
- ✅ `fleet_monitor.py` — 凭据读取已修复
- 🔄 待配置 — 环境变量或 DFE 用户创建
- ⏳ 待测试 — 配置完成后运行 fleet_monitor 验证

---

*更新时间: 2026-06-21 01:45*
