"""Check one accession's register row with the same checks as the workflow.

Usage (from the ArchiveAutomation folder, venv active):
    python check_accession.py 013_001_0015

Prints every problem, or the values that would be written into the bag.
Nothing is changed.
"""

import sys

import aametadata as am
from archiveautomation import read_settings
from aavocab import Vocabulary, VocabularyError


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    accession_id = sys.argv[1].strip()
    register, vocab_dir = read_settings()
    try:
        record = am.build_record(register, accession_id, Vocabulary(vocab_dir))
    except VocabularyError as ee:
        print(ee)
        return 1
    except am.MetadataError as ee:
        print(f"{accession_id} needs fixing ({register}):")
        for problem in ee.problems:
            print(f"  - {problem}")
        return 1

    print(f"{accession_id}: OK. Values that will be written (DC.FORMAT and "
          f"DC.FORMAT_EXTENT are added after DROID):")
    for iecode, value in record.ordered():
        print(f"  {iecode:<22} {value}")
    print(f"  {'s3_location':<22} {record.s3_location}")
    for warning in record.warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
