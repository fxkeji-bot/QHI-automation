// QHI Web - 图表组件 (v2 增强版)
const FLOW_COLORS = {'10':'#64748b','15':'#eab308','20':'#3b82f6','21':'#8b5cf6','30':'#ec4899','35':'#f97316','45':'#22c55e','65':'#06b6d4','70':'#ef4444'};
const PALETTE = ['#3b82f6','#22c55e','#f97316','#a855f7','#ef4444','#06b6d4','#eab308','#ec4899'];

export class BarChart {
  constructor(container, data, options = {}) {
    this.el = typeof container === 'string' ? document.querySelector(container) : container;
    this.data = (data || []).filter(d => d.value > 0);
    this.opts = { showValues: true, horizontal: false, ...options };
    this.render();
  }
  render() {
    if (!this.el || !this.data.length) { if (this.el) this.el.innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }
    const max = Math.max(...this.data.map(d => d.value));
    const total = this.data.reduce((s, d) => s + d.value, 0);
    this.el.innerHTML = '<div class="bar-chart">' +
      this.data.map((item, i) => {
        const pct = max > 0 ? (item.value / max) * 100 : 0;
        const color = item.color || PALETTE[i % PALETTE.length];
        const share = total > 0 ? ((item.value / total) * 100).toFixed(1) : 0;
        return '<div class="bar-item"><div class="bar-value">' + item.value.toLocaleString() + '</div>' +
          '<div class="bar-wrap"><div class="bar" style="height:' + pct + '%;background:' + color + ';" title="' + item.label + ': ' + item.value + ' (' + share + '%)"></div></div>' +
          '<div class="bar-label">' + item.label + '</div></div>';
      }).join('') + '</div>';
  }
}

export class HorizontalBarChart {
  constructor(container, data, options = {}) {
    this.el = typeof container === 'string' ? document.querySelector(container) : container;
    this.data = (data || []).filter(d => d.value > 0).slice(0, 15);
    this.render();
  }
  render() {
    if (!this.el || !this.data.length) { if (this.el) this.el.innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }
    const max = Math.max(...this.data.map(d => d.value));
    const total = this.data.reduce((s, d) => s + d.value, 0);
    this.el.innerHTML = '<div class="hbar-chart">' +
      this.data.map((item, i) => {
        const pct = max > 0 ? (item.value / max) * 100 : 0;
        const color = item.color || PALETTE[i % PALETTE.length];
        return '<div class="hbar-row"><div class="hbar-label">' + item.label + '</div>' +
          '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct + '%;background:' + color + ';"></div></div>' +
          '<div class="hbar-val">' + item.value.toLocaleString() + '</div></div>';
      }).join('') + '</div>';
  }
}

export class LineChart {
  constructor(container, data, options = {}) {
    this.el = typeof container === 'string' ? document.querySelector(container) : container;
    this.data = data || [];
    this.opts = { color: '#3b82f6', showArea: true, showPoints: true, yLabel: '', ...options };
    this.render();
  }
  render() {
    if (!this.el || this.data.length < 2) { if (this.el) this.el.innerHTML = '<div class="chart-empty">数据不足</div>'; return; }
    const W = 600, H = 250, P = {t:25,r:20,b:35,l:55};
    const cW = W - P.l - P.r, cH = H - P.t - P.b;
    const vals = this.data.map(d => d.value);
    let min = Math.min(...vals), max = Math.max(...vals);
    if (min === max) { min = min - 1; max = max + 1; }
    const range = max - min;
    const pad = range * 0.1;
    const dMin = min - pad, dMax = max + pad, dRange = dMax - dMin;

    const points = this.data.map((d, i) => ({
      x: P.l + (i / (this.data.length - 1)) * cW,
      y: P.t + cH - ((d.value - dMin) / dRange) * cH,
      v: d.value, l: d.label
    }));

    const pathD = points.map((p, i) => (i === 0 ? 'M' : 'L') + ' ' + p.x.toFixed(1) + ' ' + p.y.toFixed(1)).join(' ');
    const areaD = pathD + ' L ' + points[points.length-1].x.toFixed(1) + ' ' + (P.t + cH) + ' L ' + points[0].x.toFixed(1) + ' ' + (P.t + cH) + ' Z';

    const yTicks = 5;
    let gridLines = '', yLabels = '';
    for (let i = 0; i <= yTicks; i++) {
      const y = P.t + (i / yTicks) * cH;
      const val = dMax - (i / yTicks) * dRange;
      gridLines += '<line x1="' + P.l + '" y1="' + y.toFixed(1) + '" x2="' + (W - P.r) + '" y2="' + y.toFixed(1) + '" stroke="#334155" stroke-width="1" />';
      yLabels += '<text x="' + (P.l - 8) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" fill="#64748b" font-size="11">' + (val >= 10000 ? (val/10000).toFixed(1) + 'w' : val >= 1000 ? (val/1000).toFixed(1) + 'k' : Math.round(val)) + '</text>';
    }

    let xLabels = '';
    const step = Math.max(1, Math.floor(this.data.length / 8));
    points.forEach((p, i) => {
      if (i % step === 0 || i === points.length - 1) {
        xLabels += '<text x="' + p.x.toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" fill="#64748b" font-size="10">' + p.l + '</text>';
      }
    });

    const tooltipId = 'ltip_' + Math.random().toString(36).slice(2, 8);

    const svg = '<svg class="line-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">' +
      '<defs><linearGradient id="areaFill" x1="0%" y1="0%" x2="0%" y2="100%">' +
      '<stop offset="0%" style="stop-color:' + this.opts.color + ';stop-opacity:0.25"/>' +
      '<stop offset="100%" style="stop-color:' + this.opts.color + ';stop-opacity:0"/></linearGradient></defs>' +
      gridLines + yLabels + xLabels +
      '<path d="' + areaD + '" fill="url(#areaFill)"/>' +
      '<path d="' + pathD + '" fill="none" stroke="' + this.opts.color + '" stroke-width="2.5" stroke-linejoin="round"/>' +
      points.map(p => '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3.5" fill="' + this.opts.color + '" stroke="#0f172a" stroke-width="1.5"/>').join('') +
      points.map(p => '<title>' + p.l + ': ' + p.v.toLocaleString() + '</title>').join('') +
      '</svg>';
    this.el.innerHTML = '<div class="line-chart-container">' + svg + '</div>';
  }
}

export class PieChart {
  constructor(container, data, options = {}) {
    this.el = typeof container === 'string' ? document.querySelector(container) : container;
    this.data = (data || []).filter(d => d.value > 0);
    this.opts = { size: 200, showLegend: true, ...options };
    this.render();
  }
  render() {
    if (!this.el || !this.data.length) { if (this.el) this.el.innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }
    const total = this.data.reduce((s, d) => s + d.value, 0);
    const sz = this.opts.size, r = sz / 2 - 5, cx = sz / 2, cy = sz / 2;
    let angle = -90;
    const slices = this.data.map((d, i) => {
      const a = (d.value / total) * 360, sa = angle, ea = angle + a;
      angle = ea;
      const sr = sa * Math.PI / 180, er = ea * Math.PI / 180;
      const x1 = cx + r * Math.cos(sr), y1 = cy + r * Math.sin(sr);
      const x2 = cx + r * Math.cos(er), y2 = cy + r * Math.sin(er);
      const large = a > 180 ? 1 : 0;
      return { path: 'M ' + cx + ' ' + cy + ' L ' + x1.toFixed(2) + ' ' + y1.toFixed(2) + ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2.toFixed(2) + ' ' + y2.toFixed(2) + ' Z',
        color: d.color || PALETTE[i % PALETTE.length], label: d.label, value: d.value, pct: Math.round((d.value / total) * 100) };
    });
    const svg = '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 ' + sz + ' ' + sz + '">' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r * 0.45) + '" fill="#1e293b"/>' +
      '<text x="' + cx + '" y="' + (cy - 5) + '" text-anchor="middle" fill="#f8fafc" font-size="18" font-weight="700">' + total.toLocaleString() + '</text>' +
      '<text x="' + cx + '" y="' + (cy + 14) + '" text-anchor="middle" fill="#94a3b8" font-size="11">总计</text>' +
      slices.map(s => '<path d="' + s.path + '" fill="' + s.color + '"><title>' + s.label + ': ' + s.value.toLocaleString() + ' (' + s.pct + '%)</title></path>').join('') +
      '</svg>';
    const legend = '<div class="pie-legend">' + slices.map(s =>
      '<div class="legend-item"><span class="legend-dot" style="background:' + s.color + ';"></span>' +
      '<span class="legend-label">' + s.label + '</span><span class="legend-value">' + s.value.toLocaleString() + ' (' + s.pct + '%)</span></div>'
    ).join('') + '</div>';
    this.el.innerHTML = '<div class="pie-wrap">' + svg + legend + '</div>';
  }
}

export class DonutChart {
  constructor(container, data, options = {}) {
    this.el = typeof container === 'string' ? document.querySelector(container) : container;
    this.data = (data || []).filter(d => d.value > 0);
    this.opts = { size: 180, ...options };
    this.render();
  }
  render() {
    if (!this.el || !this.data.length) { if (this.el) this.el.innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }
    const total = this.data.reduce((s, d) => s + d.value, 0);
    const sz = this.opts.size, outerR = sz / 2 - 5, innerR = outerR * 0.6, cx = sz / 2, cy = sz / 2;
    let angle = -90;
    const slices = this.data.map((d, i) => {
      const a = (d.value / total) * 360, sa = angle, ea = angle + a;
      angle = ea;
      const sr = sa * Math.PI / 180, er = ea * Math.PI / 180;
      const ox1 = cx + outerR * Math.cos(sr), oy1 = cy + outerR * Math.sin(sr);
      const ox2 = cx + outerR * Math.cos(er), oy2 = cy + outerR * Math.sin(er);
      const ix1 = cx + innerR * Math.cos(er), iy1 = cy + innerR * Math.sin(er);
      const ix2 = cx + innerR * Math.cos(sr), iy2 = cy + innerR * Math.sin(sr);
      const large = a > 180 ? 1 : 0;
      return { path: 'M ' + ox1.toFixed(2) + ' ' + oy1.toFixed(2) + ' A ' + outerR + ' ' + outerR + ' 0 ' + large + ' 1 ' + ox2.toFixed(2) + ' ' + oy2.toFixed(2) + ' L ' + ix1.toFixed(2) + ' ' + iy1.toFixed(2) + ' A ' + innerR + ' ' + innerR + ' 0 ' + large + ' 0 ' + ix2.toFixed(2) + ' ' + iy2.toFixed(2) + ' Z',
        color: d.color || PALETTE[i % PALETTE.length], label: d.label, value: d.value, pct: Math.round((d.value / total) * 100) };
    });
    const svg = '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 ' + sz + ' ' + sz + '">' +
      slices.map(s => '<path d="' + s.path + '" fill="' + s.color + '"><title>' + s.label + ': ' + s.value.toLocaleString() + ' (' + s.pct + '%)</title></path>').join('') +
      '<text x="' + cx + '" y="' + (cy - 3) + '" text-anchor="middle" fill="#f8fafc" font-size="16" font-weight="700">' + total.toLocaleString() + '</text>' +
      '<text x="' + cx + '" y="' + (cy + 12) + '" text-anchor="middle" fill="#94a3b8" font-size="10">总计</text></svg>';
    const legend = '<div class="pie-legend">' + slices.map(s =>
      '<div class="legend-item"><span class="legend-dot" style="background:' + s.color + ';"></span>' +
      '<span class="legend-label">' + s.label + '</span><span class="legend-value">' + s.value.toLocaleString() + ' (' + s.pct + '%)</span></div>'
    ).join('') + '</div>';
    this.el.innerHTML = '<div class="pie-wrap">' + svg + legend + '</div>';
  }
}

export function createStatusBadge(code) {
  const names = {'10':'排队','15':'审单中','20':'前期','21':'机房','30':'后道','35':'外发','45':'完工','65':'寄快递','70':'未付'};
  const text = names[code] || code || '未知';
  return '<span class="status-badge ' + text + '">' + text + '</span>';
}

export function formatCurrency(v) {
  const n = Number(v) || 0;
  if (n >= 10000) return '\u00a5' + (n / 10000).toFixed(2) + 'w';
  return '\u00a5' + n.toLocaleString('zh-CN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

export function formatNumber(v) {
  const n = Number(v) || 0;
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
  return n.toLocaleString('zh-CN');
}
