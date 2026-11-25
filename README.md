# GTA VI (Xbox Series X, 1.0.2.1) on PC - DexNom runtime log

Live engineering notes for running the **Xbox Series X build of GTA VI (1.0.2.1,
`game_scarlett_master.exe`)** on Windows x64 through **DexNom/VIctory** - a source-only
D3D12 translation runtime for Xbox Series titles.

Everything here is measured on the machine below. Estimates are labelled as such.
This file is updated as runs happen.

---

## Status

| | |
|---|---|
| Boot | working - title reaches the prison intro and gameplay |
| Rendering | world, characters, interiors, subtitles all draw |
| Frame rate | **8 fps / 252 ms** at 854x480, GPU 35% busy |
| Target | 10-15 fps stable |
| Blockers | CPU-side heap-buffer pass, copy-back, missing host pipelines |

---

## Hardware

| | |
|---|---|
| CPU | Intel i7-11700K, 8C/16T, 3.6 GHz base, Rocket Lake, PCIe 4.0 |
| RAM | 2 x 16 GB G.Skill F4-3600C18-16GTZR @ **3200 MT/s** (gear 1), 51.2 GB/s peak |
| GPU | AMD Radeon RX 6800, 16 GB VRAM, ~512 GB/s |
| OS | Windows 11 x64, 32 GB visible, 45 GB commit limit |

---

## Runtime

- Fork: **https://github.com/DexNom/VIctory**, branch `main`, commit `921d8d3`
- Installed with their `Setup.cmd` to `%LOCALAPPDATA%\DexNom Runtime`
- Local source tree: `C:\GTA6\dex`

### Build

```
cd C:\GTA6\dex
cargo build --locked --release -p victory --features diagnostics --bins
```

Copy `victory.exe`, `victory-play.exe`, `victory-warm.exe` from `target\release` over
`%LOCALAPPDATA%\DexNom Runtime`.

### Warm the shader cache (before every run)

`victory-warm.exe` wants the launcher's state lock; `victory.exe warm` does not.

```
cd "$env:LOCALAPPDATA\DexNom Runtime"
$env:VICTORY_GAME_DIR  = 'C:\GTA6\GTA6.Xbox.v1.0.2.1.CYBERLEEK-GameDrive.Org.part1\GTA6.Xbox.v1.0.2.1-CYBERLEEK'
$env:VICTORY_CACHE_DIR = "$env:LOCALAPPDATA\DexNom Runtime\cache"
$env:VICTORY_DATA_DIR  = "$env:LOCALAPPDATA\DexNom Runtime\state"
.\victory.exe warm --jobs 16
```

- Cold: **758 s**, 25 748 shaders translated, 10 refused, 2 734 compute pipelines
- Warm (cache present): **55-65 s**, same counts, cache unchanged at **831.3 MB**
- A binary rebuild does **not** invalidate the shader cache

### Run

```
cd "$env:LOCALAPPDATA\DexNom Runtime"
.\victory-play.exe
```

---

## Measurements

Frame buckets are per frame. The heap-buffer figure is CPU time summed over the fill
workers, so it can exceed the wall-clock frame.

| run | window | draws/frame | frame | copies | copy-back | heap pass | GPU |
|---|---|---|---|---|---|---|---|
| 1, cold cache | 768x432 | 6 893 | 1 046.8 ms | 169.2 ms / 216 MB | 54.6 ms | 1 569 ms | 46.4 ms |
| 3, tuned switches | 960x540 | 1 583 | ~350-400 ms | 96.2 ms / 229.5 MB | 114.4 ms | 106.6 ms | 28.3 ms |
| 5, in-place copy patch | 854x480 | 6 374-10 679 | 465-597 ms | 82.3 ms / 286.9 MB (3.49 GB/s) | 127.5 ms | 2 405 ms | 61.2 ms |
| 5, settled | 854x480 | 6 278 | **252.3 ms** | - | - | - | 88 ms (35%) |

Runtime switches in use:

```
VICTORY_WINDOW=854x480
VICTORY_FILL_WORKERS=4
VICTORY_PARALLEL_PRELUDES=1
VICTORY_UNWATCHED_FRAMES=2
VICTORY_TEXTURE_STAGE_MB=384
```

---

## Where the time goes

At 854x480 and ~6.3 k draws the GPU is **35% busy** - it finishes its work and waits.
The frame is CPU-bound.

1. **Heap-buffer pass - ~2.4 s of CPU per frame** (`victory-gpu/src/draw.rs:1628`,
   `shadow.refresh`). The single largest cost by a wide margin. Copies heap-buffer spans
   from title memory into host shadows every frame, or every other frame with
   `VICTORY_UNWATCHED_FRAMES=2`.
2. **Copy-back - 127 ms / 60 MB** (`shadow.rs`), GPU-written memory merged back into the
   title. Already uses `NtWriteVirtualMemory` (`VICTORY_DIRECT_WRITES`, on by default).
3. **Copies - 82 ms / 287 MB** (`host.rs:6261 copy_mapped`). Was 2.39 GB/s through
   `ReadProcessMemory` on our own process; now partly in-place at 3.49 GB/s.
4. **Textures - 9-55 ms / 26-60 MB**, with 1 000-11 700 slots waiting at any time.

### The copy patch

`copy_mapped` used `ReadProcessMemory(GetCurrentProcess(), ...)` for every shadow refresh.
The kernel call existed only to turn an unmapped page into an error instead of an access
violation, and it copies at a flat 2.39 GB/s. The patch pins the source range with
`watch::title_memory_reading_now`, asks `texture::committed` (one `K32QueryWorkingSetEx`
per 256 pages, no page-table walk), and does a plain `ptr::copy_nonoverlapping` when every
page is there. Unmapped ranges, holes and in-flight remaps fall through to the old path.
`VICTORY_COPY_PLAIN=0` reverts it.

Adoption is partial (~40% of bytes): the try-lock loses to four fill workers, and
`committed` refuses spans with trimmed pages.

---

## Open defects

Rendering is correct enough to play but not complete.

- **Weapon model missing.** The player's gun does not draw. The frame line reports
  `dropped N without a host pipeline (0 being made)` - the draw is skipped because no host
  pipeline exists for it, and `0 being made` means it is never built.
- **Untextured arms/hands** on some characters - the mesh draws, the skin texture does not.
- **One NPC renders red.** Skin texture comes out saturated red, consistent with a channel
  or format mix-up on one texture format rather than a lighting problem.
- **Dropped draws, 353-3 287 per frame**, all with no host pipeline.

These are pipeline- and texture-side, separate from the frame-rate work. All four have a
change on upstream `main` - see **Landed upstream** below.

---

## Landed upstream (cold-project-vi main)

Source changes live in **https://github.com/felicienradio/cold-project-vi**, branch `main`,
commits go straight to `main`. The three below are ports into the tree this log runs
(`C:\GTA6\dex`). All three pass `cargo check -p victory-gpu`.

None of them has been measured on a run yet. Every figure under Measurements predates them.

| commit | title | defect it targets | knob |
|---|---|---|---|
| `7103c75` | `shader: name the SGPR behind 'a hardware SGPR input'` | A translator refusal printed one generic string, so a refused shader could not be traced to the input that caused it. The message now names the SGPR. | none |
| `0f06d8a` | `gpu: a failed pipeline gets another attempt` | Host pipeline creation was cached in a `OnceLock`, so one failed PSO stayed failed for the rest of the run. That is the `0 being made` in the frame line, and the permanent `dropped N without a host pipeline`. | `VICTORY_PIPELINE_RETRY_FRAMES`, default `300` frames |
| `e321a74` | `gpu: a slot whose pages are away keeps its host copy for a while` | A texture slot whose pages were unmapped lost its host copy immediately and bound null, so a streaming texture sampled nothing for that frame. This is the untextured arms/hands and the red NPC. | `VICTORY_TEXTURE_KEEP_MS`, default `2000` ms |

### `0f06d8a` - pipeline retry

`made` is a `OnceLock<HostPipeline>`; `failed_frame` and `failures` record the last attempt
and the attempt count. `due()` decides whether this frame owes a retry and `retry_frames()`
reads `VICTORY_PIPELINE_RETRY_FRAMES`. On failure `queue_state` returns to `NOT_QUEUED` so
the next due frame asks again, and `missing()` reports `N attempts` instead of `0 being made`.

A failed PSO is retried once its last attempt is `VICTORY_PIPELINE_RETRY_FRAMES` old, so a
pipeline that will never build costs one attempt every 300 frames instead of one attempt for
the whole run.

### `e321a74` - texture slots that are away

`Waiting.mapped_at` stamps the frame a slot's pages went away, `TextureQueue::away()` reports
how long they have been gone, and `HostHeap::texture_slot_away()` exposes that to the draw
pass. The pass keeps the host copy for `VICTORY_TEXTURE_KEEP_MS` before letting the slot go,
so the sampling bind still has bytes behind it in the frame the pages are missing.

New frame-line fields next to the drop counters:

```
passed over unmapped (N kept their host copy, M let go)
```

---

## Next

1. `VICTORY_INPLACE=1` - open title memory as a host heap so shaders read it directly, no
   shadow copy. Targets the 2.4 s heap pass at the source.
2. Copy-back: 127 ms for 60 MB is 470 MB/s; find where it is spent.
3. Drop the window to 640x360 (44% fewer pixels than 854x480) once the CPU side is fixed.
4. Pipeline drops: the next run measures `0f06d8a`. The drop trace should carry `N attempts`
   where it carried `0 being made`; the dropped-draw count (353-3 287 per frame) is the
   figure to compare against.
5. Texture sampling: the next run measures `e321a74`. The frame line should carry
   `passed over unmapped (N kept their host copy, M let go)`, and the red-face and
   untextured-arms defects are checked against it - reduced or not.

---

## Reproduce

1. Install the runtime with `Setup.cmd` pointing at `game_scarlett_master.exe`.
2. Warm with `victory.exe warm --jobs 16` (see above).
3. Launch `victory-play.exe` with the switches listed under Measurements.
4. The window caption carries the live figures: `fps | ms/frame | gpu % | cpu % | ram | draws/frame | up`.
5. Per-frame detail is in `%LOCALAPPDATA%\DexNom Runtime\logs\run-*.log`.

---

## Repository layout

```
README.md                     status, measurements, defects, next
patches/                      our changes to DexNom/VIctory, as git patches
  0001-victory-gpu-host-copy-inplace.patch   copy shadow refreshes in place (host.rs)
  0002-victory-hle-window-size.patch         VICTORY_WINDOW override (lifecycle.rs)
config/                       the exact switches and commands
  env.ps1                     every VICTORY_* a run uses
  warm.ps1                    shader warm (victory.exe warm, not victory-warm.exe)
  launch.ps1                  launch
  victory.toml                path config
scripts/                      log readers - UTF-16/ANSI safe, shared access on a live log
  dex_frame.py                last frame lines + copies rate in GB/s
  dex_probe.py                copystat, copy-back checks, pipeline lines
  dex_log4.py                 last frame lines, fields split
  tail_log.py                 tail with records rejoined
  run_summary.py              one run condensed
docs/
  copyback-attribution.md     where the 2 s frames went in the older tree, commit by commit
```

Nothing in this repository is a game file. The title, its archives and its shader
containers stay where they are installed. This is the runtime work around them: patches,
switches, readers, and the numbers they produced.

---
*Unofficial. Not affiliated with Rockstar Games or Take-Two. No game files are
distributed here - only measurements, patches and notes against an open-source runtime.*

