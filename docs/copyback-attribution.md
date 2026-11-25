# Where a 2033-2266 ms frame goes

Branch `test/upstream-shaders`, HEAD `2dd5ce1`. Scope: `crates/victory-gpu/`.
Every line reference is to that tree.

Convention: **[measured]** is a number from the run log. **[derived]** is
arithmetic on measured numbers (the arithmetic is shown). **[code]** is a
property the source fixes without a measurement. Line references are to
`2dd5ce1`, before the change at the end of this document.

The frame:

| bucket | measured | bytes | dominant cost |
|---|---|---|---|
| `preparing` | 915-1156 ms | | of which the rows below |
| `preparing: copies` | 536-772 ms | 23.7-28.2 MB | `GetWriteWatch` over 5.6 GB + run-map queries + one memcpy |
| `preparing: textures` | 38-58 ms | 105-117 MB | one memcpy per texture, 1.8-3.1 GB/s |
| `preparing`: unlisted | 326-341 ms [derived] | 1.46 GB committed | `CreateCommittedResource` of copy-back readback staging |
| GPU | 235-249 ms | 1.46 GB read back | 730.8 MB before + 730.8 MB after |
| `copying back` | 553-713 ms | 4.2-5.5 MB written | 189.4 ms compare + per-run read/merge/write (run count not instrumented) |
| (inside that) compare scan | 189.4 ms | 730.8 MB compared | 11,152 `bcmp` over freshly committed pages |
| (inside copies) `watches` | 199.29 ms | 5626.3 MB walked | 581 `GetWriteWatch` calls |
| `moves` | 360.68 ms | 145 MB (28 + 117) | one copy pass, kernel or memcpy, plus the map queries (see §2) |

Sum of the four named buckets: 1362-1792 ms of 2033-2266. The unlisted
readback commit is the bulk of the remainder.

---

## 1. `preparing: copies` / `moves` — 536-772 ms for 23.7-28.2 MB

**Callsite.** `Host::run_deferred`, the `Step::Copy` arm,
`host.rs:1491-1501`; the timer that fills the bucket is
`host.rs:1489` → `host.rs:1547`, plus a second add in `Batch::flush`,
`host.rs:1601-1611`.

The arm does three things per title copy:

1. `batch.flush(host, upload_arena)` (`host.rs:1497`) — every pending
   `Shadow::update` for this submission.
2. `batch.title_written()` (`host.rs:1498`) — clears a `HashSet`, free.
3. `copy_mapped(dst, src, len, title_dst = true)` (`host.rs:1499`,
   `host.rs:1626-1678`), which is `watch::writing` (`host.rs:1655`) then
   `runs::for_runs` (`host.rs:1656`) then `copy_readable`
   (`host.rs:1741-1756`) which calls `runs::for_runs` **again**.

**Where the milliseconds are.** The bytes are 23.7-28.2 MB [measured], so
the bucket runs at 31-53 MB/s [derived: 23.7/0.772 to 28.2/0.536]. At a
resident memcpy rate that transfer is single-digit milliseconds, so at
most a few percent of this bucket is the copy. The rest is the machinery
the copy is wrapped in:

- **`watch::writes` → `GetWriteWatch`** (`watch.rs:143-152`), once per
  distinct refreshed range. 581 calls and 5626.3 MB walked per frame
  [measured], 199.29 ms [measured] — that is 28.2 GB/s of kernel
  page-table walk, 1,373,608 kernel pages [derived:
  5626.3e6 / 4096], 145 ns per page. The kernel must visit every 4 KiB
  page of the range to collect the dirty ones and clear the bits: cost
  is proportional to the *range*, not to what changed, and 5606.7 of
  5626.3 MB was unchanged [measured].
- **`runs::Map::ensure`** (`runs.rs:277-299`), at least twice per copy —
  once for the destination `for_runs`, once for the source
  `copy_readable`. On a miss it evicts the least recently used of eight
  windows and calls `Window::build` (`runs.rs:123-182`), which walks
  `[start - 64 MiB, end + 64 MiB)` — 128 MiB — one `VirtualQuery` per
  region, capped at `QUERIES = 1<<18`. `Window::access`
  (`runs.rs:184-221`) then calls `committed()`
  (`runs.rs:230-246`) — another `VirtualQuery` — for every gap the
  window calls uncommitted, up to `QUERIES_AT_ONCE = 64` per call.
- **`watch::writing` → `open`** (`watch.rs:282-297`): one
  `VirtualProtect` per guarded 64 KiB block in the range. Usually zero
  blocks, so usually free.
- `C::MoveUs` wraps 1 and 3 together, so the printed `moves 360.68 ms`
  is not memcpy time; it is memcpy **plus** the run-map queries for
  every `copy_mapped` call in the frame (title copies, refresh staging,
  textures, fills).

**Accounting.** `MoveUs` 360.68 ms [measured] is an upper bound on the
copy work in this bucket, and it also contains the 105-117 MB of texture
copying. So the part of 536-772 ms that is outside `copy_mapped`
altogether is at least 176-412 ms [derived: 536-360.68 to 772-360.68],
and that part is `batch.flush`'s `GetWriteWatch` plus `copy_stale`'s page
loop plus lock acquisition.

**Measurement defect, not a time defect.** The flush time inside a
`Step::Copy` is added to `PREPARING[0]` twice — once by `Batch::flush`
(`host.rs:1610`) and again by the step timer that was started before the
arm ran (`host.rs:1489`, added at `host.rs:1547`). The bucket named
"copies" therefore reports flush work twice. It does not make the frame
slower; it makes the bucket 199 ms larger than the code it names.

---

## 2. `copy-back` read + merge + write — 553-713 ms for 4.2-5.5 MB

**Callsites.** Driver loop `host.rs:872-887` (`COPY_BACK[0]` is taken
before the loop and added after `clear_pending`). Per plan:
`Shadow::copy_back_range`, `shadow.rs:187-312`.

Within it, four loops and one syscall:

| lines | what | bytes | calls |
|---|---|---|---|
| `shadow.rs:209-222` | compare scan | 730.8 MB | 11,152 `bcmp` |
| `shadow.rs:234-235` | whole-run read into title memory | 3.9 MB total | one per run |
| `shadow.rs:242-293` | per-64 KiB merge | 3.9 MB × 3 streams | one per piece |
| `shadow.rs:316-322` | `write_run` → `watch::writing` + `write_mapped` | 4.2-5.5 MB | one per changed span |
| `shadow.rs:298-309` | final `watch::writes` per plan | ≤730.8 MB | one per plan |

**Where the milliseconds are.** 553-713 ms total [measured], 189.4 ms of
it the scan [measured], which leaves 364-524 ms for moving 3.9 MB in and
4.2-5.5 MB out [measured] — about 8-9 MB at 15-26 MB/s [derived:
8.1/0.5236 to 9.4/0.3636]. At 348 MB/s through `WriteProcessMemory`
(the module's own measured figure) that work is 26 ms. So ~340-500 ms
is paid per *run*, not per byte. A run costs at most: one
`read_into` → `read` (`host.rs:1774-1794`) → `runs::readable`
(`runs.rs:309-313`) → `Map::ensure` + `Window::access`; then one
`write_run` → `watch::writing` → `open` → `write_mapped`
(`host.rs:1812-1858`) → `for_runs` → `ensure` + `access`, then one
memcpy. That is 2-4 map lookups and up to 2 window rebuilds per run.

**This bucket cannot be fully explained by the code as written.** Two
mechanisms fit 364-524 ms, and the counters given do not separate them:

- **A. `runs` window rebuilds.** `copy_back_range` walks planes of title
  memory scattered across pools; with eight windows and a 5 s TTL, each
  `ensure` for an address outside the covered windows evicts one and
  re-walks 128 MiB. At ~2,048 regions per window that is ~1-4 ms per
  rebuild, and hundreds of rebuilds is exactly 364-524 ms.
- **B. A failed-read storm.** `read_into` asks for a whole run at once.
  A single uncommitted page fails the whole run (`host.rs:1786-1789`),
  then the per-piece loop (`shadow.rs:246-251`) asks again 64 KiB at a
  time and counts each failure in `Skipped`/`SkippedBytes`
  (`shadow.rs:252-256`). If the copy-back ranges cover pages the title
  has since unmapped (tiled or freed pools), this is thousands of failed
  reads, each a kernel page-table walk.

The measurements that settle it, all already in the log:

- `skipped {n} {MB}` — the first half of the `copystat` line, not quoted
  in the report. A large `SkippedBytes` means B.
- `{queries} queries {ms} ms ({regions} mapped)` and the fps line's
  `{walks} map walks {ms} ms` (`host.rs:1990-1991`, `host.rs:2005`).
  Thousands of walks at ~1.5 ms means A.
- `VICTORY_SAFE_COPIES` in the run environment. If it was set, A is
  impossible (the map is bypassed) and B is the only surviving
  mechanism.

**An inconsistency worth recording.** `7.9 MB through the kernel` with
`0.0 fallbacks` [measured] cannot come from `write_kernel`
(`host.rs:1760-1770`), which is the only counter site that increments
both, and which fires once per run. 7.9 MB via `write_kernel` needs at
least 120 calls at 64 KiB, which would print as ~120 fallbacks, not 0.0.
The pair fits `VICTORY_SAFE_COPIES=1` exactly: there `read_into` goes
through `safe_copy_read` (`host.rs:1797-1808`, +3.9 MB) and `write_mapped`
through its kernel branch (`host.rs:1817-1840`, +4.0 MB), and
`write_kernel` never runs. The other candidate — one huge `write_kernel`
call per ~20 frames — is impossible because the copy-back writes only
4.2-5.5 MB per frame in total. So the run most likely had the reference
kernel path on, which would also make the 364-524 ms above entirely
mechanism B. Confirm from the run's environment before trusting either.

---

## 3. The compare scan — 189.4 ms, 730.8 MB compared

**Callsite.** `shadow.rs:207-227`; the loop is `shadow.rs:209-222`, the
comparison `shadow.rs:215`, the counter `shadow.rs:213-214` and the timer
`shadow.rs:223-227` (`C::BackWatchUs`).

**Shape.** Pieces are 64 KiB aligned to title memory
(`shadow.rs:211`), so 730.8 MB [measured] is 11,152 `bcmp` calls
[derived: 730.8e6 / 65536], each comparing 64 KiB of `after` against
`old`. Both slices belong to the readback staging the driver allocated
for this submission (`host.rs:658-664`), so the loop reads 1.4616 GB
[derived: 2 × 730.8 MB].

**Why it is 3.86 GB/s instead of 20+.** 730.8 MB / 189.4 ms is
3.86 GB/s nominal, 7.7 GB/s counting both streams [derived]. `memcmp`
on resident memory is several times that. The gap is page faults: both
buffers were committed by `CreateCommittedResource` inside this same
submission (`readback_buffer`, `host.rs:2283-2326`) and have never been
touched by the CPU, so the first read of each 4 KiB page takes a
transition fault. 1.4616 GB / 4096 = 356,835 faults [derived], which is
80.2% of the 444,797 the process took [measured]. The fault count and
the scan time are the same phenomenon.

**Nothing here is skipped between frames.** Every byte of every plan is
compared on every submission, before any merge, exactly as the doc
comment on `copy_back_range` promises (`shadow.rs:180-186`). The scan is
correct; it is expensive because it is the first reader of 1.46 GB of
brand-new pages.

---

## 4. `watches` — 199.29 ms, 5626.3 MB walked

**Callsite.** `watch::writes`, `watch.rs:117-192`; the syscall is
`GetWriteWatch(WRITE_WATCH_FLAG_RESET, ...)` at `watch.rs:143-152`; the
counter is `watch.rs:162-167`.

**Callers.** `Shadow::update_free`, `shadow.rs:377-388` (one per
distinct refreshed range per submission), `texture::Staging::refresh_now`,
`texture.rs:193`, and `Shadow::copy_back_range`'s final re-ask,
`shadow.rs:302` (one per plan).

**Shape.** 581 calls, 5626.3 MB of range, 199.29 ms [measured]. The
kernel keeps a dirty bit per 4 KiB page in a `MEM_WRITE_WATCH` allocation
and answers a range in one call, but it must visit every page in the
range to answer and to reset. 1,373,608 pages [derived] at 145 ns each
[derived]. The range is 99.65% unchanged (5606.7 / 5626.3 [measured]),
and none of those 5.6 GB is compared by this process — the kernel walks
it, we do not.

**Deduplication already exists.** `Asked` (`watch.rs:53-110`) answers a
range already asked this frame without a syscall, and `Journal` lets
overlapping host copies share one answer. The 5.6 GB is therefore the
union of *distinct* ranges, not repeats. `Asked::add` (`watch.rs:73-88`)
inserts into a `Vec` with a memmove and repopulates a `BTreeMap`
(`watch.rs:177-184`); that bookkeeping is outside `C::WatchUs` and lands
in the caller's time.

---

## 5. The bucket that is not in the log: 1.46 GB of readback staging per frame

**Callsite.** `host.rs:654-678` — for each merged shader-written range,
two allocations:

```rust
readback_arena.alloc(self, StagingKind::Readback, len),   // before
readback_arena.alloc(self, StagingKind::Readback, len),   // after
```

**What they cost.** `StagingArena::alloc` (`host.rs:429-465`) creates a
dedicated `READBACK` heap with `CreateCommittedResource` + `Map` for
every ask above `STAGING_CHUNK` (4 MiB), pushes it to `transient`, and
`reset()` (`host.rs:467-472`) drops it and truncates the chunk pool to
`MAX_POOLED_STAGING_CHUNKS = 4` (16 MiB). So a frame whose plans total
730.8 MB [measured] commits 2 × 730.8 MB = 1.4616 GB and frees it again
— at least 349 heaps [derived: 1.4616e9 / 4 MiB], each with one
`CreateCommittedResource` and one `Map`.

**Where it shows in the frame.** These allocations happen inside
`Host::execute` after `batch.flush` and before the `prepared` mark
(`host.rs:758`), so they are inside the reported `preparing` total but
inside none of `copies`, `textures`, or `runs`. The gap is
326-341 ms [derived: 915 - (536+38) to 1156 - (772+58)]. The only bulk
work in that window is this loop and the command-list recording that
follows it; the recording is one `CopyBufferRegion` per plan.

**This is the one cost the code and the counters agree on exactly.** It
is also the source of 80% of the page faults. It is the change below.

---

## 6. `textures` — 38-58 ms for 105-117 MB

**Callsite.** `texture.rs:203-205`, one `copy_mapped(…, title_dst =
false)` per staging refresh; timer `texture.rs:177-182` (`PREPARING[2]`),
with `watch`/`copy`/`detile`/`hash` sub-timers at `texture.rs:192-236`.
105-117 MB in 38-58 ms is 1.8-3.1 GB/s [derived], the only bucket in the
frame whose cost is proportional to its bytes. 108.7 MB hashed and 0.0
MB found changed [measured] is the physical-page-view path
(`texture.rs:213-239`), which cannot be write-watched.

---

## The hypothesis, checked against the code

> change detection is the structural cost: ~5.6 GB of shadow memory is
> compared per frame and 730 MB of copy-back is compared to find 3.9 MB
> of changes, and 444,797 page faults per frame means the process is
> re-faulting pages that Windows has already trimmed, which makes every
> scan slower than the last.

**Confirmed:** the 730 MB compare to find 3.9 MB is exact
(`C::BackChecked` 730.8 MB, `C::BackRead` 3.9 MB). Change detection —
199.29 ms of kernel dirty-bit walk plus 189.4 ms of byte compare — is
388.7 ms of a 2033-2266 ms frame, 17-19%.

**Partly wrong in mechanism:** the 5.6 GB is not compared. It is the
range the kernel walks in `GetWriteWatch`, at 28.2 GB/s. What this
process compares is 730.8 MB.

**Refuted — the page-fault reading.** The faults are not pages Windows
trimmed and we re-touch. `StagingArena::reset` truncates the readback
pool to 4 × 4 MiB (`host.rs:425-426`, `host.rs:467-472`), so 1.46 GB of
`READBACK` heaps is created and destroyed *every submission*. The faults
are first-touch faults on memory that did not exist last frame. There is
also no growth term anywhere in the code: windows are capped at eight
(`runs.rs:41`), the per-frame caches are cleared by `new_frame`
(`watch.rs:102-110`), the journal is monotonic but bounded by pages, and
staging is truncated on reset. "Every scan slower than the last" has no
mechanism here; per-frame fault counts would settle whether it drifts.

**And the proposed mechanism does not exist for this direction.**
`watch::guard` (`watch.rs:216-247`) protects *title view memory* and its
vectored handler (`watch.rs:331-356`) sees **CPU** writes to it. The
200 guard faults per frame [measured] are the title's own CPU writes,
already consumed by the upload side (`update_free`). GPU writes land in
the shadow buffer in default-heap VRAM, where `PAGE_GUARD` cannot see
them. A guard-fed dirty index on the copy-back path would silently
report GPU writes as unchanged — the exact "assume changed" weakening
the brief forbids. The compare has to read the bytes the GPU may have
written; the only lever is what those bytes cost.

---

## The change: keep the copy-back staging between submissions

`StagingArena` now keeps its large slots, matched by length, and keeps
its chunks past the first four up to a byte budget (`MAX_RESERVED_STAGING`).
Nothing about the compare changes: every byte of every plan is still
compared before any merge, and an unreadable range still lands in
`Skipped`/`SkippedBytes`. What changes is that the second frame's compare
reads pages the CPU already faulted in, and the frame stops committing
and releasing 1.46 GB.

It raises no memory peak: the 1.46 GB is live inside one submission
today. It does raise steady-state RSS by up to that amount, which is the
trade — peak for churn.

It is the right fix under either reading of the fault counter. If the
faults are first-touch on new heaps, pooling removes them. If they are
re-faults after trimming — because 1.46 GB of churn per frame blows the
working set — pooling removes the churn, and the same pages are touched
every frame instead.

**Prediction (falsifiable).** On the same scene:

- `page faults` 444,797 → ~88,000. The 356,835 readback faults go; the
  remaining ~88,000 (upload staging, copies, scratch) stay.
- `copy-back … 189.4 ms scanning` → 40-60 ms. 730.8 MB compared against
  warm pages at 12-18 GB/s.
- `copying back` 553-713 → 410-575 ms: the scan loses ~130 ms and the
  per-run read/merge/write does not move.
- `preparing` claims nothing: 915-1156 stays. Whatever commit charge the
  staging carried is not sized by the log, so this change does not
  predict it.
- Frame 2033-2266 → 1890-2130 ms, ~0.47-0.53 fps.
- Unchanged, and this is the check that the change is honest:
  `BackChecked` stays 730.8 MB, `BackRead` stays ~3.9 MB, `moves` and
  `watches` do not move.

If `page faults` does not fall by at least 250,000 per frame, the faults
were not the staging and this attribution is wrong.
