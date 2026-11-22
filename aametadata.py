"""Libnova metadata for an accession: read from the accession register, checked
against the shared vocabulary, completed from DROID's results, and written into
the bag as bag-info.txt, bag-info.xml and libnova_metadata.json.

The field names are Libnova IECodes, as used by the physical ingest scripts.
"""

import csv
import datetime as DT
import hashlib
import json
import logging
import pathlib
import re
import xml.etree.ElementTree as ET

import bagit

from aavocab import FALLBACK_MEDIA_TYPE

REPO_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_REGISTER = REPO_DIR / "register" / "accession_register.csv"

# ---------------------------------------------------------------------------
# The field list (see the phase 1 design doc)
# ---------------------------------------------------------------------------

REQUIRED = [
    "title", "creator", "DC.SOURCE", "DC.TYPE", "DC.LANGUAGE",
    "DC.RIGHTS_ACCESS", "appraised", "accession", "DC.DATE", "DC.DATE_ACCEPTED",
]
RECOMMENDED = ["DC.DESCRIPTION", "subject", "DC.COVERAGE_TEMPORAL"]
OPTIONAL = [
    "DC.DATE_COPYRIGHTED", "DC.RELATION_HASVERSION",
    "DC.ACCRUAL_METHOD", "DC.ACCRUAL_PERIODICITY", "DC.ACCRUAL_POLICY",
]
DEFAULTED = ["DC.PUBLISHER", "DC.COVERAGE_SPATIAL", "DC.FORMAT_MEDIUM", "DC.RIGHTS"]
COMPUTED = ["DC.IDENTIFIER", "DC.FORMAT", "DC.FORMAT_EXTENT"]

REGISTER_FIELDS = REQUIRED + RECOMMENDED + OPTIONAL + DEFAULTED
ALL_FIELDS = REGISTER_FIELDS + COMPUTED

CONTROLLED = ["DC.TYPE", "DC.LANGUAGE", "appraised", "accession"]
DATE_FIELDS = ["DC.DATE", "DC.DATE_ACCEPTED", "DC.DATE_COPYRIGHTED"]

# Fields that take one value only; every other field may hold several,
# separated by '|' as in the physical inventory CSVs.
SINGLE_VALUE = [
    "title", "DC.SOURCE", "DC.RIGHTS_ACCESS", "appraised", "accession",
    "DC.COVERAGE_TEMPORAL", "DC.IDENTIFIER", "DC.FORMAT_EXTENT",
] + DATE_FIELDS

# Order of the fields in bag-info.xml and libnova_metadata.json: the order of
# a Libnova export, then the fields the export did not show.
OUTPUT_ORDER = [
    "DC.IDENTIFIER", "DC.SOURCE", "DC.TYPE", "DC.COVERAGE_SPATIAL",
    "DC.DESCRIPTION", "DC.COVERAGE_TEMPORAL", "DC.FORMAT", "DC.FORMAT_MEDIUM",
    "DC.DATE_ACCEPTED", "subject", "creator", "title", "DC.RIGHTS",
    "DC.RIGHTS_ACCESS", "DC.LANGUAGE", "DC.PUBLISHER", "DC.DATE",
    "DC.DATE_COPYRIGHTED", "appraised", "accession", "DC.FORMAT_EXTENT",
    "DC.RELATION_HASVERSION", "DC.ACCRUAL_METHOD", "DC.ACCRUAL_PERIODICITY",
    "DC.ACCRUAL_POLICY",
]

# Register column header -> IECode, where the physical CSV uses another name.
HEADER_ALIASES = {"SOURCE": "DC.SOURCE"}

WORKFLOW_COLUMNS = ["accession_id", "s3_location"]


class MetadataError(Exception):
    """Raised with every problem found, so they can be fixed in one go."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def clean(value):
    """One line, single spaces."""
    return " ".join((value or "").split())


def header_to_iecode(header):
    """'IECode: DC.TYPE', 'IECode:DC.TYPE' or 'IECode: SOURCE' -> IECode."""
    hh = header.strip()
    if not hh.lower().startswith("iecode:"):
        return None
    code = hh.split(":", 1)[1].strip()
    return HEADER_ALIASES.get(code, code)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def parse_date(value):
    """Return (YYYY-MM-DD or None for Undated, error or None).

    Accepted, as in the physical ingest: 2007 -> 2007-01-01, 2008-08 ->
    2008-08-01, 2007-2009 -> 2007-01-01, 20080805 and 2008-08-05 as given;
    an open range 2022- -> 2022-01-01.
    Slash dates are refused: 5/6/2010 could be 5 June or 6 May.
    """

    vv = clean(value)
    if vv.lower() == "undated":
        return None, None
    if "/" in vv:
        return None, f"'{vv}' is ambiguous; use YYYY-MM-DD"

    mm = re.fullmatch(r"(\d{4})-?", vv)  # a year, or an open range "2022-"
    if mm:
        return f"{mm[1]}-01-01", None
    mm = re.fullmatch(r"(\d{4})-(\d{4})", vv)
    if mm:
        if mm[1] > mm[2]:
            return None, f"'{vv}': the range ends before it starts"
        return f"{mm[1]}-01-01", None
    mm = re.fullmatch(r"(\d{4})-(\d{2})", vv)
    if mm:
        candidate = f"{mm[1]}-{mm[2]}-01"
    else:
        mm = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", vv)
        if not mm:
            return None, f"'{vv}' is not a date; use YYYY-MM-DD, YYYY-MM or YYYY"
        candidate = f"{mm[1]}-{mm[2]}-{mm[3]}"
    try:
        DT.date.fromisoformat(candidate)
    except ValueError:
        return None, f"'{vv}' is not a real date"
    return candidate, None


TEMPORAL_FORMS = "2020, 2020-10, 2008-2013 or 2022- (open)"


def check_temporal(value):
    """DC.COVERAGE_TEMPORAL: a year (2020), a month (2020-10), a range of
    years (2008-2013) or an open range (2022-). Kept as typed."""
    vv = clean(value)
    mm = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", vv)
    if mm:
        if mm[2] and not 1 <= int(mm[2]) <= 12:
            return f"'{vv}': {mm[2]} is not a month"
        return None
    mm = re.fullmatch(r"(\d{4})-(\d{4})?", vv)
    if mm:
        if mm[2] and mm[1] > mm[2]:
            return f"'{vv}': the range ends before it starts"
        return None
    return f"'{vv}' should be {TEMPORAL_FORMS}"


# ---------------------------------------------------------------------------
# The register
# ---------------------------------------------------------------------------

def read_register_row(register_path, accession_id):
    """Return (row as {iecode or column: value}, unknown IECode headers)."""

    path = pathlib.Path(register_path)
    if not path.is_file():
        raise MetadataError([f"Accession register not found: {path}"])

    with open(path, encoding="utf-8-sig", newline="") as ff:
        reader = csv.reader(ff)
        try:
            headers = next(reader)
        except StopIteration:
            raise MetadataError([f"Accession register is empty: {path}"])
        rows = [rr for rr in reader if any(cc.strip() for cc in rr)]

    columns = {}  # column index -> key
    unknown = []
    for ii, hh in enumerate(headers):
        hh_clean = hh.strip()
        if hh_clean.lower() in WORKFLOW_COLUMNS:
            columns[ii] = hh_clean.lower()
            continue
        iecode = header_to_iecode(hh_clean)
        if iecode is None:
            continue
        if iecode not in REGISTER_FIELDS and iecode not in COMPUTED:
            unknown.append(hh_clean)
            continue
        columns[ii] = iecode

    if "accession_id" not in columns.values():
        raise MetadataError([f"Accession register has no 'accession_id' column: {path}"])
    id_col = [ii for ii, kk in columns.items() if kk == "accession_id"][0]

    matches = [rr for rr in rows if len(rr) > id_col and rr[id_col].strip() == accession_id]
    if not matches:
        raise MetadataError([f"No row for accession '{accession_id}' in the register {path}"])
    if len(matches) > 1:
        raise MetadataError(
            [f"{len(matches)} rows for accession '{accession_id}' in the register; there must be one"]
        )

    row = {}
    for ii, key in columns.items():
        row[key] = matches[0][ii] if ii < len(matches[0]) else ""
    return row, unknown


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

class Record:
    """The metadata of one accession: {iecode: [values]}, plus workflow data."""

    def __init__(self, accession_id, s3_location, fields, warnings):
        self.accession_id = accession_id
        self.s3_location = s3_location
        self.fields = fields
        self.warnings = warnings

    def ordered(self):
        """[(iecode, value)] in output order, one pair per value."""
        pairs = []
        for iecode in OUTPUT_ORDER:
            for value in self.fields.get(iecode, []):
                pairs.append((iecode, value))
        return pairs

    def fingerprint(self):
        """Short hash of the register-based fields, to notice later changes."""
        text = json.dumps(
            {kk: vv for kk, vv in self.fields.items() if kk not in COMPUTED},
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def bag_info(self):
        """bag-info.txt fields: External-Identifier + one label per IECode."""
        info = {"External-Identifier": self.accession_id}
        for iecode, values in self.fields.items():
            if values:
                info[iecode] = values if len(values) > 1 else values[0]
        return info


def build_record(register_path, accession_id, vocab):
    """Read and check the accession's register row. Raise MetadataError with
    every problem found; return a Record otherwise."""

    row, unknown = read_register_row(register_path, accession_id)
    problems = []
    warnings = [f"Unknown register column '{hh}' ignored (misspelt?)" for hh in unknown]

    if not vocab.media_types:
        problems.append(
            "The IANA media types snapshot is missing. Run: archiveautomation-vocab refresh-iana"
        )

    s3_location = clean(row.get("s3_location"))
    if not s3_location:
        problems.append("s3_location: empty (needed to upload the bag)")

    fields = {}
    for iecode in REGISTER_FIELDS:
        raw = clean(row.get(iecode, ""))
        if not raw and iecode in vocab.defaults:
            raw = clean(vocab.defaults[iecode])

        values = [clean(vv) for vv in raw.split("|")] if raw else []
        values = [vv for vv in values if vv]

        if not values:
            if iecode in REQUIRED:
                problems.append(f"{iecode}: required, but empty")
            elif iecode in RECOMMENDED:
                warnings.append(f"{iecode}: empty (recommended)")
            continue

        if len(values) > 1 and iecode in SINGLE_VALUE:
            problems.append(f"{iecode}: takes one value, got {len(values)} ({raw})")
            continue

        if iecode in CONTROLLED:
            fixed = []
            for vv in values:
                canon = vocab.canonical(iecode, vv)
                if canon is None:
                    problems.append(
                        f"{iecode}: '{vv}' is not allowed. Allowed: {', '.join(vocab.allowed(iecode))}"
                    )
                else:
                    fixed.append(canon)
            values = fixed

        elif iecode in DATE_FIELDS:
            date, error = parse_date(values[0])
            if error:
                problems.append(f"{iecode}: {error}")
                continue
            if date is None:  # Undated
                if iecode == "DC.DATE_ACCEPTED":
                    problems.append("DC.DATE_ACCEPTED: 'Undated' is not allowed here")
                continue
            values = [date]

        elif iecode == "DC.COVERAGE_TEMPORAL":
            error = check_temporal(values[0])
            if error:
                problems.append(f"{iecode}: {error}")
                continue

        elif iecode == "DC.RIGHTS_ACCESS":
            level = vocab.rights_level(values[0])
            if level is None:
                allowed = ", ".join(lv for lv, _ in vocab.rights_access.values())
                problems.append(f"DC.RIGHTS_ACCESS: '{values[0]}' is not a level. Allowed: {allowed}")
                continue
            values = [level[1]]  # filled in below, once DC.SOURCE is known

        fields[iecode] = values

    # DC.RIGHTS_ACCESS sentences that name the source.
    if "DC.RIGHTS_ACCESS" in fields and "{DC.SOURCE}" in fields["DC.RIGHTS_ACCESS"][0]:
        if "DC.SOURCE" in fields:
            fields["DC.RIGHTS_ACCESS"] = [
                fields["DC.RIGHTS_ACCESS"][0].replace("{DC.SOURCE}", fields["DC.SOURCE"][0])
            ]
        elif "DC.SOURCE: required, but empty" not in problems:
            problems.append("DC.RIGHTS_ACCESS: Restricted needs DC.SOURCE to name who approves")

    for iecode in COMPUTED:
        if clean(row.get(iecode, "")) and iecode != "DC.IDENTIFIER":
            warnings.append(f"{iecode} is computed from the bag; the register value is ignored")
    if clean(row.get("DC.IDENTIFIER", "")) not in ("", accession_id):
        warnings.append("DC.IDENTIFIER is the accession ID; the register value is ignored")
    fields["DC.IDENTIFIER"] = [accession_id]

    if problems:
        raise MetadataError(problems)
    return Record(accession_id, s3_location, fields, warnings)


# ---------------------------------------------------------------------------
# DC.FORMAT and DC.FORMAT_EXTENT from DROID
# ---------------------------------------------------------------------------

def human_size(total_bytes):
    size = float(total_bytes)
    for unit in ["bytes", "KB", "MB", "GB", "TB"]:
        if size < 1000 or unit == "TB":
            break
        size /= 1000
    if unit == "bytes":
        return f"{total_bytes} bytes"
    return f"{size:.1f} {unit}"


def _plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count:,} {word}s"


def formats_from_droid(droid_csv, vocab):
    """Return (media types for DC.FORMAT, DC.FORMAT_EXTENT text, list of
    files that got the fallback media type)."""

    with open(droid_csv, encoding="utf-8-sig", newline="") as ff:
        reader = csv.reader(ff)
        headers = [hh.strip().upper() for hh in next(reader)]
        rows = list(reader)

    def col(name):
        return headers.index(name) if name in headers else None

    i_type, i_size, i_ext = col("TYPE"), col("SIZE"), col("EXT")
    i_path = col("FILE_PATH") if col("FILE_PATH") is not None else col("NAME")
    # DROID adds extra MIME_TYPE columns when a file matches several formats.
    i_mimes = [ii for ii, hh in enumerate(headers) if hh == "MIME_TYPE"]
    if i_type is None or i_size is None or not i_mimes:
        raise ValueError(f"{droid_csv} does not look like a DROID CSV export")

    def cell(rr, ii):
        return rr[ii].strip() if ii is not None and ii < len(rr) else ""

    media_types = []
    fallback_files = []
    total_bytes = 0
    kinds = {}  # kind -> [count, set of extensions]

    for rr in rows:
        if cell(rr, i_type).lower() not in ("file", "container"):
            continue
        total_bytes += int(cell(rr, i_size) or 0)

        candidates = []
        for ii in i_mimes:
            candidates += [mm.strip() for mm in cell(rr, ii).split(",") if mm.strip()]
        chosen = next((mm.lower() for mm in candidates if vocab.is_registered(mm)), None)
        if chosen is None:
            chosen = FALLBACK_MEDIA_TYPE
            reported = ", ".join(candidates) if candidates else "not identified"
            fallback_files.append(f"{cell(rr, i_path)} ({reported})")
        if chosen not in media_types:
            media_types.append(chosen)

        kind = vocab.kind_of(chosen)
        entry = kinds.setdefault(kind, [0, set()])
        entry[0] += 1
        ext = cell(rr, i_ext).lower().lstrip(".")
        if ext:
            entry[1].add(f".{ext}")

    total_files = sum(cc for cc, _ in kinds.values())
    parts = []
    for kind in vocab.kind_order:
        if kind in kinds:
            count, exts = kinds[kind]
            text = _plural(count, f"{kind} file")
            if exts:
                text += f"({', '.join(sorted(exts))})"
            parts.append(text)
    extent = f"{human_size(total_bytes)}: {_plural(total_files, 'file')}"
    if parts:
        extent += " " + ", ".join(parts)

    return sorted(media_types), extent, fallback_files


# ---------------------------------------------------------------------------
# Writing into the bag
# ---------------------------------------------------------------------------

def create_bag(bag_path, record):
    """Turn bag_path into a BagIt bag with the record in bag-info.txt."""
    return bagit.make_bag(str(bag_path), bag_info=record.bag_info(), checksums=["sha256"])


def write_metadata_files(bag_path, record):
    """Update bag-info.txt and write bag-info.xml and libnova_metadata.json.
    Call bagit's save afterwards (aalib.finalize_bag) for the tag manifest."""

    bag_path = pathlib.Path(bag_path)

    bag = bagit.Bag(str(bag_path))
    for key in list(bag.info):
        if key in ALL_FIELDS:
            del bag.info[key]
    bag.info.update(record.bag_info())
    bag.save()

    root = ET.Element("metadata")
    for iecode, value in record.ordered():
        ET.SubElement(root, iecode).text = value
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(
        bag_path / "bag-info.xml", encoding="UTF-8", xml_declaration=True
    )

    body = {"metadata": [{"iecode": ic, "value": vv} for ic, vv in record.ordered()]}
    with open(bag_path / "libnova_metadata.json", "w", encoding="utf-8") as ff:
        json.dump(body, ff, ensure_ascii=False, indent=2)
        ff.write("\n")
