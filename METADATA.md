# Accession metadata (Libnova)

Every bag carries the accession's Libnova record. The metadata is **not** typed
into the accession config: it comes from the accession register, is checked
against the shared vocabulary before anything is scanned or copied, and is
written into the bag in three files.

## Accession register

`register\accession_register.csv` — one row per accession, UTF-8 (in Excel:
*Save As → CSV UTF-8*). The `register\` folder is git-ignored: the repository
is public and the register holds unpublished metadata. **Never commit it.**

Start from `accession_register.csv.example`. Columns:

- `accession_id` — must match `accession_id` in the accession config; one row only.
- `s3_location` — where the bag will be uploaded in S3.
- `IECode: <field>` — one column per Libnova field, with the same headers as the
  physical inventory CSVs (`IECode: SOURCE` for DC.SOURCE; `IECode:DC.TYPE`
  without the space is accepted). Several values: `en | ar-SA`.

| Field | Required | Rule |
| --- | --- | --- |
| title, creator, DC.SOURCE | Yes | Free text |
| DC.TYPE, DC.LANGUAGE, appraised, accession | Yes | Controlled (`vocabulary\enums.json`); case is corrected |
| DC.RIGHTS_ACCESS | Yes | Public, Internal, Restricted or Highly Restricted (or the full sentence); written as its full sentence (`vocabulary\rights_access.json`) |
| DC.DATE, DC.DATE_ACCEPTED | Yes | `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, `YYYY-YYYY` or open `YYYY-` (written as YYYY-MM-DD); DC.DATE may be `Undated`. Slash dates are refused. |
| DC.DESCRIPTION, subject, DC.COVERAGE_TEMPORAL | Recommended | Warning if empty. DC.COVERAGE_TEMPORAL: `2020`, `2020-10`, `2008-2013` or open `2022-`, kept as typed |
| DC.DATE_COPYRIGHTED, DC.RELATION_HASVERSION, DC.ACCRUAL_* | Optional | |
| DC.PUBLISHER, DC.COVERAGE_SPATIAL, DC.FORMAT_MEDIUM, DC.RIGHTS | Default | From `vocabulary\defaults.json` unless the register gives a value |
| DC.IDENTIFIER, DC.FORMAT, DC.FORMAT_EXTENT | Computed | Accession ID; IANA media types and extent from DROID |

All problems in a row are listed together and the run stops before the
antivirus scan, so nothing is scanned, copied or quarantined.

## Shared vocabulary

`vocabulary\` is committed with the code. It holds the allowed values
(`enums.json`), the access sentences (`rights_access.json`), the defaults
(`defaults.json`), the file kinds for DC.FORMAT_EXTENT (`file_kinds.json`) and
a snapshot of the IANA media types registry (`iana\`).

```
archiveautomation-vocab refresh-iana              # fetch a new IANA snapshot (needs internet)
archiveautomation-vocab refresh-libnova --check   # compare enums.json with Libnova
archiveautomation-vocab refresh-libnova           # update enums.json from Libnova
archiveautomation-vocab show                      # list what the vocabulary holds
```

`refresh-libnova` reads the allowed values of DC.TYPE, DC.LANGUAGE, accession and
appraised from Libnova's metadata schema (`descriptor_id` in `enums.json`) and needs
`$env:LIBNOVA_API_KEY`. Commit the updated `enums.json` afterwards.

Run `refresh-iana` once after installing, then now and then. A file DROID can't
identify, or whose media type isn't registered, gets `application/octet-stream`
and is listed in the run output for review.

### From PowerShell (physical-archives scripts)

`powershell\AAVocabulary.ps1` gives PowerShell scripts the same lists:

```powershell
. "C:\Tools\ArchiveAutomation\powershell\AAVocabulary.ps1"
$enumFix = Get-AAEnumFix                       # same shape as the old hand-written table
Repair-AAEnumValue -IECode "DC.LANGUAGE" -Value "EN | ar-sa" -EnumFix $enumFix   # -> en, ar-SA
Get-AARightsAccess -Level "Restricted" -Source "Office of the Provost"
```

`Repair-AAEnumValue` splits on `|` first, then corrects each value, and warns
about values Libnova would refuse. Test: `powershell -ExecutionPolicy Bypass -File tests\test_vocabulary.ps1`.

## Files written into the bag

| File | Contents |
| --- | --- |
| `bag-info.txt` | BagIt's lines plus one line per IECode value (`DC.TYPE: Collection`); several values repeat the label |
| `bag-info.xml` | The record in the structure Libnova exports |
| `libnova_metadata.json` | The exact body for `PUT /file/{id}/metadata` |

All three are covered by `tagmanifest-sha256.txt`.

## Settings

Defaults need no settings. To keep the register or vocabulary elsewhere, copy
`etc\archiveautomation.cfg.example` to `etc\archiveautomation.cfg` and set
`[PATHS]`.

## Tests

```
pip install pytest
python -m pytest tests
```
