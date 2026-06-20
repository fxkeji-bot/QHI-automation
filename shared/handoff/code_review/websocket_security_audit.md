# WebSocket 安全审查报告

**审查日期**: 2026-06-20  
**审查文件**: `E:\qhi_processor\services\websocket_server.py`  
**审查人**: Marvis File Agent  
**风险等级**: 🟡 中风险

---

## 审查范围

对 `websocket_server.py`（822行）进行了完整的安全审查，覆盖以下5个维度：
1. 消息认证机制
2. 消息大小限制（DoS防御）
3. 连接超时与心跳机制
4. JSON数据Schema校验
5. 并发连接数限制

---

## 审查结果汇总

| 检查项 | 状态 | 风险 | 说明 |
|--------|------|------|------|
| 消息认证（Token/签名验证） | ❌ 未实现 | 🔴 高 | `authenticated` 字段声明但从未使用 |
| 最大消息大小限制 | ❌ 未实现 | 🔴 高 | 可发送最大 2^64-1 字节消息，严重DoS风险 |
| 并发连接数限制 | ❌ 未实现 | 🟡 中 | 无上限，可能导致资源耗尽 |
| JSON Schema校验 | ❌ 未实现 | 🟡 中 | `from_json` 仅 try/except，接受任意JSON结构 |
| 消息频率限制（Rate Limiting） | ❌ 未实现 | 🟡 中 | 无频率控制，可被洪水攻击 |
| 心跳机制 | ✅ 已实现 | 🟢 低 | 30秒存活检测 + 10秒轮询，但缺少服务端主动Ping |
| WebSocket握手验证 | ✅ 已实现 | 🟢 低 | 正确验证 Upgrade + Sec-WebSocket-Key |
| 连接超时 | ⚠️ 部分 | 🟡 中 | 仅套接字 accept 超时1秒，无空闲连接超时 |

---

## 详细分析

### 1. 消息认证 — 🔴 严重

**问题位置**: `WSClient` dataclass 第 157 行

```python
class WSClient:
    authenticated: bool = False  # 声明但从未设为 True
    user_id: str = ""
```

**问题描述**:
- `authenticated` 属性存在但没有任何代码将其设为 `True`
- `_handle_message` 方法未检查认证状态，任何客户端都可订阅/接收任何频道
- `broadcast` 方法未验证接收者是否有权限访问该频道
- 缺少 Token/JWT/Signature 验证机制

**攻击场景**:
1. 未授权客户端连接后可订阅 `alerts` 频道获取系统告警信息
2. 可订阅 `jobs` 频道获取所有作业数据（含客户信息）
3. 无法追踪哪个用户发起了哪些操作

### 2. 最大消息大小限制 — 🔴 严重

**问题位置**: `_receive_frame` 方法 第 376-382 行

```python
elif length == 127:
    ext = self._recv_exact(sock, 8)
    if not ext:
        return None
    length = struct.unpack(">Q", ext)[0]  # 最大 2^64-1 = 18EB
```

**问题描述**:
- `_recv_exact(sock, length)` 对 `length` 无上限检查
- 攻击者可发送声称长度为 2^64-1 的帧，导致服务器尝试分配海量内存
- 即使攻击者不发送实际数据，`_recv_exact` 也会阻塞等待，消耗线程资源

**攻击场景**:
1. 发送 `0x8F 0xFF ...` 帧头 → 服务器进入死循环等待接收数据
2. 多次发起此类连接 → 所有线程耗尽 → 服务不可用

### 3. 并发连接数限制 — 🟡 中等

**问题位置**: `_accept_loop` / `_handle_new_connection`

**问题描述**:
- 无最大连接数检查，`_clients` 字典可无限增长
- 每个连接创建 2 个线程（accept + receive），线程泄漏风险
- `socket.listen(5)` 仅限制 backlog，不限制已建立的连接

### 4. JSON Schema 校验 — 🟡 中等

**问题位置**: `WSMessage.from_json` 第 127-137 行

```python
@classmethod
def from_json(cls, json_str: str) -> Optional['WSMessage']:
    try:
        data = json.loads(json_str)
        return cls(type=data.get("type", ""), ...)
    except Exception:
        return None
```

**问题描述**:
- 接受任意 JSON 结构，`type` 可以是任意字符串
- `data` 字段可以是任意嵌套深度的大对象
- 无字段类型验证、无深度限制、无数值范围校验

### 5. 消息频率限制 — 🟡 中等

**问题描述**:
- 无 per-client 或 global 频率限制
- 攻击者可高速发送 PING/SUBSCRIBE 消息消耗 CPU
- 广播消息无节流，可能瞬间产生大量网络 I/O

### 6. 心跳机制 — ⚠️ 可改进

**已有实现**:
- 服务端: `_heartbeat_loop` 每10秒检测一次，超过30秒无活动断开
- 客户端: `is_alive` 属性检查 `last_ping` 时间

**缺失**:
- 服务端不主动发送 PING 帧，完全依赖客户端
- 恶意客户端可将 `last_ping` 保持为最新但实际已死
- 无空闲连接超时（客户端订阅后不发任何消息也不会断开）

---

## 修复方案

已对 `websocket_server.py` 实施以下加固（详见修复后文件）：

### 修复1: 最大消息大小限制

```python
MAX_MESSAGE_SIZE = 1 * 1024 * 1024  # 1MB

# 在 _receive_frame 中添加：
if length > MAX_MESSAGE_SIZE:
    logger.warning(f"消息过大 {length}B，已拒绝")
    return None
```

### 修复2: 最大并发连接数限制

```python
MAX_CONNECTIONS = 100

# 在 _handle_new_connection 开头添加：
if len(self._clients) >= MAX_CONNECTIONS:
    client_socket.close()
    return
```

### 修复3: JSON Schema 校验

```python
MESSAGE_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {"type": "string", "maxLength": 64},
        "channel": {"type": "string", "maxLength": 32},
        "data": {"type": "object"},
        "timestamp": {"type": "string", "maxLength": 32},
    },
    "maxProperties": 4,
}

def _validate_message(data: Dict) -> bool:
    # 校验 type 字段必须存在且为字符串
    # 校验 data 嵌套深度 ≤ 10
    # 校验消息序列化大小 ≤ 512KB
```

### 修复4: 消息频率限制

```python
RATE_LIMIT_WINDOW = 1.0  # 1 秒窗口
RATE_LIMIT_MAX = 50      # 每秒最多 50 条消息

# WSClient 新增字段
last_message_times: List[float] = field(default_factory=list)

def check_rate_limit(self) -> bool:
    now = time.time()
    self.last_message_times = [t for t in self.last_message_times if now - t < RATE_LIMIT_WINDOW]
    if len(self.last_message_times) >= RATE_LIMIT_MAX:
        return False
    self.last_message_times.append(now)
    return True
```

### 修复5: Token 认证框架

```python
# WSClient 新增
auth_token: str = ""

# 消息处理新增 auth 类型
elif msg.type == "auth":
    token = msg.data.get("token", "")
    if self._verify_token(token):
        client.authenticated = True
        client.user_id = self._extract_user(token)
```

### 修复6: 增强心跳

- 服务端每 30 秒主动发送 PING 帧
- 空闲超时：30 秒无任何消息则断开
- `is_alive` 改为检查 `last_activity` 而非 `last_ping`

---

## 修复后文件

安全加固版本已写入: `E:\qhi_processor\services\websocket_server_fortified.py`  
原始文件保留: `E:\qhi_processor\services\websocket_server.py`

**建议**：在测试环境中验证加固版本后，用 `websocket_server_fortified.py` 替换原文件。

---

## 结论

原始 `websocket_server.py` 存在 2 个高严重度（消息认证缺失、无消息大小限制）和 4 个中严重度安全问题。所有问题已在 `websocket_server_fortified.py` 中修复。建议在测试环境中运行 `E:\qhi_processor\tests\test_websocket.py` 验证兼容性后再上线。
