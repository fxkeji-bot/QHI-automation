import sqlite3, json
db = r'C:\Users\diy\.qhi_processor\qhi_enterprise.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('Tables:', tables)

for t in tables:
    if any(kw in t.lower() for kw in ['device', 'printer', 'machine']):
        print(f'\n=== {t} ===')
        cur.execute(f'PRAGMA table_info({t})')
        for c in cur.fetchall(): print(f'  {c}')
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        cnt = cur.fetchone()[0]
        print(f'  Count: {cnt}')
        if cnt > 0:
            cur.execute(f'SELECT * FROM {t} LIMIT 3')
            for r in cur.fetchall(): print(f'  {str(r)[:150]}')

conn.close()
