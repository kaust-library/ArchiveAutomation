"""Shared vocabulary for ArchiveAutomation (and the physical ingest scripts).

The vocabulary folder holds JSON files with the allowed values of controlled
Libnova fields, the DC.RIGHTS_ACCESS sentences, default values, the file kinds
used in DC.FORMAT_EXTENT, and a dated snapshot of the IANA media types registry.

Command line:
    python aavocab.py refresh-iana   download a new IANA snapshot
    python aavocab.py show           print what the vocabulary folder holds
"""

import csv
import datetime as DT
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_VOCAB_DIR = REPO_DIR / "vocabulary"

IANA_URL = "https://www.iana.org/assignments/media-types/{top}.csv"
IANA_TOP_TYPES = [
    "application", "audio", "font", "haptics", "image",
    "message", "model", "multipart", "text", "video",
]

FALLBACK_MEDIA_TYPE = "application/octet-stream"


class VocabularyError(Exception):
    pass


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as ff:
            return json.load(ff)
    except FileNotFoundError:
        raise VocabularyError(f"Vocabulary file not found: {path}")
    except json.JSONDecodeError as ee:
        raise VocabularyError(f"Vocabulary file {path} is not valid JSON: {ee}")


class Vocabulary:
    """Everything in the vocabulary folder, loaded once per run."""

    def __init__(self, vocab_dir=DEFAULT_VOCAB_DIR):
        self.dir = pathlib.Path(vocab_dir)
        if not self.dir.is_dir():
            raise VocabularyError(f"Vocabulary folder not found: {self.dir}")

        enums = _read_json(self.dir / "enums.json")
        # {iecode: {lower-case value: official spelling}}
        self.enums = {
            iecode: {vv.lower(): vv for vv in spec["values"]}
            for iecode, spec in enums.items()
            if not iecode.startswith("_")
        }

        rights = _read_json(self.dir / "rights_access.json")["levels"]
        # {lower-case level: (level, sentence)}
        self.rights_access = {lvl.lower(): (lvl, sentence) for lvl, sentence in rights.items()}

        self.defaults = {
            kk: vv for kk, vv in _read_json(self.dir / "defaults.json").items()
            if not kk.startswith("_")
        }

        self.file_kinds = _read_json(self.dir / "file_kinds.json")["kinds"]

        self.iana_dir = self.dir / "iana"
        self.media_types = load_iana_snapshot(self.iana_dir)
        retrieved = self.iana_dir / "RETRIEVED.txt"
        self.iana_retrieved = (
            retrieved.read_text(encoding="utf-8").strip() if retrieved.is_file() else ""
        )

    # -- controlled values -------------------------------------------------
    def allowed(self, iecode):
        return list(self.enums[iecode].values())

    def canonical(self, iecode, value):
        """Official spelling of 'value' for a controlled field, or None."""
        return self.enums[iecode].get(value.strip().lower())

    # -- media types ---------------------------------------------------------
    def is_registered(self, media_type):
        return media_type.strip().lower() in self.media_types

    def kind_of(self, media_type):
        mt = media_type.strip().lower()
        for kind in self.file_kinds:
            for entry in kind["media_types"]:
                entry = entry.lower()
                if entry.endswith(("/", ".")):
                    if mt.startswith(entry):
                        return kind["name"]
                elif mt == entry:
                    return kind["name"]
        return "other"

    @property
    def kind_order(self):
        return [kk["name"] for kk in self.file_kinds] + ["other"]


def load_iana_snapshot(iana_dir):
    """Set of registered media types (lower case) from the IANA CSV snapshot."""

    media_types = set()
    for csv_file in sorted(pathlib.Path(iana_dir).glob("*.csv")):
        media_types |= load_iana_snapshot_file(csv_file, csv_file.stem.lower())
    return media_types


def refresh_iana(vocab_dir=DEFAULT_VOCAB_DIR):
    """Download the IANA media type registry CSVs into vocab_dir/iana."""

    iana_dir = pathlib.Path(vocab_dir) / "iana"
    iana_dir.mkdir(parents=True, exist_ok=True)

    fetched = []
    for top in IANA_TOP_TYPES:
        url = IANA_URL.format(top=top)
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
        except urllib.error.HTTPError as ee:
            print(f"  {top}: skipped (HTTP {ee.code})")
            continue
        except urllib.error.URLError as ee:
            print(f"Could not reach {url}: {ee.reason}")
            print("Check the internet connection and try again. The old snapshot is unchanged.")
            return False
        (iana_dir / f"{top}.csv").write_bytes(data)
        count = len(load_iana_snapshot_file(iana_dir / f"{top}.csv", top))
        fetched.append(f"{top} ({count})")
        print(f"  {top}: {count} media types")

    stamp = DT.datetime.now().strftime("%Y-%m-%d %H:%M")
    (iana_dir / "RETRIEVED.txt").write_text(
        f"IANA Media Types registry, https://www.iana.org/assignments/media-types\n"
        f"Retrieved {stamp}: {', '.join(fetched)}\n",
        encoding="utf-8",
    )
    total = len(load_iana_snapshot(iana_dir))
    print(f"Saved {total} registered media types to {iana_dir}")
    return True


def load_iana_snapshot_file(csv_file, top):
    """Media types in one IANA CSV. Some early registrations have no template;
    for those the type is built from the top-level type and the name."""
    tmp = set()
    with open(csv_file, encoding="utf-8-sig", newline="") as ff:
        for row in csv.DictReader(ff):
            template = (row.get("Template") or "").strip()
            name = (row.get("Name") or "").strip().split(" ")[0]
            if "/" in template:
                tmp.add(template.lower())
            elif name:
                tmp.add(f"{top}/{name}".lower())
    return tmp


def _show(vocab_dir=DEFAULT_VOCAB_DIR):
    vv = Vocabulary(vocab_dir)
    print(f"Vocabulary folder: {vv.dir}")
    for iecode in vv.enums:
        print(f"  {iecode}: {', '.join(vv.allowed(iecode))}")
    print(f"  DC.RIGHTS_ACCESS levels: {', '.join(lv for lv, _ in vv.rights_access.values())}")
    print(f"  Defaults: {', '.join(vv.defaults)}")
    print(f"  File kinds: {', '.join(vv.kind_order)}")
    print(f"  IANA media types: {len(vv.media_types)}")
    print(f"  {vv.iana_retrieved}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["refresh-iana"]:
        return 0 if refresh_iana() else 1
    if argv[:1] == ["show"]:
        try:
            _show()
        except VocabularyError as ee:
            print(ee)
            return 1
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
