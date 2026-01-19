#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import gzip
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, List, Tuple, Optional, Any, Dict, Set

INSERT_RE = re.compile(r"^INSERT INTO `(?P<table>\w+)` VALUES\s*(?P<values>.+);$")

def iter_lines_gz(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n")

def split_tuples(values_blob: str) -> List[str]:
    """
    Split a MySQL VALUES blob like:
      (1,'a'),(2,'b, c'),(3,NULL)
    into ["(1,'a')", "(2,'b, c')", "(3,NULL)"].

    This is a small state machine that respects quoted strings and escapes.
    """
    out: List[str] = []
    i = 0
    n = len(values_blob)
    depth = 0
    in_str = False
    esc = False
    start = None

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
    cur = []
    in_str = False
    esc = False

    def flush_token(tok: str) -> None:
        tok = tok.strip()
        if tok == "NULL":
            vals.append(None)
        else:
            # int (all relevant columns for our use are ints or strings)
            if tok and tok.lstrip("-").isdigit():
                vals.append(int(tok))
            else:
                vals.append(tok)

    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
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
        i += 1

    flush_token("".join(cur))
    return vals

def iter_inserts(path: Path, table_name: str) -> Iterator[List[Any]]:
    """
    Yield row arrays for INSERT statements into `table_name`.
    """
    for line in iter_lines_gz(path):
        m = INSERT_RE.match(line)
        if not m:
            continue
        if m.group("table") != table_name:
            continue
        blob = m.group("values")
        for tup in split_tuples(blob):
            yield parse_tuple(tup)

def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

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

def build_db(dump_dir: Path, db_path: Path, min_page_len: int, min_inlinks: int) -> None:
    page_gz = dump_dir / "enwiki-latest-page.sql.gz"
    props_gz = dump_dir / "enwiki-latest-page_props.sql.gz"
    lt_gz = dump_dir / "enwiki-latest-linktarget.sql.gz"
    pl_gz = dump_dir / "enwiki-latest-pagelinks.sql.gz"

    for p in (page_gz, props_gz, lt_gz, pl_gz):
        if not p.exists():
            raise FileNotFoundError(p)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA temp_store=MEMORY;")
    ensure_schema(conn)
    cur = conn.cursor()

    # ---- Pass 1: load page (keep all, but we will filter candidates soon) ----
    # page columns in dumps: page_id, page_namespace, page_title, page_restrictions,
    # page_is_redirect, page_is_new, page_random, page_touched, page_links_updated,
    # page_latest, page_len, page_content_model, page_lang
    #
    # We only need: id, namespace, title, is_redirect, len (indices 0,1,2,4,10)
    print("Loading page ...", flush=True)
    page_rows = 0
    candidate_page_ids: Set[int] = set()

    batch: List[Tuple[int,int,str,int,int]] = []
    for row in iter_inserts(page_gz, "page"):
        page_id = int(row[0])
        ns = int(row[1])
        title = str(row[2])
        is_redir = int(row[4])
        page_len = int(row[10])

        batch.append((page_id, ns, title, is_redir, page_len))
        if len(batch) >= 50_000:
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

    # ---- Pass 2: load only wikibase_item QIDs for candidate pages ----
    print("Loading page_props (wikibase_item only) ...", flush=True)
    # page_props columns: pp_page, pp_propname, pp_value, pp_sortkey
    qid_rows = 0
    qid_batch: List[Tuple[int,str]] = []
    for row in iter_inserts(props_gz, "page_props"):
        pp_page = int(row[0])
        if pp_page not in candidate_page_ids:
            continue
        prop = str(row[1])
        if prop != "wikibase_item":
            continue
        qid = str(row[2])
        qid_batch.append((pp_page, qid))
        if len(qid_batch) >= 50_000:
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

    # Get candidate titles that *also* have QIDs.
    print("Selecting candidate titles with QIDs ...", flush=True)
    cand_titles: Set[str] = set()
    for (title,) in conn.execute(
        """
        SELECT p.page_title
        FROM page p
        JOIN page_qid q ON q.page_id = p.page_id
        WHERE p.page_namespace = 0
          AND p.page_is_redirect = 0
          AND p.page_len >= ?
        """,
        (min_page_len,),
    ):
        cand_titles.add(title)

    print(f"Candidate titles with QIDs: {len(cand_titles):,}", flush=True)

    # ---- Pass 3: load linktarget rows ONLY for those candidate titles (ns0) ----
    print("Loading linktarget (filtered) ...", flush=True)
    # linktarget columns: lt_id, lt_namespace, lt_title
    lt_rows = 0
    candidate_lt_ids: Set[int] = set()

    lt_batch: List[Tuple[int,int,str]] = []
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
        if len(lt_batch) >= 50_000:
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

    # ---- Pass 4: stream pagelinks and count inlinks ONLY for candidate lt_ids ----
    #
    # Per MediaWiki schema, pagelinks references linktarget (pl_target_id -> lt_id). :contentReference[oaicite:2]{index=2}
    # pagelinks dump columns (as of mid-2024+): pl_from, pl_from_namespace, pl_target_id. :contentReference[oaicite:3]{index=3}
    print("Counting inlinks from pagelinks (filtered) ...", flush=True)

    counts: Dict[int, int] = {}
    seen = 0
    kept = 0

    for row in iter_inserts(pl_gz, "pagelinks"):
        pl_from = int(row[0])              # noqa: F841 (not used directly)
        pl_from_ns = int(row[1])
        pl_target_id = int(row[2])

        seen += 1
        if pl_from_ns != 0:
            continue
        if pl_target_id not in candidate_lt_ids:
            continue

        kept += 1
        counts[pl_target_id] = counts.get(pl_target_id, 0) + 1

        if kept % 5_000_000 == 0:
            print(f"  processed rows: {seen:,}  kept: {kept:,}  targets-counted: {len(counts):,}", flush=True)

    print(f"Finished pagelinks scan. Total rows seen: {seen:,}; kept: {kept:,}", flush=True)

    # Write counts meeting threshold
    print(f"Writing inlink_counts (>= {min_inlinks}) ...", flush=True)
    out_batch: List[Tuple[int,int]] = []
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
    ap.add_argument("--dump-dir", required=True, type=Path)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--min-page-len", type=int, default=2000)
    ap.add_argument("--min-inlinks", type=int, default=5)
    args = ap.parse_args()

    build_db(args.dump_dir, args.db, args.min_page_len, args.min_inlinks)

if __name__ == "__main__":
    main()
