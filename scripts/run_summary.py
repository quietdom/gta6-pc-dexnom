"""Summarise a VIctory log: errors, warnings, frame lines, and the end."""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r'C:\GTA6\victory-run25.log'
with open(path, 'rb', buffering=0) as f:
    data = f.read()
text = data.decode('utf-16', 'replace') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else data.decode('utf-8', 'replace')
text = re.sub(r'\x1b\[[0-9;]*m', '', text)

records = []
for line in text.splitlines():
    if re.match(r'^\d{4}-\d\d-\d\dT', line) or not records:
        records.append(line.rstrip())
    else:
        records[-1] += ' ' + line.strip()

print(f'{len(records)} records, first {records[0][:19] if records else "-"}, last {records[-1][:19] if records else "-"}')

print('\n--- first 12')
for r in records[:12]:
    print(' ', r[:220])

print('\n--- ERROR / WARN / panic / device')
for r in records:
    if re.search(r'ERROR|WARN|panic|device removed|DEVICE_HUNG|E_FAIL|failed', r, re.I):
        print(' ', r[:240])

print('\n--- frame lines')
for r in records:
    if 'fps,' in r or 'ms/frame' in r:
        print(' ', r[r.find('victory_gpu'):][:260])

print('\n--- last 12')
for r in records[-12:]:
    print(' ', r[:240])
