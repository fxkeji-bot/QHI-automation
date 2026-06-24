// QHI Web - 主应用逻辑 v2 (图表+自动刷新+数据精确映射)
import api from './api.js';
import { BarChart, HorizontalBarChart, LineChart, PieChart, DonutChart, createStatusBadge, formatCurrency, formatNumber } from './charts.js';

const FN = {'10':'排队','15':'审单中','20':'前期','21':'机房','30':'后道','35':'外发','45':'完工','65':'寄快递','70':'未付'};
const FC = {'10':'#64748b','15':'#eab308','20':'#3b82f6','21':'#8b5cf6','30':'#ec4899','35':'#f97316','45':'#22c55e','65':'#06b6d4','70':'#ef4444'};
const REFRESH_MS = 60000;

class QHIApp {
  constructor() {
    this.currentRoute = '';
    this._refreshTimer = null;
    this.init();
  }

  async init() {
    window.addEventListener('hashchange', () => this.handleRoute());
    this.setupNav();
    this.startClock();
    this.startHealthCheck();
    this.handleRoute();
    this._refreshTimer = setInterval(() => this.refreshCurrentPage(), REFRESH_MS);
  }

  setupNav() {
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => { window.location.hash = item.dataset.route; });
    });
  }

  startClock() {
    const el = document.getElementById('current-time');
    const tick = () => { if (el) el.textContent = new Date().toLocaleString('zh-CN'); };
    tick(); setInterval(tick, 1000);
  }

  startHealthCheck() {
    const el = document.getElementById('connection-status');
    const check = async () => {
      try {
        await api.health();
        el.innerHTML = '<span class="status-dot online"></span>已连接';
        el.className = 'connection-status ok';
      } catch (e) {
        el.innerHTML = '<span class="status-dot offline"></span>连接断开';
        el.className = 'connection-status err';
      }
    };
    check(); setInterval(check, 30000);
  }

  handleRoute() {
    const hash = window.location.hash.slice(1) || '/dashboard';
    this.currentRoute = hash;
    document.querySelectorAll('.nav-item').forEach(i => i.classList.toggle('active', i.dataset.route === hash));
    this.loadPage(hash);
  }

  async loadPage(route) {
    const c = document.getElementById('main-content');
    c.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
      switch (route) {
        case '/dashboard': await this.renderDashboard(c); break;
        case '/orders': await this.renderOrders(c); break;
        case '/customers': await this.renderCustomers(c); break;
        case '/stats': await this.renderStats(c); break;
        case '/printers': await this.renderPrinters(c); break;
        default: await this.renderDashboard(c);
      }
    } catch (err) {
      c.innerHTML = '<div class="empty-state"><div class="empty-icon">!</div><p>加载失败: ' + err.message + '</p><button class="btn btn-primary" onclick="location.reload()" style="margin-top:12px">重试</button></div>';
    }
  }

  refreshCurrentPage() { this.loadPage(this.currentRoute); }

  // ===== 仪表盘 =====
  async renderDashboard(c) {
    const [dash, ordersResp, dist, revResp, printerResp] = await Promise.all([
      api.getDashboard(), api.getOrders(10), api.getFlowDistribution(),
      api.getMonthlyRevenue(), api.getPrinterStatus()
    ]);
    const orders = ordersResp.orders || [];
    const printers = printerResp.printers || [];

    c.innerHTML =
      '<div class="kpi-grid">' +
        this._kpi('今日订单', formatNumber(dash.today_orders), '📋', 'blue') +
        this._kpi('在制工单', formatNumber(dash.in_progress), '⏳', 'orange') +
        this._kpi('完工', formatNumber(dash.completed), '✅', 'green') +
        this._kpi('今日营收', formatCurrency(dash.today_revenue), '💰', 'purple') +
      '</div>' +
      '<div class="charts-grid">' +
        '<div class="card"><div class="card-header"><h3 class="card-title">流程分布</h3></div><div id="dist-chart"></div></div>' +
        '<div class="card"><div class="card-header"><h3 class="card-title">月度营收趋势</h3></div><div id="rev-chart"></div></div>' +
      '</div>' +
      '<div class="card"><div class="card-header"><h3 class="card-title">最近工单</h3><a class="btn btn-sm" href="#/orders">查看全部</a></div>' +
        '<div class="table-container"><table><thead><tr><th>工单号</th><th>客户</th><th>产品</th><th>状态</th><th>金额</th><th>日期</th></tr></thead>' +
        '<tbody>' + orders.slice(0, 8).map(o =>
          '<tr onclick="app.showOrderDetail(\'' + o.Code + '\')" style="cursor:pointer">' +
          '<td>' + o.Code + '</td><td>' + (o.Acc4CustomerName||'-') + '</td>' +
          '<td>' + (o.Title||'-').substring(0, 20) + '</td><td>' + createStatusBadge(o.ProduceFlowSpecCode) + '</td>' +
          '<td>' + formatCurrency(o.StandardAmount) + '</td><td>' + (o.Sys4CreateTime||'').substring(0, 10) + '</td></tr>'
        ).join('') + '</tbody></table></div></div>' +
      '<div class="card"><div class="card-header"><h3 class="card-title">打印机状态</h3><a class="btn btn-sm" href="#/printers">监控</a></div>' +
        '<div class="printer-grid">' + printers.map(p =>
          '<div class="printer-card printer-' + (p.online?'online':'offline') + '">' +
          '<div class="printer-status ' + (p.online?'online':'offline') + '"></div>' +
          '<div class="printer-name">' + p.name + '</div><div class="printer-type">' + p.type + '</div></div>'
        ).join('') + '</div></div>';

    // Flow distribution bar chart
    const distData = Object.entries(dist.distribution || {}).map(([k, v]) => ({
      label: v.name || FN[k] || k, value: v.count || 0, color: FC[k] || '#64748b'
    }));
    new BarChart('#dist-chart', distData);

    // Monthly revenue line chart
    const revData = (revResp.monthly || []).map(m => ({ label: m.month, value: parseFloat(m.revenue) || 0 }));
    new LineChart('#rev-chart', revData);
  }

  _kpi(label, value, icon, color) {
    return '<div class="kpi-card"><div class="kpi-icon ' + color + '">' + icon + '</div><div class="kpi-content"><div class="kpi-label">' + label + '</div><div class="kpi-value">' + value + '</div></div></div>';
  }

  // ===== 工单管理 =====
  async renderOrders(c) {
    const resp = await api.getOrders(200);
    const orders = resp.orders || [];

    c.innerHTML =
      '<div class="toolbar">' +
        '<input type="text" class="search-input" id="order-search" placeholder="搜索工单号/客户名/产品...">' +
        '<select class="filter-select" id="status-filter"><option value="">全部状态</option>' +
        Object.entries(FN).map(([k,v]) => '<option value="'+k+'">'+v+'</option>').join('') + '</select>' +
        '<button class="btn btn-primary" onclick="app.showCreateOrderModal()">+ 新建工单</button>' +
      '</div>' +
      '<div class="card"><div class="table-container"><table id="orders-table"><thead><tr>' +
        '<th>工单号</th><th>客户</th><th>产品</th><th>状态</th><th>金额</th><th>日期</th><th>操作</th>' +
      '</tr></thead><tbody>' +
      orders.map(o =>
        '<tr data-code="' + o.Code + '" data-flow="' + o.ProduceFlowSpecCode + '">' +
        '<td>' + o.Code + '</td><td>' + (o.Acc4CustomerName||'-') + '</td>' +
        '<td title="' + (o.Title||'') + '">' + (o.Title||'-').substring(0, 25) + '</td>' +
        '<td>' + createStatusBadge(o.ProduceFlowSpecCode) + '</td>' +
        '<td>' + formatCurrency(o.StandardAmount) + '</td>' +
        '<td>' + (o.BusiDate||'').substring(0, 10) + '</td>' +
        '<td><button class="btn btn-sm" onclick="app.showOrderDetail(\'' + o.Code + '\')">详情</button></td></tr>'
      ).join('') + '</tbody></table></div></div>' +
      '<div class="toolbar" style="color:#94a3b8;font-size:13px;" id="pagination-info">共 ' + orders.length + ' 条记录</div>';

    const sEl = document.getElementById('order-search');
    const fEl = document.getElementById('status-filter');
    const filter = () => {
      const s = (sEl.value||'').toLowerCase(), f = fEl.value;
      let n = 0;
      document.querySelectorAll('#orders-table tbody tr').forEach(r => {
        const ok = (!s || r.textContent.toLowerCase().includes(s)) && (!f || r.dataset.flow === f);
        r.style.display = ok ? '' : 'none'; if (ok) n++;
      });
      document.getElementById('pagination-info').textContent = '显示 ' + n + '/' + orders.length + ' 条';
    };
    sEl.addEventListener('input', filter);
    fEl.addEventListener('change', filter);
  }

  async showOrderDetail(code) {
    try {
      const resp = await api.getOrderDetail(code);
      const o = resp.order || {};
      const records = resp.flow_records || [];
      const details = resp.details || [];
      const sidebar = document.getElementById('detail-sidebar');
      const content = document.getElementById('detail-content');

      let html = '<div class="detail-section"><h4>基本信息</h4>';
      const fields = [
        ['工单号', o.Code], ['客户', o.Acc4CustomerName], ['产品', o.Title],
        ['状态', createStatusBadge(o.ProduceFlowSpecCode)], ['金额', formatCurrency(o.StandardAmount)],
        ['日期', (o.BusiDate||'').substring(0,10)], ['创建时间', (o.Sys4CreateTime||'').substring(0,19)],
        ['备注', o.Remark || '-']
      ];
      fields.forEach(([l, v]) => {
        html += '<div class="detail-row"><span class="detail-label">' + l + '</span><span class="detail-value">' + (v||'-') + '</span></div>';
      });
      html += '</div>';

      if (records.length > 0) {
        html += '<div class="detail-section"><h4>流程记录 (' + records.length + '条)</h4>';
        records.forEach(r => {
          const name = FN[r.ProduceFlowSpecCode] || r.ProduceFlowSpecCode;
          const color = FC[r.ProduceFlowSpecCode] || '#64748b';
          html += '<div class="flow-record"><span class="badge" style="background:' + color + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">' + name + '</span>' +
            '<span style="color:#94a3b8;font-size:12px;">' + (r.Sys4CreateTime||'') + '</span>' +
            '<span style="font-size:12px;">' + (r.Remark||'') + '</span></div>';
        });
        html += '</div>';
      }

      content.innerHTML = html;
      sidebar.classList.add('active');
    } catch (e) { alert('加载详情失败: ' + e.message); }
  }

  // ===== 客户管理 =====
  async renderCustomers(c) {
    const [topResp, listResp] = await Promise.all([api.getTopCustomers(), api.getCustomers()]);
    const top = topResp.customers || [];
    const list = listResp.customers || [];

    c.innerHTML =
      '<div class="charts-grid">' +
        '<div class="card"><div class="card-header"><h3 class="card-title">TOP客户排行</h3></div><div id="top-chart"></div></div>' +
        '<div class="card"><div class="card-header"><h3 class="card-title">客户订单分布</h3></div><div id="cust-pie"></div></div>' +
      '</div>' +
      '<div class="card" style="margin-top:16px;"><div class="card-header"><h3 class="card-title">客户列表 (' + list.length + ')</h3></div>' +
        '<div class="toolbar"><input type="text" class="search-input" id="cust-search" placeholder="搜索客户名称..."></div>' +
        '<div class="table-container"><table id="cust-table"><thead><tr><th>编码</th><th>名称</th></tr></thead>' +
        '<tbody>' + list.map(cu => '<tr><td>' + cu.code + '</td><td>' + cu.name + '</td></tr>').join('') + '</tbody></table></div></div>';

    // Horizontal bar chart for top customers
    const chartData = top.slice(0, 10).map(c => ({
      label: (c.name || '').substring(0, 12), value: parseInt(c.total_amount) || 0
    }));
    new HorizontalBarChart('#top-chart', chartData);

    // Pie chart for order distribution by customer
    const topPie = top.slice(0, 6).map(c => ({ label: (c.name||'').substring(0,8), value: parseInt(c.order_count)||0 }));
    new PieChart('#cust-pie', topPie);

    document.getElementById('cust-search').addEventListener('input', e => {
      const s = e.target.value.toLowerCase();
      document.querySelectorAll('#cust-table tbody tr').forEach(r => {
        r.style.display = r.textContent.toLowerCase().includes(s) ? '' : 'none';
      });
    });
  }

  // ===== 统计分析 =====
  async renderStats(c) {
    const [revResp, distResp] = await Promise.all([api.getMonthlyRevenue(), api.getFlowDistribution()]);
    const monthly = revResp.monthly || [];
    const dist = distResp.distribution || {};

    c.innerHTML =
      '<div class="charts-grid">' +
        '<div class="card"><div class="card-header"><h3 class="card-title">月度营收趋势</h3></div><div id="stats-rev"></div></div>' +
        '<div class="card"><div class="card-header"><h3 class="card-title">流程分布</h3></div><div id="stats-dist"></div></div>' +
      '</div>' +
      '<div class="card" style="margin-top:16px;"><div class="card-header"><h3 class="card-title">月度数据明细</h3></div>' +
        '<div class="table-container"><table><thead><tr><th>月份</th><th>营收</th></tr></thead>' +
        '<tbody>' + monthly.map(m =>
          '<tr><td>' + m.month + '</td><td>' + formatCurrency(m.revenue) + '</td></tr>'
        ).join('') + '</tbody></table></div></div>';

    // Line chart for monthly revenue
    const revData = monthly.map(m => ({ label: m.month, value: parseFloat(m.revenue) || 0 }));
    new LineChart('#stats-rev', revData);

    // Donut chart for flow distribution
    const distData = Object.entries(dist).map(([k, v]) => ({
      label: v.name || FN[k] || k, value: v.count || 0, color: FC[k] || '#64748b'
    }));
    new DonutChart('#stats-dist', distData);
  }

  // ===== 打印机监控 =====
  async renderPrinters(c) {
    const [statusResp, queueResp] = await Promise.all([api.getPrinterStatus(), api.getPrinterQueue()]);
    const printers = statusResp.printers || [];
    const queue = queueResp.queue || [];

    c.innerHTML =
      '<div class="printer-grid" style="margin-bottom:24px;">' + printers.map(p =>
        '<div class="printer-card printer-' + (p.online?'online':'offline') + '">' +
        '<div class="printer-status ' + (p.online?'online':'offline') + '"></div>' +
        '<div class="printer-name">' + p.name + '</div>' +
        '<div class="printer-type">' + p.type + '</div>' +
        '<div class="printer-ip">' + p.ip + '</div>' +
        '<div class="printer-meta">' + (p.online ? '在线' : '离线') + ' | 队列: ' + (p.queue||0) + '</div></div>'
      ).join('') + '</div>' +
      '<div class="card"><div class="card-header"><h3 class="card-title">打印队列 (' + queue.length + ')</h3></div>' +
        '<div class="table-container"><table><thead><tr><th>工单号</th><th>文件</th><th>打印机</th><th>份数</th><th>状态</th><th>时间</th></tr></thead>' +
        '<tbody>' + (queue.length ? queue.map(q =>
          '<tr><td>' + (q.order_code||'-') + '</td><td>' + (q.pdf_source||'-') + '</td><td>' + (q.printer_name||'-') + '</td>' +
          '<td>' + (q.copies||0) + '</td><td>' + (q.status||'-') + '</td><td>' + (q.submitted_at||'') + '</td></tr>'
        ).join('') : '<tr><td colspan="6" style="text-align:center;color:#64748b;">暂无打印任务</td></tr>') + '</tbody></table></div></div>';
  }

  // ===== 新建工单 =====
  showCreateOrderModal() { document.getElementById('create-order-modal').classList.add('active'); }
  hideCreateOrderModal() { document.getElementById('create-order-modal').classList.remove('active'); }
  async submitCreateOrder() {
    const data = {
      customer_name: document.getElementById('order-customer').value.trim(),
      title: document.getElementById('order-product').value.trim(),
      standard_amount: parseFloat(document.getElementById('order-amount').value) || 0,
      remark: document.getElementById('order-remark').value.trim()
    };
    if (!data.customer_name) { alert('请输入客户名称'); return; }
    try {
      const r = await api.createOrder(data);
      if (r.success) { alert('工单创建成功: ' + r.order_code); this.hideCreateOrderModal(); location.reload(); }
      else { alert('创建失败: ' + (r.error || '未知错误')); }
    } catch (e) { alert('创建失败: ' + e.message); }
  }
}

const app = new QHIApp();
window.app = app;
