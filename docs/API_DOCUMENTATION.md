# QHI 拼版处理器 API 文档

**版本**: v2.0  
**基础URL**: http://127.0.0.1:18900  
**认证**: JWT Bearer Token

---

## 认证

### POST /api/v2/auth/login
用户登录获取JWT令牌

**请求体**:
```json
{
  "username": "string",
  "password": "string"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "token": "string",
    "username": "string",
    "expires_in": 86400
  }
}
```

### GET /api/v2/auth/profile
获取当前用户信息（需要认证）

---

## 系统

### GET /api/v2/health
健康检查

### GET /api/v2/info
API信息

### GET /api/v2/stats
系统统计

---

## 作业管理

### GET /api/v2/jobs
获取作业列表

**查询参数**:
- `status`: 筛选状态 (pending/processing/completed/failed)
- `limit`: 返回数量限制

### POST /api/v2/jobs
提交单个作业

**请求体**:
```json
{
  "name": "string",
  "file_path": "string",
  "priority": "normal"
}
```

### POST /api/v2/jobs/batch
批量提交作业

**请求体**:
```json
{
  "jobs": [
    {"name": "string", "file_path": "string"}
  ]
}
```

### GET /api/v2/jobs/stats
获取队列统计

### GET /api/v2/jobs/dead-letter
获取死信队列

### GET /api/v2/jobs/{job_id}
获取作业详情

### POST /api/v2/jobs/{job_id}/cancel
取消作业

### POST /api/v2/jobs/{job_id}/retry
重试作业

---

## 设备管理

### GET /api/v2/devices
获取设备列表

### POST /api/v2/devices
注册新设备

**请求体**:
```json
{
  "name": "string",
  "device_type": "digital_printer",
  "manufacturer": "string",
  "model": "string"
}
```

### PUT /api/v2/devices/{device_id}/status
更新设备状态

**请求体**:
```json
{
  "status": "idle|running|error",
  "message": "string"
}
```

---

## VDP可变数据

### GET /api/v2/vdp/templates
获取VDP模板列表

### POST /api/v2/vdp/templates
创建VDP模板

**请求体**:
```json
{
  "name": "string",
  "template_file": "string",
  "fields": [],
  "pages": []
}
```

### POST /api/v2/vdp/jobs
提交VDP作业

**请求体**:
```json
{
  "template_id": "string",
  "data_source": "string",
  "name": "string"
}
```

---

## 预检

### POST /api/v2/preflight/check
执行PDF预检

**请求体**:
```json
{
  "file_path": "string",
  "config": {}
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "total_checks": 15,
    "passed_checks": 12,
    "warning_count": 2,
    "error_count": 1,
    "issues": []
  }
}
```

---

## 色彩管理

### POST /api/v2/color/convert
色彩空间转换

**请求体**:
```json
{
  "color": {
    "space": "rgb",
    "values": [255, 0, 0]
  },
  "target_space": "cmyk"
}
```

### GET /api/v2/color/spot/search
搜索专色

**查询参数**:
- `query`: 搜索关键词

### GET /api/v2/color/spot/{name}
获取专色详情

---

## 订单管理

### GET /api/v2/orders
获取订单列表

### POST /api/v2/orders
创建订单

**请求体**:
```json
{
  "customer_name": "string",
  "items": [
    {"name": "string", "quantity": 1, "price": 0.0}
  ]
}
```

### GET /api/v2/orders/{order_id}
获取订单详情

---

## Webhook

### POST /api/v2/webhooks
注册Webhook

**请求体**:
```json
{
  "url": "string",
  "events": ["job.completed", "job.failed"],
  "secret": "string"
}
```

### GET /api/v2/webhooks
获取Webhook列表

### DELETE /api/v2/webhooks/{webhook_id}
删除Webhook

### POST /api/v2/webhooks/{webhook_id}/test
测试Webhook

---

## 错误响应

```json
{
  "success": false,
  "error": "error_code",
  "message": "错误描述"
}
```

**常见错误码**:
- `400`: 请求参数错误
- `401`: 未认证
- `403`: 无权限
- `404`: 资源不存在
- `429`: 请求过于频繁
- `503`: 服务不可用

---

**生成时间**: 2026-06-20
