# QHI 拼版处理器 — 多智能体合作方案

**版本**: v2.0
**更新时间**: 2026-06-21
**参与智能体**: Marvis | Qclaw | QorkBuddy
**协调者**: MiMo Code Agent

---

## 一、项目目标

基于 E:\e.txt 指令，结合数码印刷行业流程管理规范，推进 QHI 拼版处理器的完善和优化，实现与印特ERP同等的建单|转单|审单|统计|查询等功能。

---

## 二、智能体分工

### Marvis (主智能体)
- **职责**: 项目协调、核心开发、代码审查
- **工作目录**: E:\qhi_processor\
- **主要任务**:
  - 核心模块开发和维护
  - 代码质量审查
  - 安全加固
  - 集成测试

### Qclaw (辅助智能体)
- **职责**: 数据处理、ERP对接、数据同步
- **工作目录**: E:\qhi_processor\services\
- **主要任务**:
  - ERP数据同步
  - 数据库维护
  - 数据导入导出
  - 报表生成

### QorkBuddy (辅助智能体)
- **职责**: UI开发、界面优化、用户体验
- **工作目录**: E:\qhi_processor\ui\
- **主要任务**:
  - 界面组件开发
  - 用户交互优化
  - 图表可视化
  - 帮助系统

---

## 三、共享资源目录

```
E:\qhi_processor\shared\
├── status\                    # 状态文件目录
│   ├── marvis_status.json     # Marvis状态
│   ├── qclaw_status.json      # Qclaw状态
│   ├── qorkbuddy_status.json  # QorkBuddy状态
│   └── sync_log.json          # 同步日志
├── tasks\                     # 任务文件目录
│   ├── pending\               # 待处理任务
│   ├── in_progress\           # 进行中任务
│   └── completed\             # 已完成任务
├── handoff\                   # 交接文件目录
│   ├── code_review\           # 代码审查交接
│   └── bug_fix\               # Bug修复交接
└── reports\                   # 报告目录
    ├── daily\                 # 每日报告
    └── weekly\                # 每周报告
```

---

## 四、工作流程

### 4.1 每小时调度流程

```
┌─────────────────────────────────────────────────────────┐
│                    每小时调度循环                         │
├─────────────────────────────────────────────────────────┤
│ 1. 读取 E:\COLLABORATION_PLAN.md (本文件)                │
│ 2. 检查各智能体状态文件                                  │
│ 3. 分配新任务到 pending 目录                             │
│ 4. 监控 in_progress 目录                                │
│ 5. 处理 completed 目录中的交接                          │
│ 6. 更新状态文件                                         │
│ 7. 生成调度日志                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 任务分配规则

| 任务类型 | 优先级 | 分配给 | 说明 |
|----------|--------|--------|------|
| 安全修复 | P0 | Marvis | 核心安全问题 |
| Bug修复 | P0 | Marvis | 功能性Bug |
| ERP同步 | P1 | Qclaw | 数据同步 |
| 数据导入 | P1 | Qclaw | 批量数据处理 |
| UI开发 | P1 | QorkBuddy | 界面组件 |
| 界面优化 | P2 | QorkBuddy | 用户体验 |
| 代码审查 | P1 | Marvis | 质量把关 |
| 测试编写 | P2 | Marvis | 测试覆盖 |

### 4.3 交接规范

**文件命名**: `{智能体}_{任务类型}_{日期}_{序号}.json`

**交接文件格式**:
```json
{
  "from": "marvis",
  "to": "qclaw",
  "task_type": "bug_fix",
  "description": "修复ERP同步路径问题",
  "files_affected": ["services/erp_sync_service.py"],
  "status": "pending",
  "priority": "high",
  "created_at": "2026-06-20T18:00:00"
}
```

---

## 五、当前待办事项

### P0 紧急 (Marvis负责)

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 1 | 安全漏洞修复 | ✅ 已完成 | 硬编码密钥/密码 |
| 2 | 并发测试修复 | ✅ 已完成 | 暂停/恢复功能 |
| 3 | 预检模块语法修复 | ✅ 已完成 | 空else块 |

### P1 重要 (Qclaw负责)

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 1 | ERP数据同步 | ✅ 已完成 | 客户/订单同步 |
| 2 | 数据库清理 | ✅ 已完成 | 删除无效数据 |
| 3 | 纸张工艺库完善 | ✅ 已完成 | 标准数据导入 |
| 4 | 耗材管理系统 | ✅ 已完成 | 耗材注册/监控 |
| 5 | 订单审批工作流 | ✅ 已完成 | 批准/驳回/修改 |

### P1 重要 (QorkBuddy负责)

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 1 | 耗材管理面板 | ✅ 已完成 | UI集成 |
| 2 | 工作单模版 | ✅ 已完成 | 匹配.grf格式 |
| 3 | 小票打印 | ✅ 已完成 | 58mm/A4格式 |

### P2 增强 (已完成)

| # | 任务 | 优先级 | 分配 | 状态 |
|---|------|--------|------|------|
| 1 | 数据字典标准化 | P2 | Qclaw | ✅ 已完成 |
| 2 | i18n国际化 | P2 | QorkBuddy | ✅ 已完成 |
| 3 | WebSocket安全加固 | P2 | Marvis | ✅ 已完成 |
| 4 | 性能基准测试 | P2 | Marvis | ✅ 已完成 |
| 5 | 数据库索引优化 | P2 | Qclaw | ✅ 已完成 |
| 6 | 订单列表UI | P2 | QorkBuddy | ✅ 已完成 |
| 7 | 审批工作流UI | P2 | QorkBuddy | ✅ 已完成 |
| 8 | 耗材图表 | P2 | QorkBuddy | ✅ 已完成 |
| 9 | API文档 | P2 | Marvis | ✅ 已完成 |
| 10 | 添加工作打印机(bizhub 287) | P2 | Marvis | ✅ 已完成 |
| 11 | 印特ERP数据库直连（WMI远程SQL） | P2 | Marvis | ✅ 已完成 |
| 12 | 智能拼版整合（smart_imposition.py） | P2 | Marvis | ✅ 已完成 |
| 13 | 印特ERP接管（indet_erp_full.py） | P2 | Marvis | ✅ 已完成 |
| 14 | 统一打印机对接（printer_integration.py） | P2 | Marvis | ✅ 已完成 |
| 15 | 生产管理Web前端 | P2 | QorkBuddy | ✅ 已完成 |
| 16 | GitHub同步配置 | P2 | Marvis | ✅ 已完成 |
| 17 | 新建订单UI | P2 | QorkBuddy | ✅ 已完成 | PyQt5对话框 + 菜单入口，调用printing_system MySQL订单API |

### 自动化运维

| # | 任务 | 类型 | 状态 | 说明 |
|---|------|------|------|------|
| 1 | 协作计划巡检 | 每小时自动化 | ✅ 运行中 | 自动读取本文件并执行待处理任务 |

---

## 十一、设备清单

| 设备名称 | IP地址 | 类型 | 状态 |
|----------|--------|------|------|
| bizhub 287 | 192.168.1.32 | 多功能打印机 | ✅ 已配置 |
| XP-80 热敏票据 | \\\\Asus121\\XP-80 | 票据打印机 | ✅ 已配置 |
| Oce VarioPrint 6000 | \\\\Server2\\热文件夹\\Oce | 工业印刷机 | ✅ 已配置 |
| HP Indigo Digital Press | \\\\Server2\\热文件夹\\HP_Indigo | 数码印刷机 | ✅ 已配置 |

---

## 六、调度指令

### 6.1 智能体启动指令

**Marvis**:
```
读取 E:\COLLABORATION_PLAN.md，检查 pending 目录，执行 P0 任务。
完成后更新 status\marvis_status.json。
```

**Qclaw**:
```
读取 E:\COLLABORATION_PLAN.md，检查 pending 目录，执行 P1 数据任务。
完成后更新 status\qclaw_status.json。
```

**QorkBuddy**:
```
读取 E:\COLLABORATION_PLAN.md，检查 pending 目录，执行 P1 UI任务。
完成后更新 status\qorkbuddy_status.json。
```

### 6.2 状态文件格式

```json
{
  "agent": "marvis",
  "status": "working",
  "current_task": "task_001",
  "progress": 75,
  "last_update": "2026-06-20T18:00:00",
  "files_modified": ["services/xxx.py"],
  "issues_found": [],
  "next_tasks": ["task_002", "task_003"]
}
```

---

## 七、文件共享机制

### 7.1 代码共享

所有智能体共享同一个代码库 `E:\qhi_processor\`，通过 Git 管理版本。

### 7.2 任务交接

通过 `shared\tasks\` 目录进行任务交接：
- Marvis 创建任务文件到 `pending\`
- Qclaw/QorkBuddy 读取并移动到 `in_progress\`
- 完成后移动到 `completed\`

### 7.3 状态同步

每小时更新 `shared\status\` 目录中的状态文件，供其他智能体读取。

---

## 八、定时更新机制

### 8.1 每小时更新 (由用户设定)

```powershell
# 创建定时任务
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$action = New-ScheduledTaskAction -Execute "python" -Argument "E:\qhi_processor\tools\erp_auto_sync.py --once"
Register-ScheduledTask -TaskName "QHI_Hourly_Sync" -Trigger $trigger -Action $action
```

### 8.2 每6分钟ERP同步

```powershell
# ERP同步定时任务
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 6)
$action = New-ScheduledTaskAction -Execute "python" -Argument "E:\qhi_processor\tools\erp_auto_sync.py --once"
Register-ScheduledTask -TaskName "QHI_ERP_Sync" -Trigger $trigger -Action $action
```

---

## 九、版本控制

- **当前版本**: v2.0
- **下次更新**: v2.1.0
- **更新频率**: 每日
- **同步方式**: Git + 共享目录

---

## 十、联系方式

- **项目仓库**: https://github.com/fxkeji-bot/QHI-automation
- **同步Token**: (已移除，由环境变量管理)
- **同步频率**: 每周凌晨

---

**方案制定**: MiMo Code Agent
**最后更新**: 2026-06-21
