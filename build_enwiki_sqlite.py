#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_enwiki_sqlite.py

Downloads minimal English Wikipedia SQL dumps (page, page_props, linktarget, pagelinks)
and builds a compact SQLite database containing:

- page          (filtered to ns0, non-redirect, and stores basic metadata)
- page_qid      (wikibase_item QID for candidate pages)
- linktarget    (only target rows needed for candidate titles)
- inlink_counts (inlink counts computed by streaming pagelinks; does NOT store all edges)

This avoids Quarry timeouts and avoids storing the full pagelinks table in SQLite.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import sqlite3
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple


# ----------------------------
# Download helpers
# ----------------------------

def _sha1_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def _download(url: str, dest: Path, *, overwrite: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        print(f"Already exists: {dest.name}")
        return

    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    print(f"Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "enwiki-links-builder/1.0"})
    with urllib.request.urlopen(req) as resp, tmp.open("wb") as out:
        total = resp.headers.get("Content-Length")
        total_i = int(total) if total and total.isdigit() else None
        downloaded = 0
        last_t = time.time()

        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_t >= 1.0:
                if total_i:
                    pct = (downloaded / total_i) * 100.0
                    print(f"  {dest.name}: {downloaded/1e9:.2f} GB / {total_i/1e9:.2f} GB ({pct:.1f}%)", end="\r")
                else:
                    print(f"  {dest.name}: {downloaded/1e9:.2f} GB", end="\r")
                last_t = now

    print()
    tmp.rename(dest)
    print(f"Saved: {dest}")

def _download_sha1(url: str, dest_sha1: Path) -> Optional[str]:
    """
    Download a .sha1 file. Returns the expected sha1 hex if parseable, else None.
    WMF sha1 files typically contain: "<sha1>  <filename>"
    """
    try:
        _download(url, dest_sha1, overwrite=True)
    except Exception as e:
        print(f"Warning: failed to download sha1 file {url}: {e}")
        return None

    try:
        txt = dest_sha1.read_text(encoding="utf-8", errors="replace").strip()
        if not txt:
            return None
        # grab first token that looks like sha1
        token = txt.split()[0].strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}", token):
            return token.lower()
    except Exception:
        return None
    return None

def download_dumps(out_dir: Path, snapshot: str, overwrite: bool) -> Dict[str, Path]:
    base = f"https://dumps.wikimedia.org/enwiki/{snapshot}"
    files = [
        "enwiki-{snap}-page.sql.gz",
        "enwiki-{snap}-page_props.sql.gz",
        "enwiki-{snap}-linktarget.sql.gz",
        "enwiki-{snap}-pagelinks.sql.gz",
    ]

    paths: Dict[str, Path] = {}
    for tmpl in files:
        fn = tmpl.format(snap=snapshot)
        url = f"{base}/{fn}"
        dest = out_dir / fn
        _download(url, dest, overwrite=overwrite)

        # Best-effort integrity check (sha1 files exist on dumps site)
        sha1_url = f"{url}.sha1"
        sha1_dest = out_dir / (fn + ".sha1")
        expected = _download_sha1(sha1_url, sha1_dest)
        if expected:
            actual = _sha1_of_file(dest)
            if actual != expected:
                raise RuntimeError(
                    f"SHA1 mismatch for {fn}\nexpected: {expected}\nactual:   {actual}"
                )

        paths[fn] = dest

    return paths


# ----------------------------
# SQL dump parsing helpers
# ----------------------------

INSERT_RE = re.compile(r"^INSERT INTO `(?P<table>\w+)` VALUES\s*(?P<values>.+);$")

CREATE_TABLE_RE = re.compile(r"^CREATE TABLE `(?P<table>\w+)` \(")
COLUMN_RE = re.compile(r"^\s*`(?P<col>[^`]+)`\s+")

def get_table_columns_from_dump(dump_gz: Path, table_name: str) -> List[str]:
    """
    Reads the CREATE TABLE for `table_name` from a Wikimedia .sql.gz dump
    and returns the column names in order.
    """
    cols: List[str] = []
    in_table = False

    for line in iter_lines_gz(dump_gz):
        if not in_table:
            m = CREATE_TABLE_RE.match(line)
            if m and m.group("table") == table_name:
                in_table = True
            continue

        # Stop when table definition ends
        if line.startswith(")"):
            break

        mcol = COLUMN_RE.match(line)
        if mcol:
            cols.append(mcol.group("col"))

    if not cols:
        raise RuntimeError(f"Could not find CREATE TABLE columns for `{table_name}` in {dump_gz.name}")
    return cols

def iter_lines_gz(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n")

def split_tuples(values_blob: str) -> List[str]:
    """
    Split a MySQL VALUES blob like:
      (1,'a'),(2,'b, c'),(3,NULL)
    into ["(1,'a')", "(2,'b, c')", "(3,NULL)"].
    Respects quoted strings and backslash escapes.
    """
    out: List[str] = []
    i = 0
    n = len(values_blob)
    depth = 0
    in_str = False
    esc = False
    start: Optional[int] = None

    while i < n:
        ch = values_blob[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "'":
                in_str = False
        else:
            if ch == "'":
                in_str = True
            elif ch == "(":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and start is not None:
                    out.append(values_blob[start:i+1])
                    start = None
        i += 1

    return out

def parse_tuple(tuple_str: str) -> List[Any]:
    """
    Parse a single tuple "(...)" into Python values, handling:
    - NULL
    - ints
    - SQL strings with backslash escapes
    """
    assert tuple_str[0] == "(" and tuple_str[-1] == ")"
    s = tuple_str[1:-1]

    vals: List[Any] = []
    cur: List[str] = []
    in_str = False
    esc = False

    def flush_token(tok: str) -> None:
        tok = tok.strip()
        if tok == "NULL":
            vals.append(None)
        else:
            if tok == "NULL":
                vals.append(None)
            else:
                vals.append(tok)   # always string

    for ch in s:
        if in_str:
            if esc:
                cur.append(ch)
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "'":
                in_str = False
            else:
                cur.append(ch)
        else:
            if ch == "'":
                in_str = True
            elif ch == ",":
                flush_token("".join(cur))
                cur = []
            else:
                cur.append(ch)

    flush_token("".join(cur))
    return vals

def iter_inserts(path: Path, table_name: str) -> Iterator[List[Any]]:
    for line in iter_lines_gz(path):
        m = INSERT_RE.match(line)
        if not m:
            continue
        if m.group("table") != table_name:
            continue
        blob = m.group("values")
        for tup in split_tuples(blob):
            yield parse_tuple(tup)


# ----------------------------
# SQLite builder
# ----------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=MEMORY;

        DROP TABLE IF EXISTS page;
        DROP TABLE IF EXISTS page_qid;
        DROP TABLE IF EXISTS linktarget;
        DROP TABLE IF EXISTS inlink_counts;

        CREATE TABLE page (
            page_id INTEGER PRIMARY KEY,
            page_namespace INTEGER NOT NULL,
            page_title TEXT NOT NULL,
            page_is_redirect INTEGER NOT NULL,
            page_len INTEGER NOT NULL
        );

        CREATE TABLE page_qid (
            page_id INTEGER PRIMARY KEY,
            qid TEXT NOT NULL
        );

        CREATE TABLE linktarget (
            lt_id INTEGER PRIMARY KEY,
            lt_namespace INTEGER NOT NULL,
            lt_title TEXT NOT NULL
        );

        CREATE TABLE inlink_counts (
            lt_id INTEGER PRIMARY KEY,
            inlinks INTEGER NOT NULL
        );

        CREATE INDEX idx_page_ns_title ON page(page_namespace, page_title);
        CREATE INDEX idx_lt_ns_title ON linktarget(lt_namespace, lt_title);
        """
    )
    conn.commit()

def build_db(
    *,
    dump_dir: Path,
    snapshot: str,
    db_path: Path,
    min_page_len: int,
    min_inlinks: int,
) -> None:
    page_gz = dump_dir / f"enwiki-{snapshot}-page.sql.gz"
    props_gz = dump_dir / f"enwiki-{snapshot}-page_props.sql.gz"
    lt_gz = dump_dir / f"enwiki-{snapshot}-linktarget.sql.gz"
    pl_gz = dump_dir / f"enwiki-{snapshot}-pagelinks.sql.gz"

    for p in (page_gz, props_gz, lt_gz, pl_gz):
        if not p.exists():
            raise FileNotFoundError(p)

    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    cur = conn.cursor()

    # Discover actual column order from CREATE TABLE to avoid hard-coded indexes
    page_cols = get_table_columns_from_dump(page_gz, "page")
    page_idx = {name: i for i, name in enumerate(page_cols)}

    needed = ["page_id", "page_namespace", "page_title", "page_is_redirect", "page_len"]
    missing = [c for c in needed if c not in page_idx]
    if missing:
        raise RuntimeError(f"`page` table missing expected columns: {missing}. Found: {page_cols}")

    i_id = page_idx["page_id"]
    i_ns = page_idx["page_namespace"]
    i_title = page_idx["page_title"]
    i_redir = page_idx["page_is_redirect"]
    i_len = page_idx["page_len"]

    # ---- Pass 1: load page, collect candidate page_ids (ns0, non-redirect, len>=min) ----
    print("Loading page ...", flush=True)
    page_rows = 0
    candidate_page_ids: Set[int] = set()

    # enwiki page columns include page_len at index 10 in current dumps
    batch: List[Tuple[int, int, str, int, int]] = []
    for row in iter_inserts(page_gz, "page"):
        page_id = int(row[i_id])
        ns = int(row[i_ns])
        title = str(row[i_title])
        is_redir = int(row[i_redir])
        page_len = int(row[i_len])

        # Decide if this is a page we want to store at all
        keep_page = (ns == 0 and is_redir == 0)

        if keep_page:
            batch.append((page_id, ns, title, is_redir, page_len))

        # Candidate set is an even narrower subset (length threshold)
        if keep_page and page_len >= min_page_len:
            candidate_page_ids.add(page_id)

        if len(batch) >= 250_000:
            cur.executemany(
                "INSERT INTO page(page_id,page_namespace,page_title,page_is_redirect,page_len) VALUES (?,?,?,?,?)",
                batch,
            )
            conn.commit()
            page_rows += len(batch)
            batch.clear()
            print(f"  page rows inserted: {page_rows:,}", flush=True)

        if ns == 0 and is_redir == 0 and page_len >= min_page_len:
            candidate_page_ids.add(page_id)

    if batch:
        cur.executemany(
            "INSERT INTO page(page_id,page_namespace,page_title,page_is_redirect,page_len) VALUES (?,?,?,?,?)",
            batch,
        )
        conn.commit()
        page_rows += len(batch)

    print(f"Loaded page: {page_rows:,} rows", flush=True)
    print(f"Candidate pages (ns0, non-redirect, len>={min_page_len}): {len(candidate_page_ids):,}", flush=True)

    # ---- Pass 2: load wikibase_item QIDs for candidate pages ----
    print("Loading page_props (wikibase_item only for candidates) ...", flush=True)
    qid_rows = 0
    qid_batch: List[Tuple[int, str]] = []

    for row in iter_inserts(props_gz, "page_props"):
        pp_page = int(row[0])
        if pp_page not in candidate_page_ids:
            continue
        if str(row[1]) != "wikibase_item":
            continue
        qid = str(row[2])
        qid_batch.append((pp_page, qid))
        if len(qid_batch) >= 250_000:
            cur.executemany("INSERT OR REPLACE INTO page_qid(page_id,qid) VALUES (?,?)", qid_batch)
            conn.commit()
            qid_rows += len(qid_batch)
            qid_batch.clear()
            print(f"  qid rows inserted: {qid_rows:,}", flush=True)

    if qid_batch:
        cur.executemany("INSERT OR REPLACE INTO page_qid(page_id,qid) VALUES (?,?)", qid_batch)
        conn.commit()
        qid_rows += len(qid_batch)

    print(f"Loaded page_qid: {qid_rows:,} rows", flush=True)

    # Candidate titles with QIDs (keeps linktarget small)
    print("Selecting candidate titles with QIDs ...", flush=True)
    cand_titles: Set[str] = set(
        t for (t,) in conn.execute(
            """
            SELECT p.page_title
            FROM page p
            JOIN page_qid q ON q.page_id = p.page_id
            WHERE p.page_namespace = 0
              AND p.page_is_redirect = 0
              AND p.page_len >= ?
            """,
            (min_page_len,),
        )
    )
    print(f"Candidate titles with QIDs: {len(cand_titles):,}", flush=True)

    # ---- Pass 3: load linktarget rows only for those candidate titles (ns0) ----
    print("Loading linktarget (filtered) ...", flush=True)
    lt_rows = 0
    candidate_lt_ids: Set[int] = set()
    lt_batch: List[Tuple[int, int, str]] = []

    for row in iter_inserts(lt_gz, "linktarget"):
        lt_id = int(row[0])
        lt_ns = int(row[1])
        lt_title = str(row[2])

        if lt_ns != 0:
            continue
        if lt_title not in cand_titles:
            continue

        candidate_lt_ids.add(lt_id)
        lt_batch.append((lt_id, lt_ns, lt_title))
        if len(lt_batch) >= 250_000:
            cur.executemany("INSERT INTO linktarget(lt_id,lt_namespace,lt_title) VALUES (?,?,?)", lt_batch)
            conn.commit()
            lt_rows += len(lt_batch)
            lt_batch.clear()
            print(f"  linktarget rows inserted: {lt_rows:,}", flush=True)

    if lt_batch:
        cur.executemany("INSERT INTO linktarget(lt_id,lt_namespace,lt_title) VALUES (?,?,?)", lt_batch)
        conn.commit()
        lt_rows += len(lt_batch)

    print(f"Loaded linktarget: {lt_rows:,} rows", flush=True)
    print(f"Candidate lt_ids: {len(candidate_lt_ids):,}", flush=True)

    # ---- Pass 4: stream pagelinks and count inlinks for candidate lt_ids only ----
    #
    # pagelinks references linktarget via pl_target_id -> lt_id in modern dumps.
    print("Counting inlinks by streaming pagelinks (filtered) ...", flush=True)

    counts: Dict[int, int] = {}
    seen = 0
    kept = 0
    last_log = time.time()

    pl_cols = get_table_columns_from_dump(pl_gz, "pagelinks")
    pl_idx = {name: i for i, name in enumerate(pl_cols)}
    needed_pl = ["pl_from_namespace", "pl_target_id"]
    missing_pl = [c for c in needed_pl if c not in pl_idx]
    if missing_pl:
        raise RuntimeError(f"`pagelinks` missing expected columns: {missing_pl}. Found: {pl_cols}")

    i_pl_from_ns = pl_idx["pl_from_namespace"]
    i_pl_target_id = pl_idx["pl_target_id"]

    for row in iter_inserts(pl_gz, "pagelinks"):
        # Expected columns: pl_from, pl_from_namespace, pl_target_id
        pl_from_ns = int(row[i_pl_from_ns])
        pl_target_id = int(row[i_pl_target_id])

        seen += 1
        if pl_from_ns != 0:
            continue
        if pl_target_id not in candidate_lt_ids:
            continue

        kept += 1
        counts[pl_target_id] = counts.get(pl_target_id, 0) + 1

        now = time.time()
        if now - last_log >= 10.0:
            print(
                f"  rows seen: {seen:,}  kept: {kept:,}  targets-counted: {len(counts):,}",
                flush=True,
            )
            last_log = now

    print(f"Finished pagelinks scan. rows seen: {seen:,}; kept: {kept:,}", flush=True)

    # Write counts >= min_inlinks
    print(f"Writing inlink_counts (>= {min_inlinks}) ...", flush=True)
    out_batch: List[Tuple[int, int]] = []
    written = 0
    for lt_id, c in counts.items():
        if c < min_inlinks:
            continue
        out_batch.append((lt_id, c))
        if len(out_batch) >= 50_000:
            cur.executemany("INSERT OR REPLACE INTO inlink_counts(lt_id,inlinks) VALUES (?,?)", out_batch)
            conn.commit()
            written += len(out_batch)
            out_batch.clear()
            print(f"  inlink_counts rows written: {written:,}", flush=True)

    if out_batch:
        cur.executemany("INSERT OR REPLACE INTO inlink_counts(lt_id,inlinks) VALUES (?,?)", out_batch)
        conn.commit()
        written += len(out_batch)

    print(f"Done. inlink_counts rows written: {written:,}", flush=True)

    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path("./enwiki_dumps"))
    ap.add_argument("--db", type=Path, default=Path("./enwiki_links.sqlite"))
    ap.add_argument("--snapshot", default="latest", help="Usually 'latest' (monthly).")
    ap.add_argument("--min-page-len", type=int, default=5000)
    ap.add_argument("--min-inlinks", type=int, default=5)
    ap.add_argument("--overwrite", action="store_true", help="Re-download even if files exist.")
    ap.add_argument("--skip-download", action="store_true", help="Assume dumps already exist in --out-dir.")
    args = ap.parse_args()

    if not args.skip_download:
        download_dumps(args.out_dir, args.snapshot, overwrite=args.overwrite)

    build_db(
        dump_dir=args.out_dir,
        snapshot=args.snapshot,
        db_path=args.db,
        min_page_len=args.min_page_len,
        min_inlinks=args.min_inlinks,
    )


if __name__ == "__main__":
    main()
