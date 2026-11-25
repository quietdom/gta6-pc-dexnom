import re, glob, os
d = max(glob.glob(r'C:\Users\Administrator\AppData\Local\DexNom Runtime\logs\run-*.log'), key=os.path.getmtime)
raw = open(d,'rb',buffering=0).read()
t = raw.decode('utf-16','replace') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8','replace')
t = re.sub(r'\x1b\[[0-9;]*m','',t)
rec=[]
for line in t.splitlines():
    if re.match(r'^\d{4}-\d\d-\d\dT', line) or not rec: rec.append(line.rstrip())
    else: rec[-1]+=' '+line.strip()
def show(pat, n=3, w=200):
    m=[r for r in rec if re.search(pat, r, re.I)]
    print('\n--- %s  (%d)' % (pat, len(m)))
    for r in m[-n:]:
        b = r.split(': ',2)[-1]
        print('  ', b[:w])
show(r'fallback', 2)
show(r'unmapped page')
show(r'copies that|copy-back|copied back', 2)
show(r'pipeline', 3, 230)
