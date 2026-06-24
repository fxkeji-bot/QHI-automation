// QHI Web - API 封装
const API_BASE = '/api';

class QHIApi {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 30000;
  }

  async fetch(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const cacheKey = `${url}${JSON.stringify(options)}`;
    
    if (options.method === 'GET' || !options.method) {
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() - cached.time < this.cacheTimeout) {
        return cached.data;
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (options.method === 'GET' || !options.method) {
        this.cache.set(cacheKey, { data, time: Date.now() });
      }

      return data;
    } catch (error) {
      console.error('API请求失败:', error);
      throw error;
    }
  }

  clearCache() {
    this.cache.clear();
  }

  // 仪表盘数据
  async health() {
    return this.fetch('/health');
  }
  async getDashboard() {
    return this.fetch('/dashboard');
  }

  // 工单列表
  async getOrders(limit = 20) {
    return this.fetch(`/flow/orders?limit=${limit}`);
  }

  // 工单详情
  async getOrderDetail(code) {
    return this.fetch(`/flow/order/${code}/detail`);
  }

  // 客户列表
  async getCustomers() {
    return this.fetch('/customers/list');
  }

  // TOP10客户
  async getTopCustomers() {
    return this.fetch('/customers/top10');
  }

  // 流程分布
  async getFlowDistribution() {
    return this.fetch('/flow/flow_distribution');
  }

  // 月度营收
  async getMonthlyRevenue() {
    return this.fetch('/flow/monthly_revenue');
  }

  // 统计摘要
  async getStatsSummary() {
    return this.fetch('/stats/summary');
  }

  // 打印机状态
  async getPrinterStatus() {
    return this.fetch('/fleet/status');
  }

  // 打印队列
  async getPrinterQueue() {
    return this.fetch('/printer/queue');
  }

  // 流程分类
  async getFlowCategories() {
    return this.fetch('/flow/categories');
  }

  // 创建工单
  async createOrder(data) {
    const result = await this.fetch('/flow/create', {
      method: 'POST',
      body: JSON.stringify(data)
    });
    this.clearCache();
    return result;
  }

  // 更新流程
  async updateFlow(data) {
    const result = await this.fetch('/flow/update', {
      method: 'POST',
      body: JSON.stringify(data)
    });
    this.clearCache();
    return result;
  }

  // 审核工单
  async auditOrder(data) {
    const result = await this.fetch('/flow/audit', {
      method: 'POST',
      body: JSON.stringify(data)
    });
    this.clearCache();
    return result;
  }
}

const api = new QHIApi();
export default api;
