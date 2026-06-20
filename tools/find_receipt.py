import os
results = []
for r, ds, fs in os.walk(r'E:\qhi_processor'):
    for f in fs:
        if f.endswith('.py'):
            path = os.path.join(r, f)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    c = fh.read()
                    if any(k in c for k in ['58mm', '80mm', 'thermal', 'win32print', 'lpr ', 'print_queue', 'receipt_print']):
                        results.append(f'{path} ({len(c)} bytes)')
            except:
                pass
for r in results:
    print(r)
