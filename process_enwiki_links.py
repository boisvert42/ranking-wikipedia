#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import sqlite3
import time
from typing import Dict, List, Set, Tuple

import requests

WDQS = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "enwiki-inlinks-script (local)",
}

def chunks(lst: List[str], n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def fetch_humans(qids: List[str]) -> Set[str]:
    if not qids:
        return set()

    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item WHERE {{
      VALUES ?item {{ {values} }}
      ?item wdt:P31 wd:Q5 .
    }}
    """
    r = requests.get(WDQS, params={"query": sparql}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()

    out: Set[str] = set()
    for b in data["results"]["bindings"]:
        uri = b["item"]["value"]  # .../entity/Qxxx
        out.add(uri.rsplit("/", 1)[-1])
    return out

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--with-person-flag", action="store_true")
    ap.add_argument("--wdqs-batch", type=int, default=500)
    ap.add_argument("--wdqs-sleep", type=float, default=0.2)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute(
        """
        SELECT
          p.page_id,
          REPLACE(p.page_title, '_', ' ') AS title,
          ic.inlinks AS inlinks,
          q.qid AS qid
        FROM inlink_counts ic
        JOIN linktarget lt ON lt.lt_id = ic.lt_id
        JOIN page p ON p.page_namespace = 0 AND p.page_title = lt.lt_title
        JOIN page_qid q ON q.page_id = p.page_id
        ORDER BY ic.inlinks DESC
        """
    ))

    # Build person set (optional)
    humans: Set[str] = set()
    if args.with_person_flag:
        qids = sorted({r["qid"] for r in rows if r["qid"]})
        print(f"WDQS: checking human(Q5) for {len(qids):,} qids...")
        for batch in chunks(qids, args.wdqs_batch):
            humans |= fetch_humans(batch)
            time.sleep(args.wdqs_sleep)
        print(f"WDQS: humans found: {len(humans):,}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "inlinks", "qid", "is_person"])
        for r in rows:
            qid = r["qid"]
            w.writerow([r["title"], int(r["inlinks"]), qid, (qid in humans) if args.with_person_flag else ""])

    conn.close()
    print(f"Wrote {len(rows):,} rows to {args.out}")

if __name__ == "__main__":
    main()
