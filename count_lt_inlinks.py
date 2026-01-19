#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
count_lt_inlinks.py

Input:  enwiki-*-pagelinks.sql.gz
Output: lt_id_counts.tsv  (lt_id<TAB>inlinks)

Counts incoming links per linktarget ID using:
- streaming parse of pagelinks dump
- filter by pl_from_namespace (default 0)
- chunked external sort of kept lt_ids
- k-way merge + run-length counting

Memory bounded by --chunk-size (count of kept ids in RAM per chunk).
Disk usage: chunk files + counts output.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import tempfile
import time
from pathlib import Path
from typing import Iterator, List

from mw_sql_dump import iter_inserts, get_table_columns_from_dump


def iter_ints(path: Path) -> Iterator[int]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield int(line)

def write_sorted_chunk(nums: List[int], out_dir: Path, idx: int) -> Path:
    nums.sort()
    p = out_dir / f"chunk_{idx:06d}.txt"
    with p.open("w", encoding="utf-8") as f:
        for n in nums:
            f.write(f"{n}\n")
    return p

def merge_count(sorted_files: List[Path], out_tsv: Path) -> None:
    iters = [iter_ints(p) for p in sorted_files]
    merged = heapq.merge(*iters)

    with out_tsv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["lt_id", "inlinks"])

        prev = None
        cnt = 0
        wrote = 0

        for x in merged:
            if prev is None:
                prev = x
                cnt = 1
                continue

            if x == prev:
                cnt += 1
            else:
                w.writerow([prev, cnt])
                wrote += 1
                prev = x
                cnt = 1

        if prev is not None:
            w.writerow([prev, cnt])
            wrote += 1

    print(f"merge-count complete: wrote {wrote:,} rows to {out_tsv}", flush=True)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pagelinks", type=Path, required=True, help="Path to enwiki-*-pagelinks.sql.gz")
    ap.add_argument("--out", type=Path, default=Path("lt_id_counts.tsv"))
    ap.add_argument("--from-namespace", type=int, default=0)
    ap.add_argument("--chunk-size", type=int, default=5_000_000, help="Kept lt_ids per chunk before sorting to disk")
    ap.add_argument("--tmp-dir", type=Path, default=None, help="Directory for chunk files (default: auto temp dir)")
    ap.add_argument("--keep-chunks", action="store_true", help="Do not delete chunk files")
    ap.add_argument("--progress-every", type=int, default=5_000_000, help="Log progress every N rows seen")
    args = ap.parse_args()

    pl_gz = args.pagelinks
    if not pl_gz.exists():
        raise FileNotFoundError(pl_gz)

    # Discover pagelinks column indexes (schema-safe)
    pl_cols = get_table_columns_from_dump(pl_gz, "pagelinks")
    idx = {c: i for i, c in enumerate(pl_cols)}
    for c in ["pl_from_namespace", "pl_target_id"]:
        if c not in idx:
            raise RuntimeError(f"pagelinks missing {c}. columns={pl_cols}")

    i_from_ns = idx["pl_from_namespace"]
    i_target = idx["pl_target_id"]

    # Chunk dir
    owned_tmp = False
    if args.tmp_dir is None:
        tmp_root = Path(tempfile.mkdtemp(prefix="lt_inlinks_chunks_"))
        owned_tmp = True
    else:
        tmp_root = args.tmp_dir
        tmp_root.mkdir(parents=True, exist_ok=True)

    print(f"Chunk dir: {tmp_root}", flush=True)

    # Stream + chunk-sort
    chunk: List[int] = []
    chunk_files: List[Path] = []
    seen = 0
    kept = 0
    chunk_idx = 0
    t0 = time.time()
    last_log = t0

    for row in iter_inserts(pl_gz, "pagelinks"):
        seen += 1
        if int(row[i_from_ns]) != args.from_namespace:
            continue

        tid = int(row[i_target])
        kept += 1
        chunk.append(tid)

        if len(chunk) >= args.chunk_size:
            p = write_sorted_chunk(chunk, tmp_root, chunk_idx)
            chunk_files.append(p)
            chunk_idx += 1
            chunk.clear()

        if seen % args.progress_every == 0:
            now = time.time()
            rate = args.progress_every / max(1e-9, (now - last_log))
            elapsed = now - t0
            print(
                f"seen={seen:,} kept={kept:,} chunks={len(chunk_files)} "
                f"rate~{rate:,.0f} rows/s elapsed={elapsed/60:.1f}m",
                flush=True,
            )
            last_log = now

    if chunk:
        p = write_sorted_chunk(chunk, tmp_root, chunk_idx)
        chunk_files.append(p)
        chunk.clear()

    print(f"Streaming done. seen={seen:,} kept={kept:,} chunks={len(chunk_files)}", flush=True)

    # Merge-count
    merge_count(chunk_files, args.out)

    # Cleanup
    if not args.keep_chunks:
        for p in chunk_files:
            try:
                p.unlink()
            except OSError:
                pass
        if owned_tmp:
            try:
                tmp_root.rmdir()
            except OSError:
                pass

    print("Done.", flush=True)

if __name__ == "__main__":
    main()
