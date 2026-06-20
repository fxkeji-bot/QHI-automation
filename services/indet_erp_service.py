"""
印特ERP数据库集成服务 (Indet ERP Integration Service)
====================================================
深度集成印特EMS SQL Server数据库，实现数据直连读取与双向同步。
支持方案A（直连SQL Server）和方案B（API中间层）自动降级。

数据库表映射：
  RSM_Business        - 业务单主表
  RSM_BusinessSub     - 业务单子表
  RSM_BusinessSpec    - 业务单规格明细
  PPM_JobBill         - 工单主表
  CRM_Customer        - 客户信息
  BAS_Paper           - 纸张基础数据
  BAS_ProcessPrice    - 工艺单价
  BAS_FinishingPrice  - 后道工序单价

Author: QHI System
Version: 2.0.0
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ============================================================
# 配置管理
# ============================================================
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "indet_erp_config.json"
)

DEFAULT_CONFIG = {
    "version": "2.0",
    "primary": {
        "mode": "direct",  # direct | api
        "sql_server": {
            "host": "192.168.1.22",
            "port": 1433,
            "database": "EMSXDB",
            "driver": "ODBC Driver 17 for SQL Server",
            "trusted_connection": True,
            "connect_timeout": 10,
            "query_timeout": 30,
            "pool_size": 5
        }
    },
    "fallback": {
        "mode": "api",
        "api": {
            "base_url": "http://192.168.1.22:8080/api",
            "timeout": 15,
            "retry": 3
        }
    },
    "sync": {
        "interval_minutes": 5,
        "tables_sync": [
            "RSM_Business", "RSM_BusinessSub", "RSM_BusinessSpec",
            "PPM_JobBill", "CRM_Customer", "BAS_Paper",
            "BAS_ProcessPrice", "BAS_FinishingPrice"
        ],
        "write_back_tables": [
            "PPM_JobBill"
        ]
    }
}


class IndetERPConfig:
    """印特ERP配置管理器"""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    merged = DEFAULT_CONFIG.copy()
                    _deep_merge(merged, loaded)
                    return merged
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("配置加载失败，使用默认配置: %s", e)
        return DEFAULT_CONFIG.copy()

    def save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        logger.info("配置已保存至 %s", self.config_path)

    def get_connection_string(self) -> str:
        """构建 SQL Server 连接字符串"""
        db = self.config["primary"]["sql_server"]
        trusted = db.get("trusted_connection", True)
        if trusted:
            return (
                f"DRIVER={{{db['driver']}}};"
                f"SERVER={db['host']},{db['port']};"
                f"DATABASE={db['database']};"
                f"Trusted_Connection=yes;"
                f"TrustServerCertificate=yes;"
            )
        else:
            return (
                f"DRIVER={{{db['driver']}}};"
                f"SERVER={db['host']},{db['port']};"
                f"DATABASE={db['database']};"
                f"UID={db.get('username', '')};"
                f"PWD={db.get('password', '')};"
                f"TrustServerCertificate=yes;"
            )


def _deep_merge(base: Dict, override: Dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ============================================================
# SQL Server 直连服务 (方案A)
# ============================================================
class SQLServerDirectConnector:
    """SQL Server 直连服务 - 方案A"""

    def __init__(self, config: IndetERPConfig):
        self.config = config
        self._connection = None
        self._pool = []
        self._available = None  # None=未测试, True=可用, False=不可用
        self._last_test_time = None

    def test_connection(self) -> bool:
        """测试数据库连接是否可用"""
        conn_str = self.config.get_connection_string()
        try:
            import pyodbc
            conn = pyodbc.connect(conn_str, timeout=self.config.config["primary"]["sql_server"]["connect_timeout"])
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            self._available = True
            self._last_test_time = datetime.now()
            logger.info("SQL Server 直连测试成功: %s", conn_str)
            return True
        except ImportError:
            logger.warning("pyodbc 未安装，尝试安装...")
            try:
                import subprocess
                subprocess.check_call(["pip", "install", "pyodbc"])
                return self.test_connection()
            except Exception as e:
                logger.error("pyodbc 安装失败: %s", e)
                self._available = False
                return False
        except Exception as e:
            logger.warning("SQL Server 直连测试失败 (1433端口可能不通): %s", e)
            self._available = False
            self._last_test_time = datetime.now()
            return False

    def is_available(self) -> bool:
        if self._available is None:
            self.test_connection()
        if self._available is False:
            # 30秒后重试一次
            if self._last_test_time and (datetime.now() - self._last_test_time).seconds < 30:
                return False
            self.test_connection()
        return self._available or False

    def _get_connection(self):
        import pyodbc
        conn_str = self.config.get_connection_string()
        return pyodbc.connect(conn_str, timeout=self.config.config["primary"]["sql_server"]["connect_timeout"])

    def query(self, sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """执行查询并返回字典列表"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            rows = []
            for row in cursor.fetchall():
                rows.append(dict(zip(columns, row)))
            return rows
        finally:
            conn.close()

    def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """执行写操作，返回影响行数"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            conn.commit()
            return cursor.rowcount
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- 业务单查询 ----
    def get_business_list(self, limit: int = 100, offset: int = 0,
                          date_from: Optional[str] = None,
                          date_to: Optional[str] = None) -> List[Dict]:
        """获取业务单列表"""
        sql = """
            SELECT TOP (?) b.BillID, b.BillCode, b.CustomerID, b.CustomerName,
                   b.BillDate, b.TotalAmount, b.PaidAmount, b.BillStatus,
                   b.Salesman, b.CreatedAt, b.UpdatedAt
            FROM RSM_Business b
            WHERE 1=1
        """
        params = [limit + offset]
        if date_from:
            sql += " AND b.BillDate >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND b.BillDate <= ?"
            params.append(date_to)
        sql += " ORDER BY b.BillDate DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, limit])
        return self.query(sql, tuple(params))

    def get_business_detail(self, bill_id: int) -> Dict:
        """获取业务单详情"""
        business = self.query(
            "SELECT * FROM RSM_Business WHERE BillID = ?", (bill_id,)
        )
        if not business:
            return {}
        result = business[0]
        result["sub_items"] = self.query(
            "SELECT * FROM RSM_BusinessSub WHERE BillID = ?", (bill_id,)
        )
        return result

    # ---- 工单查询 ----
    def get_job_bills(self, limit: int = 100, offset: int = 0,
                      flow_code: Optional[str] = None,
                      date_from: Optional[str] = None,
                      date_to: Optional[str] = None,
                      customer_name: Optional[str] = None) -> List[Dict]:
        """获取工单列表"""
        sql = """
            SELECT TOP (?) j.OrderCode, j.CustomerName, j.Title as ProductName,
                   j.FlowCode, j.FlowName, j.CustomerRemark,
                   j.CreatedAt, j.FilePath, j.Quantity,
                   j.PaperType, j.FinishedSize, j.BusinessID
            FROM PPM_JobBill j
            WHERE 1=1
        """
        params = [limit + offset]
        if flow_code:
            sql += " AND j.FlowCode = ?"
            params.append(flow_code)
        if date_from:
            sql += " AND j.CreatedAt >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND j.CreatedAt <= ?"
            params.append(date_to)
        if customer_name:
            sql += " AND j.CustomerName LIKE ?"
            params.append(f"%{customer_name}%")
        sql += " ORDER BY j.CreatedAt DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, limit])
        return self.query(sql, tuple(params))

    def update_job_flow(self, order_code: str, flow_code: str,
                        flow_name: str) -> int:
        """更新工单流程状态（写回印特）"""
        return self.execute(
            """UPDATE PPM_JobBill
               SET FlowCode = ?, FlowName = ?, UpdatedAt = GETDATE()
               WHERE OrderCode = ?""",
            (flow_code, flow_name, order_code)
        )

    def update_job_progress(self, order_code: str,
                            progress_data: Dict) -> int:
        """更新工单生产进度"""
        return self.execute(
            """UPDATE PPM_JobBill
               SET ProductionProgress = ?, MachineStatus = ?,
                   UpdatedAt = GETDATE()
               WHERE OrderCode = ?""",
            (json.dumps(progress_data, ensure_ascii=False),
             progress_data.get("machine_status", ""),
             order_code)
        )

    # ---- 客户查询 ----
    def get_customers(self, limit: int = 500, keyword: Optional[str] = None) -> List[Dict]:
        sql = "SELECT TOP (?) CustomerID, CustomerName, ContactPerson, Phone, Address, CreatedAt FROM CRM_Customer"
        params = [limit]
        if keyword:
            sql += " WHERE CustomerName LIKE ? OR ContactPerson LIKE ?"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY CustomerName"
        return self.query(sql, tuple(params))

    # ---- 纸张数据 ----
    def get_paper_list(self, paper_type: Optional[str] = None,
                       keyword: Optional[str] = None) -> List[Dict]:
        """获取纸张列表及单价"""
        sql = """
            SELECT PaperCode, PaperName, PaperType, Grammage, SizeW, SizeH,
                   UnitPrice, Unit, SupplierName
            FROM BAS_Paper WHERE IsActive = 1
        """
        params = []
        if paper_type:
            sql += " AND PaperType = ?"
            params.append(paper_type)
        if keyword:
            sql += " AND (PaperName LIKE ? OR PaperCode LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        sql += " ORDER BY PaperType, PaperName"
        return self.query(sql, tuple(params))

    def get_paper_price(self, paper_code: str) -> Optional[Dict]:
        """获取指定纸张的单价信息"""
        result = self.query(
            "SELECT * FROM BAS_Paper WHERE PaperCode = ? AND IsActive = 1",
            (paper_code,)
        )
        return result[0] if result else None

    # ---- 工艺单价 ----
    def get_process_prices(self, category: Optional[str] = None) -> List[Dict]:
        """获取工艺单价列表"""
        sql = """
            SELECT ProcessCode, ProcessName, Category, UnitPrice,
                   Unit, MinQuantity, CoefficientFormula
            FROM BAS_ProcessPrice WHERE IsActive = 1
        """
        if category:
            sql += " AND Category = ?"
            return self.query(sql, (category,))
        return self.query(sql)

    # ---- 后道单价 ----
    def get_finishing_prices(self, category: Optional[str] = None) -> List[Dict]:
        """获取后道工序单价"""
        sql = """
            SELECT FinishingCode, FinishingName, Category, UnitPrice,
                   Unit, MinQuantity
            FROM BAS_FinishingPrice WHERE IsActive = 1
        """
        if category:
            sql += " AND Category = ?"
            return self.query(sql, (category,))
        return self.query(sql)

    # ---- 统计分析 ----
    def get_revenue_stats(self, period: str = "today") -> Dict:
        """营收统计"""
        now = datetime.now()
        if period == "today":
            date_from = now.strftime("%Y-%m-%d")
        elif period == "week":
            date_from = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        elif period == "month":
            date_from = now.strftime("%Y-%m-01")
        else:
            date_from = now.strftime("%Y-%m-01")

        sql = """
            SELECT COUNT(*) as order_count,
                   ISNULL(SUM(TotalAmount), 0) as total_revenue,
                   ISNULL(SUM(PaidAmount), 0) as total_paid
            FROM RSM_Business
            WHERE BillDate >= ?
        """
        result = self.query(sql, (date_from,))
        return result[0] if result else {"order_count": 0, "total_revenue": 0, "total_paid": 0}

    def get_production_stats(self) -> Dict:
        """产能统计 - 按工序和设备"""
        stats = {}
        flow_stats = self.query(
            """SELECT FlowName, COUNT(*) as cnt
               FROM PPM_JobBill
               WHERE FlowCode NOT IN ('45', '70')
               GROUP BY FlowName"""
        )
        stats["by_flow"] = {r["FlowName"]: r["cnt"] for r in flow_stats}
        stats["total_active"] = sum(stats["by_flow"].values())
        return stats

    def get_customer_distribution(self, top_n: int = 10) -> List[Dict]:
        """客户工单分布"""
        return self.query(
            """SELECT TOP (?) CustomerName, COUNT(*) as order_count,
                      ISNULL(SUM(TotalAmount), 0) as total_amount
               FROM RSM_Business
               GROUP BY CustomerName
               ORDER BY order_count DESC""",
            (top_n,)
        )


# ============================================================
# API 中间层服务 (方案B - 降级方案)
# ============================================================
class APIIntermediateService:
    """API 中间层服务 - 方案B"""

    def __init__(self, config: IndetERPConfig):
        self.config = config
        self.base_url = config.config["fallback"]["api"]["base_url"]
        self.timeout = config.config["fallback"]["api"]["timeout"]
        self.retry = config.config["fallback"]["api"]["retry"]

    def _request(self, endpoint: str, method: str = "GET",
                 data: Optional[Dict] = None) -> Optional[Dict]:
        import urllib.request
        import urllib.error

        url = f"{self.base_url}{endpoint}"
        for attempt in range(self.retry):
            try:
                if method == "GET":
                    req = urllib.request.Request(url, method="GET")
                else:
                    req = urllib.request.Request(
                        url, method=method,
                        data=json.dumps(data).encode("utf-8") if data else None,
                        headers={"Content-Type": "application/json"}
                    )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.URLError as e:
                logger.warning("API请求失败 (尝试 %d/%d): %s", attempt + 1, self.retry, e)
                if attempt < self.retry - 1:
                    time.sleep(1)
        return None

    def get_business_list(self, **kwargs) -> List[Dict]:
        result = self._request("/api/business")
        return result.get("data", []) if result else []

    def get_job_bills(self, **kwargs) -> List[Dict]:
        result = self._request("/api/orders")
        return result.get("data", []) if result else []

    def get_customers(self, **kwargs) -> List[Dict]:
        result = self._request("/api/customers")
        return result.get("data", []) if result else []

    def get_paper_list(self, **kwargs) -> List[Dict]:
        result = self._request("/api/paper")
        return result.get("data", []) if result else []

    def get_process_prices(self, **kwargs) -> List[Dict]:
        result = self._request("/api/process_prices")
        return result.get("data", []) if result else []

    def get_finishing_prices(self, **kwargs) -> List[Dict]:
        result = self._request("/api/finishing_prices")
        return result.get("data", []) if result else []

    def get_revenue_stats(self, **kwargs) -> Dict:
        result = self._request("/api/stats/revenue")
        return result.get("data", {}) if result else {}

    def get_production_stats(self, **kwargs) -> Dict:
        result = self._request("/api/stats/production")
        return result.get("data", {}) if result else {}


# ============================================================
# 统一服务门面
# ============================================================
class IndetERPService:
    """印特ERP统一服务 - 自动选择直连/API方案"""

    _instance: Optional["IndetERPService"] = None

    def __new__(cls, config_path: str = DEFAULT_CONFIG_PATH):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        if self._initialized:
            return
        self._initialized = True
        self.config = IndetERPConfig(config_path)
        self._direct: Optional[SQLServerDirectConnector] = None
        self._api: Optional[APIIntermediateService] = None
        self._mode = "auto"  # auto | direct | api
        self._init_connectors()

    def _init_connectors(self):
        self._direct = SQLServerDirectConnector(self.config)
        self._api = APIIntermediateService(self.config)

        # 自动检测并选择方案
        if self._direct.is_available():
            self._mode = "direct"
            logger.info("印特ERP服务: 方案A (SQL Server直连) 已激活")
        else:
            self._mode = "api"
            logger.warning("印特ERP服务: 方案A不可用，降级至方案B (API中间层)")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def connector(self):
        """获取当前活跃连接器"""
        if self._mode == "direct" and self._direct:
            return self._direct
        return self._api

    def force_mode(self, mode: str):
        """强制切换方案"""
        if mode == "direct":
            if self._direct and self._direct.is_available():
                self._mode = "direct"
            else:
                raise ConnectionError("SQL Server 直连不可用")
        elif mode == "api":
            self._mode = "api"
        else:
            raise ValueError(f"未知模式: {mode}")

    # ---- 委托方法 ----
    def get_business_list(self, **kwargs):
        return self.connector.get_business_list(**kwargs)

    def get_business_detail(self, bill_id: int):
        if self._mode == "direct":
            return self._direct.get_business_detail(bill_id)
        return {}

    def get_job_bills(self, **kwargs):
        return self.connector.get_job_bills(**kwargs)

    def update_job_flow(self, order_code: str, flow_code: str, flow_name: str):
        """更新工单流程 - 如果直连可用则直接写回印特"""
        if self._mode == "direct":
            return self._direct.update_job_flow(order_code, flow_code, flow_name)
        # API 模式: 尝试 POST 回 API
        if self._api:
            result = self._api._request("/api/orders/update_flow", "POST", {
                "order_code": order_code,
                "flow_code": flow_code,
                "flow_name": flow_name
            })
            return result.get("affected", 0) if result else 0
        return 0

    def update_job_progress(self, order_code: str, progress_data: Dict):
        if self._mode == "direct":
            return self._direct.update_job_progress(order_code, progress_data)
        return 0

    def get_customers(self, **kwargs):
        return self.connector.get_customers(**kwargs)

    def get_paper_list(self, **kwargs):
        return self.connector.get_paper_list(**kwargs)

    def get_paper_price(self, paper_code: str):
        if self._mode == "direct":
            return self._direct.get_paper_price(paper_code)
        return None

    def get_process_prices(self, **kwargs):
        return self.connector.get_process_prices(**kwargs)

    def get_finishing_prices(self, **kwargs):
        return self.connector.get_finishing_prices(**kwargs)

    def get_revenue_stats(self, **kwargs):
        return self.connector.get_revenue_stats(**kwargs)

    def get_production_stats(self, **kwargs):
        return self.connector.get_production_stats(**kwargs)

    def get_customer_distribution(self, **kwargs):
        if self._mode == "direct":
            return self._direct.get_customer_distribution(**kwargs)
        return []


# ============================================================
# 模块级便捷函数
# ============================================================
def get_erp_service() -> IndetERPService:
    """获取印特ERP服务单例"""
    return IndetERPService()
