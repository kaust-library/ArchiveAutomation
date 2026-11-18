# Automate the digital preservation workflow
# * read the accession's metadata from the accession register and check it
# * ClamAV scan, quarantine, second scan
# * copy the files into a BagIt bag, run DROID and JHOVE
# * write the Libnova metadata into the bag (bag-info.txt, bag-info.xml,
#   libnova_metadata.json)

import configparser
import logging
import os
import pathlib
import sys

import click

import aalib
import aametadata
from aavocab import DEFAULT_VOCAB_DIR, Vocabulary, VocabularyError

REPO_DIR = pathlib.Path(__file__).resolve().parent


def read_settings():
    """Paths of the register and vocabulary folder. Defaults: register\\ and
    vocabulary\\ next to this script; etc\\archiveautomation.cfg can override
    them in a [PATHS] section."""

    register = aametadata.DEFAULT_REGISTER
    vocab_dir = DEFAULT_VOCAB_DIR
    settings_file = REPO_DIR / "etc" / "archiveautomation.cfg"
    if settings_file.is_file():
        settings = configparser.ConfigParser()
        settings.read(settings_file, encoding="utf-8-sig")
        if settings.has_section("PATHS"):
            register = pathlib.Path(settings["PATHS"].get("register", register))
            vocab_dir = pathlib.Path(settings["PATHS"].get("vocabulary", vocab_dir))
    return register, vocab_dir


def load_record(register, vocab_dir, acc_number):
    """Read and check the accession's metadata; stop with every problem."""

    try:
        vocab = Vocabulary(vocab_dir)
        record = aametadata.build_record(register, acc_number, vocab)
    except VocabularyError as ee:
        logging.critical(f"{ee}. Exiting...")
        sys.exit(1)
    except aametadata.MetadataError as ee:
        print(f"\nMetadata for accession {acc_number} needs fixing ({register}):")
        for problem in ee.problems:
            print(f"  - {problem}")
        print()
        logging.critical("Fix the register row and run again. Nothing was scanned or copied.")
        sys.exit(1)

    for warning in record.warnings:
        logging.warning(warning)
    logging.info(
        f"Metadata for {acc_number} checked: {len(record.ordered())} values from the register"
    )
    return vocab, record


@click.command()
@click.argument("input", type=click.File("r"))
def aaflow(input):
    """Automate digital preservation workflow.

    From INPUT creates a BagIt bag carrying the accession's Libnova metadata.

    \b
    The INPUT contains the
    * accession number (its metadata is in the accession register),
    * source and destination folders,
    * ClamAV configuration,
    * Droid configuration,
    * Jhove configuration
    """

    # Show progress messages also when started with the 'archiveautomation'
    # command (the __main__ block below is skipped in that case).
    logging.basicConfig(
        format="%(asctime)s: %(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        level=logging.INFO,
    )
    # bagit logs every file it hashes; keep only its warnings and errors.
    logging.getLogger("bagit").setLevel(logging.WARNING)

    config = configparser.ConfigParser()
    config._interpolation = configparser.ExtendedInterpolation()
    # utf-8-sig: accepts UTF-8 files with or without a BOM (Notepad, Excel...).
    config.read(input.name, encoding="utf-8-sig")

    acc_number = config["ACCESSION"]["accession_id"].strip()
    bag_path = config["BAGGER"]["dest_dir"]
    source_list = [ii.strip() for ii in config["BAGGER"]["source_dir"].split(",")]

    if config.has_section("BAG-INFO"):
        logging.warning(
            "The [BAG-INFO] section of the accession config is no longer used; "
            "metadata comes from the accession register."
        )

    # Read and check the metadata first, so a problem stops the workflow
    # before the antivirus scan or any copying.
    register, vocab_dir = read_settings()
    vocab, record = load_record(register, vocab_dir, acc_number)

    for ss in source_list:
        if not aalib.is_path_OK(ss):
            logging.critical(f"Can't access path '{ss}'. Exiting...")
            sys.exit(1)

    if config["CLAMAV"].getboolean("run_it"):
        # Adding variables to the antivirus section so we have everything
        # we need in a single place before calling the function.
        config["CLAMAV"].update({"av_location": config["BAGGER"]["source_dir"]})
        config["CLAMAV"].update({"av_accession": acc_number})
        config["CLAMAV"].update({"quarantine_dir": "quarantine"})
        config["CLAMAV"].update({"metadata_fingerprint": record.fingerprint()})
        av_check_code, av_quarentine_file = aalib.av_check(config["CLAMAV"])

        # Second run: say if the register row changed since the first scan.
        lines = pathlib.Path(av_quarentine_file).read_text(encoding="utf-8").splitlines()
        if len(lines) > 1 and lines[1].strip() and lines[1].strip() != record.fingerprint():
            logging.warning(
                "The register row changed since the first scan; the bag uses the current row."
            )

    # Copy source folder(s) to destination (BagIt) folder.
    aalib.copy_src_dirs(source_list, bag_path)

    # Create the BagIt bag, with the register metadata in bag-info.txt
    try:
        aametadata.create_bag(bag_path, record)
    except Exception as ee:
        logging.critical(f"Error creating the bag in '{bag_path}': {ee}. Exiting...")
        sys.exit(1)

    # Run Droid on the "bag" folder
    _ = aalib.droid_run(config["DROID"], bag_path, acc_number)

    # DC.FORMAT and DC.FORMAT_EXTENT come from DROID's CSV.
    droid_csv = pathlib.Path(bag_path) / f"{acc_number}.csv"
    if not droid_csv.is_file():
        logging.critical(
            f"DROID's CSV {droid_csv} is missing, so DC.FORMAT and DC.FORMAT_EXTENT "
            "can't be set. Check the DROID output above. Exiting..."
        )
        sys.exit(1)
    media_types, extent, fallback_files = aametadata.formats_from_droid(droid_csv, vocab)
    record.fields["DC.FORMAT"] = media_types
    record.fields["DC.FORMAT_EXTENT"] = [extent]
    logging.info(f"DC.FORMAT: {', '.join(media_types)}")
    logging.info(f"DC.FORMAT_EXTENT: {extent}")
    if fallback_files:
        logging.warning(
            f"{len(fallback_files)} file(s) not identified or with an unregistered media "
            f"type got '{aametadata.FALLBACK_MEDIA_TYPE}'. Please review:"
        )
        for ff in fallback_files:
            print(f"    {ff}")

    # Write the metadata into the bag: bag-info.txt, bag-info.xml, libnova_metadata.json
    aametadata.write_metadata_files(bag_path, record)
    logging.info("Metadata written: bag-info.txt, bag-info.xml, libnova_metadata.json")

    # Run Jhove on the "bag" folder
    _ = aalib.jhove_run(config["JHOVE"], config["JHOVE MODULES"], bag_path, acc_number)

    # Add the metadata files and the DROID/JHOVE reports to the tag manifest,
    # so every file in the bag has a checksum.
    aalib.finalize_bag(bag_path)

    # The second scan finished and the bag is complete: end the quarantine.
    if config["CLAMAV"].getboolean("run_it"):
        logging.info(f"Removing quarantine file '{av_quarentine_file}'")
        os.remove(av_quarentine_file)

    # The End
    print("Have a nice day.")


if __name__ == "__main__":
    aaflow()
