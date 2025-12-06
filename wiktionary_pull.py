"""
Wiktionary Stats Builder
========================

This script downloads *two* Wiktionary SQL dumps:

    1. page.sql.gz        → provides page_len (page length)
    2. pagelinks.sql.gz   → provides inlink counts

It then produces a JSON file mapping:

    title → { page_length, number_inlinks }

This replaces the parts of your Perl script concerned with:
- article size measurement
- backlink / inlink counting

Dependencies:
    pip install requests orjson tqdm
"""

import os
import re
import gzip
import requests
from tqdm import tqdm
import orjson
import csv

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

BASE = "https://dumps.wikimedia.org/enwiktionary/latest/"

PAGE_SQL = "enwiktionary-latest-page.sql.gz"
PL_SQL   = "enwiktionary-latest-pagelinks.sql.gz"

PAGE_PATH = os.path.join(DATA_DIR, PAGE_SQL)
PL_PATH   = os.path.join(DATA_DIR, PL_SQL)

OUTPUT = os.path.join(DATA_DIR, "wiktionary_stats.json")

# ---------------------------------------------------------
# Download helper
# ---------------------------------------------------------

def download(url, dest):
    """Download a file with progress bar, skipping if present."""
    if os.path.exists(dest):
        print(f"✔ Already exists: {dest}")
        return

    print(f"⬇ Downloading {url}")

    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()

    total = int(r.headers.get("content-length", 0))
    block = 1024

    with open(dest, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, desc=os.path.basename(dest)
    ) as bar:
        for chunk in r.iter_content(block):
            f.write(chunk)
            bar.update(len(chunk))

    print(f"✔ Download complete: {dest}")

# ---------------------------------------------------------
# STEP 1 — DOWNLOAD REQUIRED FILES
# ---------------------------------------------------------

def ensure_files():
    download(BASE + PAGE_SQL, PAGE_PATH)
    download(BASE + PL_SQL,   PL_PATH)

# ---------------------------------------------------------
# STEP 2 — LOAD PAGE LENGTHS
# ---------------------------------------------------------


def parse_insert_line(line):
    """
    Given a line like:
      INSERT INTO `page` VALUES (...),(...),(...)
    return a list of tuple-strings, each without surrounding parentheses.
    """
    # Extract content between VALUES (...)
    content = line.split("VALUES", 1)[1].strip()
    if content.endswith(";"):
        content = content[:-1]

    # Remove the first '(' and last ')'
    assert content[0] == '(' and content[-1] == ')'
    content = content[1:-1]

    # Now split on '),(' safely — this boundary is not allowed inside strings.
    return content.split("),(")

def parse_tuple(tuple_str):
    """
    Parse a single tuple using csv.reader with correct delimiters
    """
    reader = csv.reader(
        [tuple_str],
        delimiter=',',
        quotechar="'",
        escapechar='\\'
    )
    return next(reader)

def load_page_lengths(path):
    page_lengths = {}

    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
        for line in tqdm(f, desc="Parsing page.sql"):
            if not line.startswith("INSERT"):
                continue

            tuple_strings = parse_insert_line(line)

            for tup in tuple_strings:
                fields = parse_tuple(tup)

                page_title = fields[2]              # varbinary(255)
                page_len = int(fields[9])          # correct index

                # Convert underscores and remove diacritics if needed
                title = page_title.replace("_", " ").lower()

                page_lengths[title] = page_len

    return page_lengths

# ---------------------------------------------------------
# STEP 3 — COUNT INLINKS
# ---------------------------------------------------------

def load_inlinks(path):
    """
    pagelinks.sql.gz contains inserts like:

      INSERT INTO `pagelinks` VALUES (from_id, namespace, 'title', ...)

    We count titles where namespace = 0.
    """
    print("\n=== Counting inlinks ===")

    inlinks = {}

    for line in tqdm(
        gzip.open(path, "rt", encoding="utf-8", errors="ignore"),
        desc="Parsing pagelinks.sql.gz"
    ):
        if not line.startswith("INSERT"):
            continue

        tuples = re.findall(r"\((.*?)\)", line)
        for tup in tuples:
            fields = tup.split(",")

            namespace = fields[1]
            if namespace != "0":
                continue

            title_sql = fields[2].strip("'")
            title = title_sql.replace("_", " ").lower()

            inlinks[title] = inlinks.get(title, 0) + 1

    return inlinks

# ---------------------------------------------------------
# STEP 4 — MERGE + SAVE
# ---------------------------------------------------------

def merge_and_save(page_length, inlinks):
    print("\n=== Saving wiktionary_stats.json ===")

    out = {}

    all_titles = set(page_length.keys()) | set(inlinks.keys())

    for title in all_titles:
        out[title] = {
            "page_length": page_length.get(title, 0),
            "number_inlinks": inlinks.get(title, 0),
        }

    with open(OUTPUT, "wb") as f:
        f.write(orjson.dumps(out))

    print(f"✔ Wrote {len(out)} entries")
    print(f"✔ Output: {OUTPUT}")

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":
    ensure_files()

    page_length = load_page_lengths(PAGE_PATH)
    inlinks     = load_inlinks(PL_PATH)

    merge_and_save(page_length, inlinks)

    print("\n=== DONE ===")
