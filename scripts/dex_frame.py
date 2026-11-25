import re, glob, os
d = max(glob.glob(r'C:\Users\Administrator\AppData\Local\DexNom Runtime\logs\run-*.log'), key=os.path.getmtime)
raw = open(d,'rb',buffering=0).read()
t = raw.decode('utf-16','replace') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8','replace')
t = re.sub(r'\x1b\[[0-9;]*m','',t)
rec=[]
for line in t.splitlines():
    if re.match(r'^\d{4}-\d\d-\d\dT', line) or not rec: rec.append(line.rstrip())
    else: rec[-1]+=' '+line.strip()
print('log', os.path.basename(d), len(rec), 'records')
fr=[x for x in rec if 'draws/frame' in x]
print('frame lines:', len(fr))
for r in fr[-5:]:
    body = r.split(': ',2)[-1]
    m = re.search(r'copies ([\d.]+) ms ([\d.]+) MB', body)
    rate = ''
    if m and float(m.group(2))>0: rate = '  -> %.2f GB/s' % (float(m.group(2))/float(m.group(1))/1000*1000/1000*1000/1000) if False else '  -> %.2f GB/s' % (float(m.group(2))/float(m.group(1)))
    print('\n', r[:19], rate)
    print(' ', body[:430])
