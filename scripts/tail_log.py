"""Tail a VIctory log that another process is still writing.

Opens with FILE_SHARE_READ | FILE_SHARE_WRITE, strips ANSI, rejoins records
that were wrapped, and prints the last N records.
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else r'C:\GTA6\victory-run25.log'
count = int(sys.argv[2]) if len(sys.argv) > 2 else 14

with open(path, 'rb', buffering=0) as f:
    data = f.read()

if data[:2] == b'\xff\xfe':
    text = data.decode('utf-16')
elif data[:2] == b'\xfe\xff':
    text = data.decode('utf-16-be')
else:
    text = data.decode('utf-8', 'replace')

text = re.sub(r'\x1b\[[0-9;]*m', '', text)
records = []
for line in text.splitlines():
    if re.match(r'^\d{4}-\d\d-\d\dT', line) or not records:
        records.append(line.rstrip())
    else:
        records[-1] += ' ' + line.strip()

print(f'{len(records)} records')
for r in records[-count:]:
    print(' ', r[:400])
