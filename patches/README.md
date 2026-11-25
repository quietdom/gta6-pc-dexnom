# Patches against DexNom/VIctory

Both apply to **`DexNom/VIctory` at `921d8d3`** (branch `main`).

```powershell
cd C:\GTA6\dex
git apply path\to\0001-victory-gpu-host-copy-inplace.patch
git apply path\to\0002-victory-hle-window-size.patch
cargo build --locked --release -p victory --features diagnostics --bins
```

Then copy `victory.exe`, `victory-play.exe` and `victory-warm.exe` from `target\release`
over `%LOCALAPPDATA%\DexNom Runtime`, and re-warm.

## 0001 - victory-gpu/src/host.rs: copy shadow refreshes in place

`copy_mapped` moved every shadow refresh through
`ReadProcessMemory(GetCurrentProcess(), ...)`. The kernel call existed only so that an
unmapped page came back as an error instead of an access violation, and it copies at a
flat **2.39 GB/s** regardless of size. The tree already copies the same memory in place
elsewhere at ~8 GB/s.

The patch pins the source range with `watch::title_memory_reading_now` (a try-lock, so it
never blocks the submit thread), asks `texture::committed` - one `K32QueryWorkingSetEx` per
256 pages, no page-table walk - and then does a plain `ptr::copy_nonoverlapping`. Ranges
with holes, a mapping in flight, or a title destination fall through to the original kernel
path unchanged. `VICTORY_COPY_PLAIN=0` disables the new path without a rebuild.

Measured effect: **2.39 -> 3.49 GB/s** on the copies bucket. Adoption is partial (~40% of
bytes) because the try-lock loses to four fill workers and `committed` refuses spans with
trimmed pages.

## 0002 - victory-hle/src/modules/lifecycle.rs: window size override

`fit()` only ever shrank an oversized window to the work area. This adds
`VICTORY_WINDOW=<width>x<height>` (`320x200` minimum) applied to the title's top-level
window, so the render target can be dropped without touching the title's own resolution
logic. Unset, behaviour is exactly as upstream.
