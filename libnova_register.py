"""Build the accession register from Libnova: every object with a DC.IDENTIFIER.

Usage (from the ArchiveAutomation folder, venv active):
    $env:LIBNOVA_API_KEY = "<your key>"
    python libnova_register.py

Only searches are sent; nothing in Libnova is changed. Writes, in register\\:
    accession_register_from_libnova.csv   one row per accession, register columns
    libnova_register_report.txt           totals, duplicates, gaps, next free numbers,
                                          and rows that don't pass today's checks
Your register\\accession_register.csv is not touched: review the new file, then
copy its rows across (or rename it).
"""

import collections
import csv
import datetime as DT
import pathlib
import re
import sys

import aametadata as am
from aalibnova import Libnova, LibnovaError, get_api_key, iecode_from_index_key
from aavocab import Vocabulary, VocabularyError

REPO_DIR = pathlib.Path(__file__).resolve().parent
OUT_DIR = REPO_DIR / "register"
OUT_CSV = OUT_DIR / "accession_register_from_libnova.csv"
OUT_REPORT = OUT_DIR / "libnova_register_report.txt"

PAGE_SIZE = int(__import__("os").environ.get("LIBNOVA_PAGE_SIZE", 200))
ACCESSION_RE = re.compile(r"^(\d{3})_(\d{3})_(\d{4})$")
# Containers per Record Series (README_Physical_Archives_Ingest.md); used only
# if the search doesn't page.
KNOWN_CONTAINERS = list(range(11, 24))

# Register columns: workflow columns, Libnova references, then the IECodes in
# the order of accession_register.csv.example.
IECODE_COLUMNS = [
    ("title", "IECode: title"), ("creator", "IECode: creator"), ("DC.SOURCE", "IECode: SOURCE"),
    ("DC.TYPE", "IECode: DC.TYPE"), ("DC.LANGUAGE", "IECode: DC.LANGUAGE"),
    ("DC.RIGHTS_ACCESS", "IECode: DC.RIGHTS_ACCESS"), ("appraised", "IECode: appraised"),
    ("accession", "IECode: accession"), ("DC.DATE", "IECode: DC.DATE"),
    ("DC.DATE_ACCEPTED", "IECode: DC.DATE_ACCEPTED"), ("DC.DESCRIPTION", "IECode: DC.DESCRIPTION"),
    ("subject", "IECode: subject"), ("DC.COVERAGE_TEMPORAL", "IECode: DC.COVERAGE_TEMPORAL"),
    ("DC.DATE_COPYRIGHTED", "IECode: DC.DATE_COPYRIGHTED"),
    ("DC.RELATION_HASVERSION", "IECode: DC.RELATION_HASVERSION"),
    ("DC.ACCRUAL_METHOD", "IECode: DC.ACCRUAL_METHOD"),
    ("DC.ACCRUAL_PERIODICITY", "IECode: DC.ACCRUAL_PERIODICITY"),
    ("DC.ACCRUAL_POLICY", "IECode: DC.ACCRUAL_POLICY"),
    ("DC.PUBLISHER", "IECode: DC.PUBLISHER"), ("DC.COVERAGE_SPATIAL", "IECode: DC.COVERAGE_SPATIAL"),
    ("DC.FORMAT_MEDIUM", "IECode: DC.FORMAT_MEDIUM"), ("DC.RIGHTS", "IECode: DC.RIGHTS"),
]
HEADERS = ["accession_id", "s3_location", "libnova_id", "libnova_container_id"] + [
    hh for _, hh in IECODE_COLUMNS
]
# Computed by the workflow, so not carried into the register.
SKIPPED = {"DC.IDENTIFIER", "DC.FORMAT", "DC.FORMAT_EXTENT"}


# ---------------------------------------------------------------------------
# Collecting
#
# The search index (POST /file/elastic) caps results at 10,000 and 200 a page,
# and doesn't page. So the folders of each container are listed instead with
# the conditions search (GET /file), which pages with limit/offset and returns
# each object with its metadata; folders without DC.IDENTIFIER are skipped.
# ---------------------------------------------------------------------------

DELETED = []  # deleted folders that still carry a DC.IDENTIFIER


def folders_with_identifier(client, cid, log):
    """All folders of container 'cid' that have DC.IDENTIFIER, as hits."""
    hits, seen, offset, folders = [], set(), 0, 0
    while True:
        body = {"conditions": [{"container_id": cid}, {"type": "FOLDER"}],
                "limit": PAGE_SIZE, "offset": offset}
        page = client.call("GET", "/file", body).get("result") or []
        if not page:
            break
        new = [obj for obj in page if obj.get("id") not in seen]
        if not new:
            raise LibnovaError(
                f"Container {cid}: the next page repeated earlier results, so offset paging "
                "doesn't work here. Nothing was written; please send this output."
            )
        for obj in new:
            seen.add(obj.get("id"))
            meta = collections.defaultdict(list)
            for entry in obj.get("file_metadata") or []:
                meta[entry.get("iecode")].append(entry.get("value"))
            if meta.get("DC.IDENTIFIER"):
                hit = dict(obj)
                hit["metadata"] = dict(meta)
                if obj.get("deleted"):
                    # Deleted in Libnova (kept until purged): not an accession,
                    # but listed so stray identifiers can be cleaned up.
                    DELETED.append(hit)
                else:
                    hits.append(hit)
        folders += len(new)
        offset += len(page)
        print(f"\r  container {cid}: {folders} folders read, {len(hits)} with DC.IDENTIFIER", end="", flush=True)
    print()
    log(f"  container {cid}: {folders} folders, {len(hits)} with DC.IDENTIFIER")
    return hits


def collect_all(client, log):
    hits = []
    for cid in KNOWN_CONTAINERS:
        hits += folders_with_identifier(client, cid, log)
    return hits


# ---------------------------------------------------------------------------
# Turning hits into register rows
# ---------------------------------------------------------------------------

def rights_level(sentence, vocab):
    """Full DC.RIGHTS_ACCESS sentence -> its level, or None."""
    hit = vocab.rights_level(sentence)
    return hit[0] if hit else None


def to_row(hit, vocab, notes):
    meta = {iecode_from_index_key(kk): vv for kk, vv in (hit.get("metadata") or {}).items()}
    ident = " | ".join(meta.get("DC.IDENTIFIER") or [])
    row = {
        "accession_id": ident,
        "s3_location": f"{hit.get('container_id')}{hit.get('fullpath', '')}",
        "libnova_id": hit.get("id"),
        "libnova_container_id": hit.get("container_id"),
    }
    known = {iecode for iecode, _ in IECODE_COLUMNS}
    for iecode, header in IECODE_COLUMNS:
        values = [str(vv).strip() for vv in (meta.get(iecode) or []) if str(vv).strip()]
        if iecode == "DC.RIGHTS_ACCESS" and values:
            level = rights_level(values[0], vocab)
            if level:
                values = [level]
            else:
                notes.append(f"{ident}: DC.RIGHTS_ACCESS doesn't match a level, kept as is: {values[0]}")
        row[header] = " | ".join(values)
    for iecode in meta:
        if iecode not in known and iecode not in SKIPPED:
            notes.append(f"{ident}: field '{iecode}' is not a register column; left out")
    return row


def gaps_report(ids):
    """Per prefix NNN_MMM: count, highest, missing numbers, next free number."""
    groups = collections.defaultdict(set)
    for ident in ids:
        mm = ACCESSION_RE.match(ident)
        if mm:
            groups[f"{mm[1]}_{mm[2]}"].add(int(mm[3]))
    lines = []
    for prefix in sorted(groups):
        nums = groups[prefix]
        missing = [nn for nn in range(1, max(nums) + 1) if nn not in nums]
        text = f"  {prefix}: {len(nums)} accession(s), highest {prefix}_{max(nums):04d}, next free {prefix}_{max(nums) + 1:04d}"
        if missing:
            shown = ", ".join(f"{nn:04d}" for nn in missing[:30])
            more = f" ... ({len(missing)} in all)" if len(missing) > 30 else ""
            text += f"\n      not found: {shown}{more}"
        lines.append(text)
    return lines


def check_rows(csv_path, ids, vocab):
    """Which rows would not pass today's start-of-run checks (for information)."""
    out = []
    for ident in ids:
        try:
            am.build_record(csv_path, ident, vocab)
        except am.MetadataError as ee:
            out.append(f"  {ident}: " + "; ".join(ee.problems))
    return out


# ---------------------------------------------------------------------------

def main():
    report = []

    def log(text):
        print(text)
        report.append(text)

    try:
        vocab = Vocabulary()
        client = Libnova(get_api_key())
        log(f"Collecting DC.IDENTIFIER from {client.base_url} ...")
        hits = collect_all(client, log)
    except (LibnovaError, VocabularyError) as ee:
        print(f"\n{ee}")
        return 1

    notes, rows, other = [], [], []
    for hit in hits:
        row = to_row(hit, vocab, notes)
        if ACCESSION_RE.match(row["accession_id"]):
            rows.append(row)
        else:
            other.append(f"  '{row['accession_id']}' on {hit.get('type')} {row['s3_location']} (id {row['libnova_id']})")
    rows.sort(key=lambda rr: (rr["accession_id"], str(rr["libnova_id"])))

    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as ff:
        ww = csv.DictWriter(ff, fieldnames=HEADERS)
        ww.writeheader()
        ww.writerows(rows)

    counts = collections.Counter(rr["accession_id"] for rr in rows)
    dupes = sorted(ident for ident, nn in counts.items() if nn > 1)
    unique_ids = sorted(ident for ident, nn in counts.items() if nn == 1)

    log("")
    log(f"Objects with DC.IDENTIFIER: {len(hits)}")
    log(f"Accession numbers (NNN_NNN_NNNN): {len(counts)} ({len(rows)} rows)")
    log(f"Written: {OUT_CSV}")
    sections = [
        ("Accession numbers on more than one object (the register needs one row each)",
         [f"  {ii}:\n" + "\n".join(f"      {rr['libnova_id']}  {rr['s3_location']}" for rr in rows if rr['accession_id'] == ii) for ii in dupes]),
        ("Deleted objects that still carry a DC.IDENTIFIER (skipped)",
         [f"  {' | '.join(hh['metadata'].get('DC.IDENTIFIER') or [])}: {hh.get('id')}  {hh.get('container_id')}{hh.get('fullpath', '')}" for hh in DELETED]),
        ("DC.IDENTIFIER values that are not accession numbers (left out)", other),
        ("Per series and collection", gaps_report(counts)),
        ("Notes", [f"  {nn}" for nn in notes]),
        ("Rows that would not pass today's checks (only matters if the accession is processed again)",
         check_rows(OUT_CSV, unique_ids, vocab)),
    ]
    for title, lines in sections:
        report.append("")
        report.append(f"{title}: {len(lines) if title != 'Per series and collection' else ''}".rstrip(": "))
        report.extend(lines or ["  none"])

    report.insert(0, f"Libnova register report, {DT.datetime.now():%Y-%m-%d %H:%M}")
    OUT_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Report: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
