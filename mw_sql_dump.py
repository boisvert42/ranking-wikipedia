# mw_sql_dump.py
import gzip
import re
from pathlib import Path
from typing import Any, Iterator, List, Optional

INSERT_RE = re.compile(r"^INSERT INTO `(?P<table>\w+)` VALUES\s*(?P<values>.+);$")

def iter_lines_gz(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n")

def split_tuples(values_blob: str) -> List[str]:
    """
    Split a MySQL VALUES blob into individual tuple strings, respecting quotes/escapes.
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
    Parse "(...)" into list of tokens.
    Keeps all non-NULL tokens as strings (callers cast specific columns).
    """
    assert tuple_str[0] == "(" and tuple_str[-1] == ")"
    s = tuple_str[1:-1]

    vals: List[Any] = []
    cur: List[str] = []
    in_str = False
    esc = False

    def flush(tok: str) -> None:
        tok = tok.strip()
        if tok == "NULL":
            vals.append(None)
        else:
            vals.append(tok)

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
                flush("".join(cur))
                cur = []
            else:
                cur.append(ch)

    flush("".join(cur))
    return vals

def iter_inserts(path: Path, table_name: str) -> Iterator[List[Any]]:
    for line in iter_lines_gz(path):
        m = INSERT_RE.match(line)
        if not m or m.group("table") != table_name:
            continue
        blob = m.group("values")
        for tup in split_tuples(blob):
            yield parse_tuple(tup)

CREATE_TABLE_RE = re.compile(r"^CREATE TABLE `(?P<table>\w+)` \(")
COLUMN_RE = re.compile(r"^\s*`(?P<col>[^`]+)`\s+")

def get_table_columns_from_dump(dump_gz: Path, table_name: str) -> List[str]:
    cols: List[str] = []
    in_table = False
    for line in iter_lines_gz(dump_gz):
        if not in_table:
            m = CREATE_TABLE_RE.match(line)
            if m and m.group("table") == table_name:
                in_table = True
            continue
        if line.startswith(")"):
            break
        mcol = COLUMN_RE.match(line)
        if mcol:
            cols.append(mcol.group("col"))
    if not cols:
        raise RuntimeError(f"Could not find CREATE TABLE for `{table_name}` in {dump_gz.name}")
    return cols
