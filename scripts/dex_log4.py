import re, glob, os
d = max(glob.glob(r'C:\Users\Administrator\AppData\Local\DexNom Runtime\logs\run-*.log'), key=os.path.getmtime)
raw = open(d,'rb',buffering=0).read()
t = raw.decode('utf-16','replace') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8','replace')
t = re.sub(r'\x1b\[[0-9;]*m','',t)
rec=[]
for line in t.splitlines():
    if re.match(r'^\d{4}-\d\d-\d\dT', line) or not rec: rec.append(line.rstrip())
    else: rec[-1]+=' '+line.strip()
fr=[x for x in rec if 'fps' in x]
print('frame lines:', len(fr))
for r in fr[-3:]:
    body = r.split(': ',2)[-1]
    print('\n', r[:19])
    print(' ', body[:520])
print('\n--- pipeline library lines')
for r in [x for x in rec if 'pipeline library' in x][-3:]:
    print(' ', r[:300])
