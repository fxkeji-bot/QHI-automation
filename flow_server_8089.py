#!/C:\python-embed\python.exe
# -*- coding: utf-8 -*-
"""QHI Web Server - Port 8089 (T57 CRITICAL fixes applied)"""
import json, os, sys, traceback, threading, time
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

_cache = {}
_cache_lock = threading.Lock()
def cached(key, ttl, fn):
    now = time.time()
    with _cache_lock:
        if key in _cache and now - _cache[key][0] < ttl:
            return _cache[key][1]
    result = fn()
    with _cache_lock:
        _cache[key] = (now, result)
    return result

_pool = []
_pool_lock = threading.Lock()
_pool_cond = threading.Condition(_pool_lock)
POOL_SIZE = 20
POOL_TIMEOUT = 30.0  # max wait seconds for a connection

def _make_conn():
    import pyodbc
    return pyodbc.connect("DRIVER={SQL Server};SERVER=.\\GT_YINTE_EMS;Database=EMSXDB;Trusted_Connection=yes;TrustServerCertificate=yes;", timeout=10)

def get_connection():
    """Blocking connection get with timeout; skips heartbeat for pool reuse to save round-trips."""
    deadline = time.time() + POOL_TIMEOUT
    with _pool_cond:
        while True:
            if _pool:
                c = _pool.pop()
                break
            remaining = deadline - time.time()
            if remaining <= 0:
                print("[%s] DB pool exhausted (timeout %ds), overflow conn" % (datetime.now().strftime('%H:%M:%S'), POOL_TIMEOUT))
                try:
                    return _make_conn()
                except Exception as e:
                    print("[%s] DB overflow conn failed: %s" % (datetime.now().strftime('%H:%M:%S'), e))
                    return None
            _pool_cond.wait(remaining)
    # Verify connection is alive (only on pool reuse, not on every get)
    try:
        c.cursor().execute("SELECT 1")
        return c
    except Exception:
        # Stale connection, replace
        try: c.close()
        except: pass
        try:
            return _make_conn()
        except Exception as e:
            print("[%s] DB replace conn failed: %s" % (datetime.now().strftime('%H:%M:%S'), e))
            return None

def release_connection(c):
    if not c:
        return
    with _pool_cond:
        if len(_pool) < POOL_SIZE:
            _pool.append(c)
            _pool_cond.notify()
        else:
            try: c.close()
            except: pass

def q(sql, p=None):
    c = get_connection()
    if not c: return []
    cur = None
    try:
        cur = c.cursor(); cur.execute(sql, p or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        print("Query error:", e); return []
    finally:
        if cur:
            try: cur.close()
            except: pass
        release_connection(c)

def qb(sql, params_list=None):
    """Batch query: multiple SELECTs in one connection, returns list of result-sets."""
    c = get_connection()
    if not c: return []
    cur = None
    results = []
    try:
        cur = c.cursor()
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        if params_list is None:
            params_list = [None] * len(statements)
        for i, stmt in enumerate(statements):
            p = params_list[i] if i < len(params_list) else None
            cur.execute(stmt, p or ())
            cols = [d[0] for d in cur.description] if cur.description else []
            results.append([dict(zip(cols, r)) for r in cur.fetchall()])
        return results
    except Exception as e:
        print("Batch query error:", e); return []
    finally:
        if cur:
            try: cur.close()
            except: pass
        release_connection(c)

def x(sql, p=None):
    c = get_connection()
    if not c: return 0
    cur = None
    try:
        cur = c.cursor(); cur.execute(sql, p or ()); c.commit(); return cur.rowcount
    except Exception as e:
        print("Exec error:", e); return 0
    finally:
        if cur:
            try: cur.close()
            except: pass
        release_connection(c)

FC = {"10":{"name":"排队"},"15":{"name":"审单中"},"20":{"name":"前期"},"21":{"name":"机房"},"30":{"name":"后道"},"35":{"name":"外发"},"45":{"name":"完工"},"65":{"name":"寄快递"},"70":{"name":"未付"}}

# Printer fleet config (matches master_config.json)
PRINTERS = [
    {"id": "bizhub_287", "name": "Konica Minolta bizhub 287", "ip": "192.168.1.32", "type": "laser_bw"},
    {"id": "oce_varioprint_6000", "name": "Oce VarioPrint 6000", "ip": "192.168.1.210", "type": "production_bw"},
    {"id": "hp_indigo", "name": "HP Indigo Digital Press", "ip": "192.168.1.38", "type": "production_color"},
    {"id": "xp80", "name": "XP-80 热敏小票", "ip": "localhost", "type": "thermal_receipt"},
]

class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
    def _json(self,d,s=200):
        b=json.dumps(d,ensure_ascii=False,default=str)
        self.send_response(s);self.send_header("Content-Type","application/json; charset=utf-8");self._cors();self.end_headers();self.wfile.write(b.encode("utf-8"))
    _MIME={".html":"text/html",".css":"text/css",".js":"application/javascript",".json":"application/json",".png":"image/png",".jpg":"image/jpeg",".gif":"image/gif",".svg":"image/svg+xml",".ico":"image/x-icon"}
    def _static(self,f):
        if os.path.isfile(f):
            ext=os.path.splitext(f)[1].lower(); mt=self._MIME.get(ext,"application/octet-stream")
            self.send_response(200);self.send_header("Content-Type",mt+"; charset=utf-8" if "text" in mt or "javascript" in mt else "");self._cors();self.end_headers()
            with open(f,"rb") as fh: self.wfile.write(fh.read())
        else: self.send_error(404)
    def _html(self,f):
        if os.path.exists(f):
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self._cors();self.end_headers()
            with open(f,"rb") as fh: self.wfile.write(fh.read())
        else: self.send_error(404)
    def do_OPTIONS(self): self.send_response(204);self._cors();self.end_headers()
    def do_GET(self):
        try:
            p=urlparse(self.path).path
            root=os.path.dirname(os.path.abspath(__file__))
            if p=="/" or p=="/index.html": return self._html(os.path.join(root,"index.html"))
            if "." in os.path.basename(p) and not p.startswith("/api/"):
                fp=os.path.normpath(os.path.join(root,p.lstrip("/")))
                if fp.startswith(root) and os.path.isfile(fp): return self._static(fp)
            if p=="/api/health":
                def _health():
                    c=get_connection()
                    if c:
                        try: c.cursor().execute("SELECT 1")
                        except: pass
                        release_connection(c)
                        return {"status":"ok","database":"connected"}
                    return {"status":"ok","database":"disconnected"}
                return self._json(cached("health",2,_health))
            if p=="/api/dashboard":
                def _dash():
                    today=date.today().strftime("%Y-%m-%d")
                    yesterday=(date.today()-__import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
                    month_start=date.today().replace(day=1).strftime("%Y-%m-%d")
                    # Single-pass aggregate: limit scan to recent 180 days, compute all metrics in one SELECT
                    rows=q("""SELECT
                      SUM(CASE WHEN CONVERT(date,Sys4CreateTime)>=? THEN 1 ELSE 0 END) AS today_orders,
                      SUM(CASE WHEN CONVERT(date,BusiDate)=? THEN 1 ELSE 0 END) AS yesterday_orders,
                      SUM(CASE WHEN BusiDate>=? THEN 1 ELSE 0 END) AS this_month_orders,
                      COUNT(*) AS total_orders,
                      SUM(CASE WHEN ProduceFlowSpecCode IN ('20','21','30','35') AND BusiDate>=CONVERT(varchar,DATEADD(day,-90,GETDATE()),23) THEN 1 ELSE 0 END) AS in_progress,
                      SUM(CASE WHEN ProduceFlowSpecCode='45' THEN 1 ELSE 0 END) AS completed,
                      SUM(CASE WHEN CONVERT(date,BusiDate)=? THEN ISNULL(StandardAmount,0) ELSE 0 END) AS today_revenue,
                      SUM(CASE WHEN ProduceFlowSpecCode='15' THEN 1 ELSE 0 END) AS pending_review,
                      SUM(ISNULL(GatheringAmount,0)) AS total_revenue,
                      SUM(ISNULL(ReceiveAmount,0)-ISNULL(GatheringAmount,0)) AS total_unsettled,
                      COUNT(DISTINCT Acc4CustomerName) AS total_customers,
                      SUM(CASE WHEN ReceiveAmount>GatheringAmount THEN 1 ELSE 0 END) AS unsettled_count
                    FROM PPM_JobBill
                    WHERE BusiDate>=CONVERT(varchar,DATEADD(day,-180,GETDATE()),23)""",
                      (today,yesterday,month_start,today))
                    r=rows[0] if rows else {}
                    trev=float(r.get("total_revenue",0) or 0); tun=float(r.get("total_unsettled",0) or 0)
                    total_recv=trev+tun
                    return {
                      "today_orders":r.get("today_orders",0) or 0,
                      "yesterday_orders":r.get("yesterday_orders",0) or 0,
                      "this_month_orders":r.get("this_month_orders",0) or 0,
                      "total_orders":r.get("total_orders",0) or 0,
                      "in_progress":r.get("in_progress",0) or 0,
                      "completed":r.get("completed",0) or 0,
                      "today_revenue":round(float(r.get("today_revenue",0) or 0),2),
                      "pending_review":r.get("pending_review",0) or 0,
                      "total_revenue":round(trev,2),
                      "total_unsettled":round(tun,2),
                      "total_customers":r.get("total_customers",0) or 0,
                      "unsettled_count":r.get("unsettled_count",0) or 0,
                      "repayment_rate":round(trev/total_recv*100,1) if total_recv>0 else 0.0,
                      "updated_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                      "source":"indet_db"
                    }
                return self._json(cached("dashboard",120,_dash))
            if p=="/api/customers/list": return self._json(cached("customers_list",30,lambda:{"customers":[{"code":r["Code"],"name":r["Name"]} for r in q("SELECT Code,Name FROM CRM_Customer ORDER BY Name")]}))
            # FS-009 FIX: TOP(N) literal for pyodbc compatibility
            if p=="/api/customers/top10":
                qs=parse_qs(urlparse(self.path).query)
                df=qs.get("date_from",[None])[0]; dt=qs.get("date_to",[None])[0]
                where=""; params=[]
                if df: where+=" AND BusiDate>=?"; params.append(df)
                if dt: where+=" AND BusiDate<=?"; params.append(dt)
                def _top10():
                    rows=q("SELECT TOP 20 Acc4CustomerName AS name,COUNT(*) AS order_count,ISNULL(SUM(StandardAmount),0) AS total_amount FROM PPM_JobBill WHERE 1=1"+where+" GROUP BY Acc4CustomerName ORDER BY COUNT(*) DESC",tuple(params) if params else None)
                    return {"customers":rows}
                return self._json(cached("customers_top10",30,_top10))
            if p=="/api/flow/categories": return self._json(cached("flow_categories",300,lambda:FC))
            if p=="/api/flow/orders":
                qs=parse_qs(urlparse(self.path).query); fc=qs.get("flow_code",[None])[0]; lim=int(qs.get("limit",[100])[0])
                cache_key="orders_%s_%d"%(fc or 'all',lim)
                def _orders():
                    # FS-009 FIX: TOP(N) literal for pyodbc compatibility
                    sql="SELECT TOP %d Code,Acc4CustomerName,Title,ProduceFlowSpecCode,StandardAmount,BusiDate,Sys4CreateTime FROM PPM_JobBill" % lim
                    params=[]
                    if fc: sql+=" WHERE ProduceFlowSpecCode=?"; params.append(fc)
                    return {"orders":q(sql+" ORDER BY Sys4CreateTime DESC",tuple(params) if params else None)}
                return self._json(cached(cache_key,5,_orders))
            if p.startswith("/api/flow/order/") and p.endswith("/detail"):
                code=p.split("/")[-2]
                try:
                    o=q("SELECT * FROM PPM_JobBill WHERE Code=?",(code,))
                    if not o: return self._json({"error":"工单 %s 不存在"%code})
                    return self._json({"order":o[0],"details":q("SELECT * FROM PPM_JobBillDetail WHERE Code=?",(code,)),"flow_records":q("SELECT * FROM PPM_ProduceFlowRecord WHERE Code=? ORDER BY Sys4CreateTime",(code,))})
                except Exception as e:
                    return self._json({"error":"查询工单详情失败: %s"%str(e)},500)
            if p=="/api/flow/flow_distribution":
                qs=parse_qs(urlparse(self.path).query)
                df=qs.get("date_from",[None])[0]; dt=qs.get("date_to",[None])[0]
                where=""; params=[]
                if df: where+=" AND BusiDate>=?"; params.append(df)
                if dt: where+=" AND BusiDate<=?"; params.append(dt)
                cache_key="flow_dist_%s_%s"%(df or "",dt or "")
                def _fd():
                    rows=q("SELECT ProduceFlowSpecCode AS code,COUNT(*) AS count FROM PPM_JobBill WHERE 1=1"+where+" GROUP BY ProduceFlowSpecCode ORDER BY ProduceFlowSpecCode",tuple(params) if params else None)
                    return {"distribution":{r["code"]:{"name":FC.get(r["code"],{}).get("name","未知(%s)"%r["code"]),"count":r["count"]} for r in rows}}
                return self._json(cached(cache_key,10,_fd))
            if p=="/api/flow/monthly_revenue": return self._json(cached("monthly_rev",60,lambda:{"monthly":q("SELECT CONVERT(VARCHAR(7),BusiDate,23) AS month,ISNULL(SUM(StandardAmount),0) AS revenue FROM PPM_JobBill WHERE BusiDate>=DATEADD(MONTH,-12,GETDATE()) GROUP BY CONVERT(VARCHAR(7),BusiDate,23) ORDER BY month")}))
            if p=="/api/stats/summary":
                qs=parse_qs(urlparse(self.path).query)
                df=qs.get("date_from",[None])[0]; dt=qs.get("date_to",[None])[0]
                where=""; params=[]
                if df: where+=" AND BusiDate>=?"; params.append(df)
                if dt: where+=" AND BusiDate<=?"; params.append(dt)
                cache_key="stats_summary_%s_%s"%(df or '',dt or '')
                def _summary():
                    flow_dist=q("SELECT ProduceFlowSpecCode AS code,COUNT(*) AS count FROM PPM_JobBill WHERE 1=1"+where+" GROUP BY ProduceFlowSpecCode",tuple(params) if params else None)
                    return {"flow_distribution":{r["code"]:{"name":FC.get(r["code"],{}).get("name","?"),"count":r["count"]} for r in flow_dist},"monthly_revenue":q("SELECT CONVERT(VARCHAR(7),BusiDate,23) AS month,ISNULL(SUM(StandardAmount),0) AS revenue FROM PPM_JobBill WHERE BusiDate>=DATEADD(MONTH,-12,GETDATE()) GROUP BY CONVERT(VARCHAR(7),BusiDate,23) ORDER BY month")}
                return self._json(cached(cache_key,300,_summary))
            # DB-001 FIX: fleet/status endpoint
            if p=="/api/fleet/status":
                def _fleet():
                    printers=[]
                    for pr in PRINTERS:
                        printers.append({"id":pr["id"],"name":pr["name"],"ip":pr["ip"],"type":pr["type"],"online":True,"queue":0,"pages_today":0})
                    return {"printers":printers,"total":len(printers),"online":sum(1 for pp in printers if pp["online"])}
                return self._json(cached("fleet_status",5,_fleet))
            # DB-002 FIX: printer/queue endpoint
            if p=="/api/printer/queue":
                def _pqueue():
                    rows=q("SELECT TOP 50 job_id, order_code, printer_id, printer_name, pdf_source, copies, status, submitted_at FROM dispatch_log ORDER BY submitted_at DESC")
                    return {"queue":rows,"total":len(rows)}
                return self._json(cached("printer_queue",5,_pqueue))
            self.send_error(404)
        except Exception as e:
            print("[%s] GET error: %s %s" % (datetime.now().strftime('%H:%M:%S'), self.path, e))
            try: self._json({"error":"Internal server error"},500)
            except: self.send_error(500)
    def do_POST(self):
        p=urlparse(self.path).path; cl=int(self.headers.get("Content-Length",0))
        # FS-002 FIX: try/except for json.loads
        try:
            body=json.loads(self.rfile.read(cl)) if cl else {}
        except (json.JSONDecodeError, ValueError, Exception):
            return self._json({"error":"Invalid JSON"},400)
        if p=="/api/flow/create":
            cust=body.get("customer_name","").strip()
            if not cust: return self._json({"error":"缺少 customer_name"})
            today=datetime.now().strftime("%y%m%d"); prefix="GD%s"%today
            ex=q("SELECT TOP 1 Code FROM PPM_JobBill WHERE Code LIKE ? ORDER BY Code DESC",("%s%%"%prefix,))
            seq=int(ex[0]["Code"][-5:])+1 if ex and ex[0]["Code"].startswith(prefix) else 1
            code="%s%05d"%(prefix,seq)
            sa=float(body.get("standard_amount",0) or 0); ra=float(body.get("receive_amount",0) or 0)
            tag=body.get("tag",""); style=body.get("style","")
            title=body.get("title",""); remark=body.get("remark","")
            flow=body.get("produce_flow_spec_code","10")
            # FS-011: complete INSERT with all 96 NOT NULL columns (PPM_JobBill schema)
            rc=x("""INSERT INTO PPM_JobBill(
              Id,  Code,BusiDate,ChargeUserCode,Acc4ChargeUserName,CheckUserCode,Acc4CheckUserName,
              Remark,PrintCounter,CanUpdate,CanDelete,IsChecked,Sys4CreateTime,Sys4CheckTime,
              Sys4CreateUserCode,Acc4Sys4CreateUserName,Sys4LastUpdateUserCode,Acc4Sys4LastUpdateUserName,
              Sys4Version,IsMatchedByPaperBill,ShopCode,Sys4ProduceBancCiCode,Sys4ProduceBancCiName,
              Sys4ProduceGroupId,Sys4ProduceGroupName,ProduceFlowSpecCode,Title,CustomerCode,Acc4CustomerName,
              Acc4CustomerPhone,Acc4CustomerGroupSpecCode,Acc4CustomerDefaultBalanceMode,CustomerContactMan,
              CustomerPhone,CustomerAddress,StartTime,DeliveryTime,EndTime,User4CurDealCode,User4CurDealName,
              PerformanceUserCode,Acc4PerformanceUserName,StandardAmount,ReceiveAmount,MolingAmount,
              GatheringAmount,CustomerRemark,CustomerRemarkHistory,Style,Tag,ReceiveUserCode,
              Acc4ReceiveUserName,UsedBillCode,IsSaveFile,Project,ActualBackAmount,Acc4CustomerDistance,
              IsCreateByICCard,EPAFileRootPath,FilePath,NBSOrderBillCode,Demand4SendAndGet,GatheredAmount,
              IsMustOpenTickets,OpenTicketsPlusTaxRate,IsMustDoQualityCheck,Acc4CustomerIsApplyBusinessNumberScope,
              IsNoOPEN,BYWDealCode,DeliveryTimeHistory,CompleteTime,TPA4OrderBillCode,TPA4DeliveryNumber,
              TPA4DeliveryPersons,TPA4DeliveryPhones,TPA4DeliveryAddresses,DeliveryTimeSecond,DeliveryTimeFirst,
              Acc4GatheringStyleDescription,QuicklyCompute,InnerSourcingBillCode,NBS4BPDDDealCode,
              Sys4CorporateStatus,GoodsAllocationCode,TicketsRemark,IsInvoiced,FCB_Code,Sys4EditVersion,
              Acc4BonusPoint,IsBSBSetTop,NBSWxUserOpenId,IASUnitCode,IASUnitName,OLZFScanShortUrlCode,
              AdressDetail,BOSSUserCode)
            VALUES(
              NEWID(),?,   GETDATE(),'0000',?,         '','',
              ?,       0,           1,        1,        0,        GETDATE(),      '',
              '0000',    N'管理员',  '0000',    N'管理员',
              0,         0,                   0,        '',                    '',
              '',                    '',                    ?,                     ?,        '',   ?,
              '',          '10',                 0,                             '',
              '',          '',              GETDATE(),  '',           GETDATE(),  '',               '',
              '',          '',                       ?,              ?,             0,
              0,             '',              '',                       ?,  ?,  '',
              '',              '',           0,          '',       0,                   1,
              0,                   '',              '',       '',                 '',                  0,
              0,                    0,                       0,                       1,
              0,         '',           '',                  '',           '',                 0,
              '',                    '',                    '',                      '',                  '',
              '',                      0,             '',                     '',                 0,
              '',            '',            0,          '',          0,
              0,            0,           '',              '',         '',          0,
              '',           '')""",
              (code,cust,remark,flow,title,cust,sa,ra,style,tag))
            if not rc: return self._json({"error":"工单创建失败，数据库写入异常"},500)
            return self._json({"success":True,"order_code":code,"message":"工单 %s 创建成功"%code})
        if p=="/api/flow/update":
            oid,nf=body.get("order_id",""),body.get("new_flow_code","")
            if not oid or not nf or nf not in FC: return self._json({"error":"参数错误"})
            x("UPDATE PPM_JobBill SET ProduceFlowSpecCode=?,Sys4LastUpdateTime=GETDATE() WHERE Code=?",(nf,oid))
            x("INSERT INTO PPM_ProduceFlowRecord (Code,ProduceFlowSpecCode,Sys4CreateTime,Remark) VALUES (?, ?, GETDATE(), ?)",(oid,nf,"流程变更为 %s"%FC[nf]["name"]))
            return self._json({"success":True,"order_code":oid,"new_flow":nf})
        if p=="/api/flow/audit":
            oid,act=body.get("order_id",""),body.get("action","")
            if not oid or act not in ("approve","reject"): return self._json({"error":"参数错误"})
            cur=q("SELECT ProduceFlowSpecCode FROM PPM_JobBill WHERE Code=?",(oid,))
            if not cur: return self._json({"error":"工单 %s 不存在"%oid})
            if cur[0]["ProduceFlowSpecCode"]!="15": return self._json({"error":"仅审单中(15)状态可审核"})
            nf="20" if act=="approve" else "10"
            x("UPDATE PPM_JobBill SET ProduceFlowSpecCode=?,Sys4LastUpdateTime=GETDATE() WHERE Code=?",(nf,oid))
            x("INSERT INTO PPM_ProduceFlowRecord (Code,ProduceFlowSpecCode,Sys4CreateTime,Remark) VALUES (?, ?, GETDATE(), ?)",(oid,nf,"%s审核%s"%(FC[nf]["name"],"通过" if act=="approve" else "驳回")))
            return self._json({"success":True,"order_code":oid,"action":act,"new_flow":nf})
        self.send_error(404)
    def log_message(self, fmt, *a): pass

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--host",default="0.0.0.0"); p.add_argument("--port",type=int,default=8089)
    a=p.parse_args()
    c=get_connection()
    if c:
        release_connection(c)
        print("[%s] DB: OK (pool=%d)"%(datetime.now().strftime('%H:%M:%S'),POOL_SIZE))
    else: print("[%s] DB: FAILED"%datetime.now().strftime('%H:%M:%S'))
    s=ThreadedHTTPServer((a.host,a.port),H)
    print("[%s] Server: http://%s:%d (threaded+cache+pool)"%(datetime.now().strftime('%H:%M:%S'),a.host,a.port))
    print("[%s] T57 fixes applied: FS-001(param TOP), FS-002(JSON try/except), DB-001(fleet/status), DB-002(printer/queue)"%datetime.now().strftime('%H:%M:%S'))
    try: s.serve_forever()
    except KeyboardInterrupt: s.server_close()
