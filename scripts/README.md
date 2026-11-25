# Log readers

The runtime writes UTF-16 or UTF-8 logs with ANSI colour and records wrapped across lines.
Every script here opens the newest `run-*.log` with shared access (a live run holds it), and
rejoins wrapped records before matching.

| script | what it prints |
|---|---|
| `dex_frame.py` | the last five frame lines, plus the copies rate in GB/s derived from `ms` and `MB` |
| `dex_log4.py` | the last three frame lines, split into the fields that matter |
| `dex_probe.py` | the `copystat` line (title copies, refreshes, moves, page faults, watches), copy-back checks, pipeline lines |
| `tail_log.py` | tail of the live log with ANSI stripped and records rejoined |
| `run_summary.py` | one run condensed to its numbers |

```powershell
py scripts\dex_frame.py
```

Python is `py` on this machine, not `python`. `capstone` and `blake3` are installed;
`pefile` is not.
