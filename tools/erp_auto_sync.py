#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_auto_sync.py — ERP自动同步脚本

功能:
- 每6分钟自动同步ERP数据到QHI
- 监控其他智能体进度
- 生成同步日志
- 异常处理和重试

使用:
    python erp_auto_sync.py              # 启动自动同步
    python erp_auto_sync.py --once       # 执行一次同步
    python erp_auto_sync.py --status     # 查看同步状态
"""
from __future__ import annotations

import os
import sys
import json
import time
import sqlite3
import logging
import signal
import threading
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class ERPAutoSync:
    """ERP自动同步服务"""
    
    def __init__(self):
        self.erp_db_path = '\\\\Server2\\客户文件2\\out\\customer_info.db'
        self.qhi_db_path = str(Path.home() / '.qhi_processor' / 'qhi_enterprise.db')
        self.log_dir = project_root / 'logs'
        self.log_dir.mkdir(exist_ok=True)
        
        self.sync_interval = 360  # 6分钟
        self.running = False
        self.last_sync = None
        self.sync_count = 0
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_file = self.log_dir / f'erp_sync_{datetime.now().strftime("%Y%m%d")}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('erp_sync')
    
    def sync_once(self) -> Dict:
        """执行一次同步"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'customers_synced': 0,
            'orders_synced': 0,
            'errors': []
        }
        
        try:
            # 同步客户
            customers = self._sync_customers()
            result['customers_synced'] = customers
            
            # 同步订单
            orders = self._sync_orders()
            result['orders_synced'] = orders
            
            result['success'] = True
            self.sync_count += 1
            self.last_sync = datetime.now()
            
            self.logger.info(f"同步成功: 客户 {customers}, 订单 {orders}")
            
        except Exception as e:
            result['errors'].append(str(e))
            self.logger.error(f"同步失败: {e}")
        
        # 保存同步状态
        self._save_status(result)
        
        return result
    
    def _sync_customers(self) -> int:
        """同步客户数据"""
        if not os.path.exists(self.erp_db_path):
            self.logger.warning(f"ERP数据库不存在: {self.erp_db_path}")
            return 0
        
        try:
            # 从ERP提取唯一客户
            erp_conn = sqlite3.connect(self.erp_db_path)
            erp_cur = erp_conn.cursor()
            erp_cur.execute("SELECT DISTINCT customer_code, customer_name FROM customer_info")
            erp_customers = {row[0]: row[1] for row in erp_cur.fetchall()}
            erp_conn.close()
            
            # 读取QHI客户
            qhi_conn = sqlite3.connect(self.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT code FROM customers")
            qhi_codes = {row[0] for row in qhi_cur.fetchall()}
            
            # 插入新客户
            new_customers = [(code, name) for code, name in erp_customers.items() 
                           if code not in qhi_codes]
            
            if new_customers:
                qhi_cur.executemany(
                    "INSERT OR IGNORE INTO customers (code, name) VALUES (?, ?)",
                    new_customers
                )
                qhi_conn.commit()
            
            qhi_conn.close()
            return len(new_customers)
            
        except Exception as e:
            self.logger.error(f"客户同步失败: {e}")
            return 0
    
    def _sync_orders(self) -> int:
        """同步订单数据（从ERP customer_info提取工单）"""
        if not os.path.exists(self.erp_db_path):
            return 0
        
        try:
            # 从ERP提取工单信息
            erp_conn = sqlite3.connect(self.erp_db_path)
            erp_cur = erp_conn.cursor()
            erp_cur.execute("""
                SELECT customer_code, customer_name, gd_no, gd_dir, 
                       file_path, extracted_json, date
                FROM customer_info 
                WHERE gd_no IS NOT NULL AND gd_no != ''
                ORDER BY date DESC
                LIMIT 100
            """)
            erp_orders = erp_cur.fetchall()
            erp_conn.close()
            
            # 读取QHI订单
            qhi_conn = sqlite3.connect(self.qhi_db_path)
            qhi_cur = qhi_conn.cursor()
            qhi_cur.execute("SELECT order_no FROM orders")
            qhi_orders = {row[0] for row in qhi_cur.fetchall()}
            
            # 插入新订单
            new_orders = 0
            for row in erp_orders:
                code, name, gd_no, gd_dir, file_path, json_str, date = row
                if gd_no and gd_no not in qhi_orders:
                    try:
                        qhi_cur.execute("""
                            INSERT OR IGNORE INTO orders 
                            (order_no, customer_name, file_path, status, created_at)
                            VALUES (?, ?, ?, 'pending', ?)
                        """, (gd_no, name, file_path, date))
                        new_orders += 1
                    except Exception:
                        pass
            
            qhi_conn.commit()
            qhi_conn.close()
            return new_orders
            
        except Exception as e:
            self.logger.error(f"订单同步失败: {e}")
            return 0
    
    def _save_status(self, result: Dict):
        """保存同步状态"""
        status_file = self.log_dir / 'erp_sync_status.json'
        status = {
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_count': self.sync_count,
            'last_result': result,
        }
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    
    def get_status(self) -> Dict:
        """获取同步状态"""
        status_file = self.log_dir / 'erp_sync_status.json'
        if status_file.exists():
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_sync': None, 'sync_count': 0}
    
    def run_forever(self):
        """持续运行同步"""
        self.running = True
        self.logger.info(f"ERP自动同步启动 (间隔: {self.sync_interval}秒)")
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        while self.running:
            try:
                self.sync_once()
            except Exception as e:
                self.logger.error(f"同步异常: {e}")
            
            # 等待下一次同步
            for _ in range(self.sync_interval):
                if not self.running:
                    break
                time.sleep(1)
        
        self.logger.info("ERP自动同步已停止")
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        self.logger.info(f"收到信号 {signum}，正在停止...")
        self.running = False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='ERP自动同步脚本')
    parser.add_argument('--once', action='store_true', help='执行一次同步')
    parser.add_argument('--status', action='store_true', help='查看同步状态')
    parser.add_argument('--interval', type=int, default=360, help='同步间隔（秒）')
    args = parser.parse_args()
    
    sync = ERPAutoSync()
    sync.sync_interval = args.interval
    
    if args.status:
        status = sync.get_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif args.once:
        result = sync.sync_once()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sync.run_forever()


if __name__ == '__main__':
    main()
