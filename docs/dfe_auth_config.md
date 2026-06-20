# HP Indigo DFE 认证配置说明

## 凭据信息

| 设备 | IP | 主机名 | DFE 版本 | 用户名 | 密码 |
|------|-----|--------|---------|--------|------|
| HP Indigo 12000 | 192.168.1.38 | HP-120K | 8.3.0 | administrator | HPdfeHpDfe#1 |
| HP Indigo 7900 | 192.168.1.205 | HP-PRO | 8.0.1 | administrator | HPdfeHpDfe#1 |

## 认证机制分析

DFE REST API 使用 **Java 会话认证**（JSESSIONID cookie）：
- 公开端点（无需认证）：`/prodflow/rest/onlinehelp/about`、`/prodflow/rest/product`
- 私有端点（需认证）：`/prodflow/rest/jobs`、`/prodflow/rest/substrates`
- 401 响应：`{"desc":"No authenticated user associated with Session(...)","code":401,"id":"UNAUTHORIZED"}`

## 当前状态

- [x] 凭据已记录到 `hp_indigo_service.py`
- [x] Basic Auth 探测 → 401（DFE 不接受 Basic Auth）
- [x] 登录端点探测 → 常见路径均 404
- [ ] **待解决**：DFE 会话认证需要在浏览器中先登录

## 解决方案（3选1）

### 方案A：浏览器先登录（最简单）
1. 在 QHI 服务器上打开浏览器访问 `http://192.168.1.38/dfe/`
2. 使用 `administrator` / `HPdfeHpDfe#1` 登录
3. 登录后，同一浏览器的 REST API 请求会自动带 JSESSIONID cookie
4. **限制**：QHI 服务（后台 Python）无法共享浏览器 cookie

### 方案B：配置 DFE 启用 API Key 认证
某些 DFE 版本支持配置 API Key（需在 DFE 设置中启用）
- 查阅 DFE 8.3.0 用户手册 → REST API 认证章节
- 或联系 HP 支持获取 DFE REST API 认证配置方法

### 方案C：通过 JDF/JMF 替代 REST API（推荐）
DFE 支持通过 JDF 文件提交作业（无需 REST API 认证）：
- 将 JDF 作业描述文件放入 DFE 热文件夹
- DFE 自动监听热文件夹并处理作业
- `services/hotfolder_dispatcher.py` 已实现此功能

## 下一步

- [ ] 用户确认选择的认证方案
- [ ] 如选方案A：在 DFE 服务器上登录 Web UI，然后测试 API
- [ ] 如选方案B：查阅 DFE 文档，配置 API Key
- [ ] 如选方案C（推荐）：使用热文件夹方式，绕过 REST API 认证问题

## 探测记录

```
[2026-06-20 20:30] Basic Auth → 401
[2026-06-20 20:30] POST /prodflow/rest/jobs → 405 (Method Not Allowed)
[2026-06-20 20:30] GET /prodflow/rest/session → 404
[2026-06-20 20:30] GET /prodflow/rest/login → 404
[2026-06-20 20:30] DFE Web UI (/dfe/) → 200 (YUI framework, 无登录表单)
```

## 文件位置

- DFE 服务代码：`E:\qhi_processor\services\hp_indigo_service.py`
- 热文件夹调度器：`E:\qhi_processor\services\hotfolder_dispatcher.py`
- 设备管理器：`E:\qhi_processor\services\device_manager.py`
