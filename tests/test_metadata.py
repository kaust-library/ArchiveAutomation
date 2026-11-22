"""Tests for the accession register, checks, DROID formats and output files.

Run from the ArchiveAutomation folder:  python -m pytest tests
All data here is made up; the real register must never be committed.
"""

import csv
import json
import pathlib
import shutil
import xml.etree.ElementTree as ET

import bagit
import pytest

import aalib
import aametadata as am
from aavocab import Vocabulary

REPO = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

HEADERS = [
    "accession_id", "s3_location", "IECode: title", "IECode: creator", "IECode: SOURCE",
    "IECode:DC.TYPE", "IECode: DC.LANGUAGE", "IECode: DC.RIGHTS_ACCESS", "IECode: appraised",
    "IECode: accession", "IECode: DC.DATE", "IECode: DC.DATE_ACCEPTED", "IECode: DC.DESCRIPTION",
    "IECode: subject", "IECode: DC.COVERAGE_TEMPORAL", "IECode: DC.DATE_COPYRIGHTED",
]

GOOD = {
    "accession_id": "001_002_9999",
    "s3_location": "11/Digital Archives/001_002_9999",
    "IECode: title": "Test Committee, 2020",
    "IECode: creator": "Test Office",
    "IECode: SOURCE": "Test Office, Test Team",
    "IECode:DC.TYPE": "collection",           # wrong case: corrected
    "IECode: DC.LANGUAGE": "en | AR-sa",      # two values, wrong case
    "IECode: DC.RIGHTS_ACCESS": "restricted",
    "IECode: appraised": "yes",
    "IECode: accession": "kaust committee record",
    "IECode: DC.DATE": "2020",
    "IECode: DC.DATE_ACCEPTED": "2024-12-29",
    "IECode: DC.DESCRIPTION": "Meeting recordings and documents.",
    "IECode: subject": "Topic A | Topic B",
    "IECode: DC.COVERAGE_TEMPORAL": "2020",
    "IECode: DC.DATE_COPYRIGHTED": "2020-01-01",
}


@pytest.fixture
def vocab(tmp_path):
    vdir = tmp_path / "vocabulary"
    shutil.copytree(REPO / "vocabulary", vdir)
    shutil.rmtree(vdir / "iana")
    shutil.copytree(FIXTURES / "iana", vdir / "iana")
    return Vocabulary(vdir)


def write_register(path, rows, headers=HEADERS):
    with open(path, "w", newline="", encoding="utf-8-sig") as ff:
        ww = csv.DictWriter(ff, fieldnames=headers)
        ww.writeheader()
        for rr in rows:
            ww.writerow({hh: rr.get(hh, "") for hh in headers})
    return path


def problems_for(tmp_path, vocab, **changes):
    row = dict(GOOD, **changes)
    reg = write_register(tmp_path / "reg.csv", [row])
    with pytest.raises(am.MetadataError) as ee:
        am.build_record(reg, row["accession_id"], vocab)
    return ee.value.problems


# -- the good row ---------------------------------------------------------------

def test_good_row(tmp_path, vocab):
    reg = write_register(tmp_path / "reg.csv", [GOOD])
    rec = am.build_record(reg, "001_002_9999", vocab)
    ff = rec.fields
    assert ff["DC.TYPE"] == ["Collection"]
    assert ff["DC.LANGUAGE"] == ["en", "ar-SA"]
    assert ff["appraised"] == ["Yes"]
    assert ff["accession"] == ["KAUST Committee record"]
    assert ff["DC.DATE"] == ["2020-01-01"]
    assert ff["subject"] == ["Topic A", "Topic B"]
    assert ff["DC.IDENTIFIER"] == ["001_002_9999"]
    assert ff["DC.RIGHTS_ACCESS"] == [
        "Restricted. Approval from Test Office, Test Team is required to access item."
    ]
    # defaults filled in
    assert ff["DC.PUBLISHER"] == ["King Abdullah University of Science and Technology"]
    assert ff["DC.FORMAT_MEDIUM"] == ["Digital"]
    assert rec.s3_location == "11/Digital Archives/001_002_9999"


def test_register_value_beats_default(tmp_path, vocab):
    headers = HEADERS + ["IECode: DC.COVERAGE_SPATIAL"]
    row = dict(GOOD, **{"IECode: DC.COVERAGE_SPATIAL": "Jeddah, Saudi Arabia"})
    reg = write_register(tmp_path / "reg.csv", [row], headers)
    rec = am.build_record(reg, "001_002_9999", vocab)
    assert rec.fields["DC.COVERAGE_SPATIAL"] == ["Jeddah, Saudi Arabia"]


def test_rights_access_levels(tmp_path, vocab):
    for level, expected in [
        ("Public", "Public access permitted."),
        ("INTERNAL", "KAUST internal access only."),
        ("highly restricted",
         "Highly Restricted. Approval from KAUST Office of the President is required to access item."),
    ]:
        row = dict(GOOD, **{"IECode: DC.RIGHTS_ACCESS": level})
        reg = write_register(tmp_path / "reg.csv", [row])
        rec = am.build_record(reg, "001_002_9999", vocab)
        assert rec.fields["DC.RIGHTS_ACCESS"] == [expected]


# -- checks ---------------------------------------------------------------------

def test_all_problems_reported_at_once(tmp_path, vocab):
    problems = problems_for(
        tmp_path, vocab,
        **{"IECode: title": "", "IECode: accession": "Committee records",
           "IECode: DC.DATE": "5/6/2010", "s3_location": ""},
    )
    text = "\n".join(problems)
    assert len(problems) == 4
    assert "title: required" in text
    assert "'Committee records' is not allowed. Allowed: Correspondence" in text
    assert "'5/6/2010' is ambiguous; use YYYY-MM-DD" in text
    assert "s3_location: empty" in text


@pytest.mark.parametrize("value,expected", [
    ("2007", "2007-01-01"), ("2008-08", "2008-08-01"), ("2007-2009", "2007-01-01"),
    ("2008-08-05", "2008-08-05"), ("20080805", "2008-08-05"),
])
def test_date_rules(value, expected):
    assert am.parse_date(value) == (expected, None)


@pytest.mark.parametrize("value,expected", [("2022-", "2022-01-01")])
def test_open_date(value, expected):
    assert am.parse_date(value) == (expected, None)


@pytest.mark.parametrize("value", ["2020", "2020-10", "2008-2013", "2022-"])
def test_temporal_forms(value):
    assert am.check_temporal(value) is None


@pytest.mark.parametrize("value", ["2020-13", "2013-2008", "2020s", "10/12/2012", "-2020"])
def test_bad_temporal(value):
    assert am.check_temporal(value)


def test_rights_access_sentence_accepted(tmp_path, vocab):
    """Rows copied from Libnova hold the sentence, not the level name."""
    for given, expected in [
        ("Public access permitted.", "Public access permitted."),
        ("KAUST internal access only.", "KAUST internal access only."),
        ("Restricted. Approval from Someone Else is required to access item.",
         "Restricted. Approval from Test Office, Test Team is required to access item."),
    ]:
        row = dict(GOOD, **{"IECode: DC.RIGHTS_ACCESS": given})
        reg = write_register(tmp_path / "reg.csv", [row])
        rec = am.build_record(reg, "001_002_9999", vocab)
        assert rec.fields["DC.RIGHTS_ACCESS"] == [expected]


@pytest.mark.parametrize("value", ["5/27/2010", "2010-02-30", "2009-2007", "March 2010"])
def test_bad_dates(value):
    date, error = am.parse_date(value)
    assert date is None and error


def test_undated(tmp_path, vocab):
    row = dict(GOOD, **{"IECode: DC.DATE": "Undated"})
    reg = write_register(tmp_path / "reg.csv", [row])
    rec = am.build_record(reg, "001_002_9999", vocab)
    assert "DC.DATE" not in rec.fields
    assert problems_for(tmp_path, vocab, **{"IECode: DC.DATE_ACCEPTED": "Undated"}) == [
        "DC.DATE_ACCEPTED: 'Undated' is not allowed here"
    ]


def test_single_value_fields(tmp_path, vocab):
    assert problems_for(tmp_path, vocab, **{"IECode: appraised": "Yes | No"}) == [
        "appraised: takes one value, got 2 (Yes | No)"
    ]


def test_bad_rights_level_and_temporal(tmp_path, vocab):
    problems = problems_for(
        tmp_path, vocab,
        **{"IECode: DC.RIGHTS_ACCESS": "Secret", "IECode: DC.COVERAGE_TEMPORAL": "2020s"},
    )
    assert any("'Secret' is not a level" in pp for pp in problems)
    assert any("should be 2020, 2020-10, 2008-2013 or 2022- (open)" in pp for pp in problems)


def test_missing_and_duplicate_rows(tmp_path, vocab):
    reg = write_register(tmp_path / "reg.csv", [GOOD, GOOD])
    with pytest.raises(am.MetadataError, match="2 rows for accession"):
        am.build_record(reg, "001_002_9999", vocab)
    with pytest.raises(am.MetadataError, match="No row for accession '001_002_0000'"):
        am.build_record(reg, "001_002_0000", vocab)
    with pytest.raises(am.MetadataError, match="register not found"):
        am.build_record(tmp_path / "nope.csv", "001_002_9999", vocab)


def test_unknown_column_is_a_warning(tmp_path, vocab):
    headers = HEADERS + ["IECode: DC.TYPPE"]
    reg = write_register(tmp_path / "reg.csv", [GOOD], headers)
    rec = am.build_record(reg, "001_002_9999", vocab)
    assert any("IECode: DC.TYPPE" in ww for ww in rec.warnings)


def test_missing_iana_snapshot(tmp_path, vocab):
    shutil.rmtree(vocab.dir / "iana")
    bare = Vocabulary(vocab.dir)
    reg = write_register(tmp_path / "reg.csv", [GOOD])
    with pytest.raises(am.MetadataError, match="refresh-iana"):
        am.build_record(reg, "001_002_9999", bare)


# -- DROID ------------------------------------------------------------------------

DROID_HEADERS = ["ID", "PARENT_ID", "URI", "FILE_PATH", "NAME", "METHOD", "STATUS", "SIZE",
                 "TYPE", "EXT", "LAST_MODIFIED", "EXTENSION_MISMATCH", "HASH",
                 "FORMAT_COUNT", "PUID", "MIME_TYPE", "FORMAT_NAME", "FORMAT_VERSION"]


def droid_csv(path, files, extra_mime=None):
    """files: [(name, size, ext, mime)]; extra_mime adds DROID's second
    PUID/MIME_TYPE columns for a file matching two formats."""
    headers = DROID_HEADERS + (["PUID", "MIME_TYPE", "FORMAT_NAME", "FORMAT_VERSION"] if extra_mime else [])
    with open(path, "w", newline="", encoding="utf-8") as ff:
        ww = csv.writer(ff)
        ww.writerow(headers)
        ww.writerow(["1", "", "file:/data/", "C:\\bag\\data", "data", "", "Done", "",
                     "Folder", "", "", "false", "", "", "", "", "", ""])
        for ii, (name, size, ext, mime) in enumerate(files, start=2):
            row = [str(ii), "1", f"file:/data/{name}", f"C:\\bag\\data\\{name}", name,
                   "Signature", "Done", str(size), "File", ext, "", "false", "", "1",
                   "fmt/x", mime, "Format", ""]
            if extra_mime:
                row += ["fmt/y", extra_mime.get(name, ""), "", ""]
            ww.writerow(row)
    return path


def test_formats_and_extent_like_libnova_export(tmp_path, vocab):
    files = (
        [(f"d{ii}.docx", 1_000_000, "docx",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document") for ii in range(20)]
        + [(f"p{ii}.pdf", 1_000_000, "pdf", "application/pdf") for ii in range(10)]
        + [(f"x{ii}.xlsx", 1_000_000, "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") for ii in range(6)]
        + [(f"v{ii}.mp4", 466_000_000, "mp4", "video/mp4") for ii in range(4)]
    )
    types, extent, fallback = am.formats_from_droid(droid_csv(tmp_path / "d.csv", files), vocab)
    assert extent == "1.9 GB: 40 files 36 document files(.docx, .pdf, .xlsx), 4 video files(.mp4)"
    assert types == sorted([
        "application/pdf", "video/mp4",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ])
    assert fallback == []


def test_unregistered_and_unidentified(tmp_path, vocab):
    files = [("a.pdf", 10, "pdf", "application/pdf"),
             ("b.foo", 20, "foo", "application/x-foo"),
             ("c", 30, "", ""),
             ("d.jpg", 40, "jpg", "image/jpeg")]   # registered via Name (no template)
    types, extent, fallback = am.formats_from_droid(droid_csv(tmp_path / "d.csv", files), vocab)
    assert types == ["application/octet-stream", "application/pdf", "image/jpeg"]
    assert extent == "100 bytes: 4 files 1 document file(.pdf), 1 image file(.jpg), 2 other files(.foo)"
    assert len(fallback) == 2 and "application/x-foo" in fallback[0] and "not identified" in fallback[1]


def test_second_mime_column(tmp_path, vocab):
    files = [("a.weird", 10, "weird", "application/x-weird")]
    path = droid_csv(tmp_path / "d.csv", files, extra_mime={"a.weird": "application/zip"})
    types, _, fallback = am.formats_from_droid(path, vocab)
    assert types == ["application/zip"] and fallback == []


# -- output files ------------------------------------------------------------------

def test_bag_with_metadata_files(tmp_path, vocab):
    reg = write_register(tmp_path / "reg.csv", [GOOD])
    rec = am.build_record(reg, "001_002_9999", vocab)
    bag_dir = tmp_path / "bag"
    bag_dir.mkdir()
    (bag_dir / "report.pdf").write_bytes(b"%PDF-1.4 test")
    am.create_bag(bag_dir, rec)

    rec.fields["DC.FORMAT"] = ["application/pdf"]
    rec.fields["DC.FORMAT_EXTENT"] = ["13 bytes: 1 file 1 document file(.pdf)"]
    (bag_dir / "001_002_9999.csv").write_text("droid csv", encoding="utf-8")
    am.write_metadata_files(bag_dir, rec)
    aalib.finalize_bag(str(bag_dir))

    bag = bagit.Bag(str(bag_dir))
    assert bag.is_valid()
    assert bag.info["DC.LANGUAGE"] == ["en", "ar-SA"]           # repeated label
    assert bag.info["DC.FORMAT"] == "application/pdf"
    assert bag.info["External-Identifier"] == "001_002_9999"
    tagged = set(bag.tagfile_entries())
    assert {"bag-info.xml", "libnova_metadata.json", "001_002_9999.csv"} <= tagged

    root = ET.parse(bag_dir / "bag-info.xml").getroot()
    assert root.tag == "metadata"
    assert root[0].tag == "DC.IDENTIFIER"
    assert [ee.text for ee in root.findall("DC.LANGUAGE")] == ["en", "ar-SA"]

    body = json.loads((bag_dir / "libnova_metadata.json").read_text(encoding="utf-8"))
    assert body["metadata"][0] == {"iecode": "DC.IDENTIFIER", "value": "001_002_9999"}
    assert {"iecode": "subject", "value": "Topic B"} in body["metadata"]
    assert len(body["metadata"]) == len(rec.ordered())


def test_arabic_text(tmp_path, vocab):
    row = dict(GOOD, **{"IECode: title": "مجموعة صور الحرم الجامعي"})
    reg = write_register(tmp_path / "reg.csv", [row])
    rec = am.build_record(reg, "001_002_9999", vocab)
    bag_dir = tmp_path / "bag"
    bag_dir.mkdir()
    (bag_dir / "a.txt").write_text("x", encoding="utf-8")
    am.create_bag(bag_dir, rec)
    am.write_metadata_files(bag_dir, rec)
    assert "مجموعة صور الحرم الجامعي" in (bag_dir / "bag-info.xml").read_text(encoding="utf-8")
    assert bagit.Bag(str(bag_dir)).info["title"] == "مجموعة صور الحرم الجامعي"


# -- IANA refresh ------------------------------------------------------------------

def test_refresh_iana(tmp_path, monkeypatch):
    import io
    import urllib.error
    import aavocab

    def fake_urlopen(url, timeout=60):
        top = url.rsplit("/", 1)[1].removesuffix(".csv")
        src = FIXTURES / "iana" / f"{top}.csv"
        if not src.is_file():
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return io.BytesIO(src.read_bytes())

    monkeypatch.setattr(aavocab.urllib.request, "urlopen", fake_urlopen)
    vdir = tmp_path / "vocabulary"
    shutil.copytree(REPO / "vocabulary", vdir)
    assert aavocab.refresh_iana(vdir)
    vv = Vocabulary(vdir)
    assert vv.is_registered("application/pdf") and vv.is_registered("text/plain")
    assert "Retrieved" in vv.iana_retrieved


# -- Libnova refresh ---------------------------------------------------------------

class FakeLibnova:
    """Answers GET /objects/metadata/schema/descriptor/{id} like ls-kaust does."""
    base_url = "https://example.invalid/api"
    SCHEMA = {
        96: ("DC.TYPE", ["Collection", "Dataset", "Event", "Image", "Interactive Resource",
                         "Moving Image", "Physical Object", "Service", "Software", "Sound",
                         "Still Image", "Text"]),
        102: ("DC.LANGUAGE", ["en", "ar-SA", "fr", "zh-CN", "es", "pt", "id", "ur", "de"]),
        177: ("accession", ["Correspondence", "KAUST event"]),
        178: ("appraised", ["Yes", "No"]),
    }

    def call(self, method, path, body=None):
        did = int(path.rsplit("/", 1)[1])
        iecode, values = self.SCHEMA[did]
        return {"success": True, "result": {"id": did, "iecode": iecode,
                                            "enum_values": json.dumps(values)}}


def old_vocabulary(tmp_path):
    """A vocabulary folder with a fixed, outdated enums.json, so the test does
    not depend on how up to date the repo's own vocabulary is."""
    vdir = tmp_path / "vocabulary"
    shutil.copytree(REPO / "vocabulary", vdir)
    (vdir / "enums.json").write_text(json.dumps({
        "DC.TYPE": {"descriptor_id": 96, "values": FakeLibnova.SCHEMA[96][1]},
        "DC.LANGUAGE": {"descriptor_id": 102, "values": ["en", "ar-SA"]},
        "appraised": {"descriptor_id": 178, "values": ["Yes", "No"]},
        "accession": {"descriptor_id": 177, "values": ["Correspondence", "KAUST event", "KAUST gift"]},
    }), encoding="utf-8")
    return vdir


def test_refresh_libnova(tmp_path, capsys):
    import aavocab
    vdir = old_vocabulary(tmp_path)

    assert aavocab.refresh_libnova(vdir, check_only=True, client=FakeLibnova())
    out = capsys.readouterr().out
    assert "+ zh-CN" in out and "- KAUST gift" in out and "nothing written" in out
    assert "zh-CN" not in (vdir / "enums.json").read_text(encoding="utf-8")

    assert aavocab.refresh_libnova(vdir, client=FakeLibnova())
    vv = Vocabulary(vdir)
    assert vv.allowed("DC.LANGUAGE") == ["en", "ar-SA", "fr", "zh-CN", "es", "pt", "id", "ur", "de"]
    assert vv.canonical("DC.LANGUAGE", "ZH-cn") == "zh-CN"
    assert vv.allowed("DC.TYPE")[0] == "Collection"


def test_refresh_libnova_wrong_descriptor(tmp_path, capsys):
    import aavocab
    vdir = old_vocabulary(tmp_path)
    enums = json.loads((vdir / "enums.json").read_text(encoding="utf-8"))
    enums["appraised"]["descriptor_id"] = 96          # points at DC.TYPE
    (vdir / "enums.json").write_text(json.dumps(enums), encoding="utf-8")
    assert not aavocab.refresh_libnova(vdir, client=FakeLibnova())
    assert "Fix descriptor_id" in capsys.readouterr().out


# -- 'x-' MIME types and ClamAV's size limit ---------------------------------

def test_x_mime_type_uses_registered_form(tmp_path, vocab):
    """DROID reports MKV as video/x-matroska; IANA registered video/matroska."""
    files = [("v.mkv", 19_000_000_000, "mkv", "video/x-matroska"),
             ("b.foo", 20, "foo", "application/x-foo")]   # no registered form: fallback
    types, extent, fallback = am.formats_from_droid(droid_csv(tmp_path / "d.csv", files), vocab)
    assert types == ["application/octet-stream", "video/matroska"]
    assert "1 video file(.mkv)" in extent
    assert len(fallback) == 1 and "application/x-foo" in fallback[0]


def test_registered_form(vocab):
    assert vocab.registered_form("video/x-matroska") == "video/matroska"
    assert vocab.registered_form("Video/MP4") == "video/mp4"
    assert vocab.registered_form("application/x-foo") is None


def test_files_over_clamav_limit_noted_in_log(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "small.txt").write_bytes(b"x" * 10)
    with open(src / "sub" / "big.mkv", "wb") as ff:   # sparse: no real 101 MB written
        ff.truncate(aalib.CLAMAV_MAX_FILESIZE_BYTES + 1)
    big = aalib.files_over_clamav_limit(src)
    assert big == [(str(pathlib.Path("sub") / "big.mkv"), aalib.CLAMAV_MAX_FILESIZE_BYTES + 1)]

    log = tmp_path / "clamAVlog.txt"
    log.write_text("----------- SCAN SUMMARY -----------\nInfected files: 0\n", encoding="utf-8")
    aalib.note_unscanned_files(log, big)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("----------- SCAN SUMMARY")   # ClamAV's own lines kept
    assert "FILES NOT SCANNED" in text and "big.mkv" in text and "--max-filesize=100M" in text
