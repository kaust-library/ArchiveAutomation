import os
import sys
import bagit
import pathlib
import shutil
import configparser
import subprocess
import logging
import datetime as DT


def is_path_OK(pp: str) -> bool:
    "Check if path exists, or not"

    if pathlib.Path(pp).exists():
        return True
    else:
        return False


def jhove_run(jhove_config, jhove_modules, bag_path, acc_number):
    """Run Jhove"""

    jhove_exec_path = os.path.join(jhove_config["jhove_dir"], jhove_config["jhove_bin"])

    bag_path_data = os.path.join(bag_path, "data")

    # Items are the module name and its value, like "[('aiff-hul', 'True'),..."
    jhove_items = jhove_modules.items()

    # List of modules to be used (i.e., value is 'true')
    jhove_mod_list = [kk for (kk, vv) in jhove_items if jhove_modules.getboolean(kk)]

    # Return code
    jj_return = 0
    for jj in jhove_mod_list:
        # Module name, the 'aiff' part of 'aiff-hul'
        mod_name = jj.split("-")[0]

        jhove_out_fname = os.path.join(bag_path, f"jhove_{acc_number}_{mod_name}")

        if jhove_config.getboolean("jhove_xml"):
            jhove_cmd = f"{jhove_exec_path} -h xml -o {jhove_out_fname}.xml -m {jj} -kr {bag_path_data}"
        else:
            jhove_cmd = f"{jhove_exec_path} -o {jhove_out_fname}.txt -m {jj} -kr {bag_path_data}"

        try:
            print(f"Running jhove {jhove_cmd}")
            result = subprocess.run(
                jhove_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            result.check_returncode()
            print(result.stdout)
        except FileNotFoundError as ee:
            print(f"File not found error: {ee}")
            jj_return = 99
            break
        except Exception as ee:
            print(f"Generic Error running jhove: {ee}")
            jj_return = 99
            break
        else:
            jj_return = 0

    return jj_return


def droid_run(droid_config, bag_path, acc_number):
    """Run Droid on the destination folder"""

    #
    # Changing to working dir, that is, the "bag path"
    original_dir = os.getcwd()
    print(f"Changing from {original_dir} to {bag_path}\n")
    os.chdir(bag_path)

    #
    # Create a droid 'profile.'
    droid_exec_path = os.path.join(droid_config["droid_dir"], droid_config["droid_bin"])
    droid_bag_path = os.path.join(bag_path, "data")
    droid_cmd = f"{droid_exec_path} -a {droid_bag_path} --recurse -p {acc_number}.droid"
    print(f"Creating droid profile...")
    print(f"Running droid command {droid_cmd}")
    try:
        result = subprocess.run(
            droid_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        result.check_returncode()
        print(result.stdout)
        print("done.\n")

        #
        # Export profile in csv format.
        droid_csv = f"{droid_exec_path} -p {acc_number}.droid -e {acc_number}.csv"
        print(f"Exporting droid profile to csv...")
        print(f"Running droid command: {droid_csv}")
        result = subprocess.run(
            droid_csv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        result.check_returncode()
        print(result.stdout)
        print("done.\n")

    except FileNotFoundError as ee:
        print(f"Error running droid command: {ee}")

    except Exception as ee:
        print(f"Error running droid: {ee}")

    try:
        # DEBUG
        if not droid_config.getboolean("keep_profile"):
            print(f"Removing droid profile {acc_number}.droid")
            os.remove(f"{acc_number}.droid")
    except FileNotFoundError as ff:
        print(f"Droid profile {acc_number}.droid not found!!")

    #
    # Before leaving, return to original dir.
    print(f"Returning to {original_dir}\n")
    os.chdir(original_dir)


def check_infected(av_output):
    """Check the ClamAV summary for infected files.

    Returns False only when the summary says 'Infected files: 0' and at least
    one file was scanned. Anything else (infections, missing summary, scan
    error) returns True, so the workflow stops.
    """

    scanned_files = None
    infected_files = None
    for line in av_output.splitlines():
        if line.startswith("Scanned files:"):
            scanned_files = int(line.split(":")[1])
        elif line.startswith("Infected files:"):
            infected_files = int(line.split(":")[1])

    if scanned_files is None or infected_files is None:
        print("Error: could not find the ClamAV scan summary. Last lines of output:")
        print("\n".join(av_output.strip().splitlines()[-15:]))
        return True

    if scanned_files == 0:
        logging.critical("No scanned files. Something wrong. Please check AV logs.")
        sys.exit(1)

    print(f"Scanned {scanned_files} files")
    if infected_files == 0:
        print("OK: no infected files")
        return False

    if infected_files == 1:
        print("Caution: there is 1 infected file!!!!!")
    else:
        print(f"Caution: there are {infected_files} infected files!!!!!")
    return True


def check_quarantine(av_quarentine_file):
    """Check if the quarantine is over."""

    in_quarantine = True

    try:
        with open(av_quarentine_file, "r", encoding="utf-8") as ff_av:
            text = ff_av.readline()

        quar_str, av_run_str = text.split(":")
        quarantine = int(quar_str)
        av_run = DT.date.fromisoformat(av_run_str.strip())

        av_quar_end = av_run + DT.timedelta(days=quarantine)
        av_today = DT.date.today()

        if av_today > av_quar_end:
            # Quarantine is over.
            in_quarantine = False

    except Exception as ee:
        logging.error(
            f"\nError {ee} while reading quarantine file {av_quarentine_file}."
        )
        sys.exit(1)

    return in_quarantine


def av_check(av_config):
    """This routine controls the Anti-virus ClamAV life cycle.
    * Checks if it's the first scan of source files
    * if yes:
    *   run the first scan,
    *   create quarantine file,
    *   stop execution of the workflow
    * else:
    *   check if the quarantine is over:
    *   if not over:
    *      stop execution
    *   else:
    *      scan source files a second time
    *      continue the workflow
    """

    # Check if there is a file with the previous check, if "yes", then check if the
    # quarantine has expired before continuing.

    try:
        qq_dir = pathlib.Path(av_config["quarantine_dir"])
        if not qq_dir.exists():
            logging.info(f"Creating quarantine directory '{qq_dir}'")
            qq_dir.mkdir()
    except FileNotFoundError as ee:
        logging.error(f"A parent directory for {qq_dir} is missing in the path")
    except Exception as ee:
        logging.error(f"Error {ee} while creating quarantine directory {qq_dir}")
        av_run_code = 99
        clamav_quarentine_file = None
        return av_run_code, clamav_quarentine_file

    clamav_quarentine_file = (
        pathlib.Path(pathlib.Path.cwd())
        .joinpath(av_config["quarantine_dir"])
        .joinpath(av_config["av_accession"])
    )

    if not clamav_quarentine_file.is_file():
        logging.info(
            f"Quarentine file {clamav_quarentine_file} not found. Running first scan"
        )
        av_run_code = av_run(av_config)
        av_run_date = DT.datetime.today().strftime("%Y-%m-%d")
        clamav_status_line = f"{av_config['quarantine_days']}:{av_run_date}"
        with open(clamav_quarentine_file, "w", encoding="utf-8") as ff_av:
            ff_av.write(clamav_status_line + "\n")
            # Second line: fingerprint of the register metadata at the first scan,
            # so the second run can say if the row changed meanwhile.
            ff_av.write(av_config.get("metadata_fingerprint", "") + "\n")
        logging.info(
            f"Starting quarantine of '{av_config['quarantine_days']}' days for accession '{av_config['av_accession']}'",
        )
        sys.exit(0)
    else:
        in_quarantine = check_quarantine(clamav_quarentine_file)
        if in_quarantine:
            logging.info(
                f"Accession {av_config['av_accession']} still in quarantine. Stopping."
            )
            sys.exit(0)
        else:
            logging.info(f"Quarantine of accession {av_config['av_accession']} is over")
            av_run_code = av_run(av_config)
            # if av_run_code == 0:
            # # Assuming that the quarantine finished, and we completed the
            # # second scan of files, then we can remove the quarantine file.
            # logging.info(f'Removing {clamav_quarentine_file} after 2nd scan')
            # os.remove(clamav_quarentine_file)

            #
            # Returning the code of ClamAV check to parent routine. Here is causing problems
            # when the file is removed but the destination dir already exists and the script
            # stops. When we run the script again, the quarantine restarts!
            return av_run_code, clamav_quarentine_file


def av_run(av_config):
    """Run the 'clamav' antivirus. The output is ClamAV log file, saved in 'av_logs_root' directory
    specified in the 'CLAMAV' session of the configuration file. If the ClamAV log file reports an
    infected file, the execution of the workflow will stop."""

    # The date when we run the antivirus check that will be used to form
    # the name of the output file of the run.
    av_run_date = DT.datetime.today().strftime("%Y%m%d")

    # Don't forget to create the Docker volume:
    # docker volume create clam_db
    # No '-it': the output is captured, not shown in a terminal, and with
    # '-it' the Docker client can hang on Windows.
    print("Updating ClamAV database (freshclam)...", flush=True)
    av_update = "docker run --rm --name fresh_clam_db --mount source=clam_db,target=/var/lib/clamav clamav/clamav:latest freshclam"
    result = subprocess.run(
        av_update, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print(result.stdout)
        logging.critical(
            "ClamAV database update failed (is Docker Desktop running?). Exiting..."
        )
        sys.exit(1)
    print("done.", flush=True)

    #
    # Preparing the Docker ClamAV command line
    av_log_file = f"clamAVlog{av_config['av_accession']}_{av_run_date}.txt"
    docker_run = f"docker run --rm --name aa_docker"
    docker_target = f"-v \"{av_config['av_location']}:/scandir\""
    docker_log_target = f"-v \"{av_config['av_logs_root']}:/logs\""
    clam_db = "--mount source=clam_db,target=/var/lib/clamav"
    clam_run = "clamav/clamav:latest clamscan /scandir"
    clam_options = " --recursive=yes --verbose"
    log_av = f"--log=/logs/{av_log_file}"
    av_check = f"{docker_run} {docker_target} {docker_log_target} {clam_db} {clam_run} {log_av} {clam_options}"
    logging.info(f"Antivirus check: {av_check}")
    print(
        f"Scanning {av_config['av_location']} with ClamAV. This can take several "
        f"minutes; progress is in {av_config['av_logs_root']}\\{av_log_file}",
        flush=True,
    )
    result = subprocess.run(av_check, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    av_log = result.stdout
    # clamscan exit codes: 0 = clean, 1 = infected, 2 = error.
    if result.returncode not in (0, 1):
        print(av_log.decode("utf-8", errors="ignore")[-3000:])
        logging.critical(f"ClamAV scan failed (exit code {result.returncode}). Exiting...")
        sys.exit(1)

    logging.info(f"Checking for infected files")
    is_infected = check_infected(av_log.decode("utf-8", errors="ignore"))
    if is_infected:
        logging.critical("Caution!!!Possible infection!!!!")
        logging.critical("Aborting execution.")
        sys.exit(1)
    else:
        logging.info("End of 'av_run")
        return


def copy_src_dirs(source_dir, dest_dir):
    """Copy files from source directory to destination. The source can be multiple folders"""

    if os.path.exists(dest_dir):
        print(f"Directory {dest_dir} already exists. Remove it first.")
        sys.exit(1)

    try:
        if len(source_dir) == 1:
            source_dir = source_dir[0]
            print(f"Copying {source_dir} to {dest_dir}", end="... ")
            shutil.copytree(source_dir, dest_dir)
            print("done")
        else:
            dest_dir_orig = dest_dir
            for ii in source_dir:
                basename = pathlib.PurePath(ii).name
                dest_dir = pathlib.PurePath(dest_dir_orig).joinpath(basename)
                print(f"Copying from {pathlib.Path(ii)} to {dest_dir}", end="... ")
                shutil.copytree(ii, dest_dir)
                print("done")
    except FileExistsError:
        print(
            f"\nError: Destination folder '{dest_dir}' already exists. Remove the folder first. \nBye for now."
        )
        sys.exit(1)
    except Exception as ee:
        print(f"\nError {ee} while copying files. Aborting the script.")
        sys.exit(1)


def finalize_bag(bag_path):
    """Add every file written next to 'data' after the bag was made
    (bag-info.xml, DROID and JHOVE reports) to the tag manifest, so they
    get checksums too. The payload manifest is not touched."""

    try:
        my_bag = bagit.Bag(bag_path)
        my_bag.save()
    except Exception as ee:
        logging.critical(f"Error updating the tag manifest in '{bag_path}': {ee}")
        sys.exit(1)

    tag_files = sorted(ff for ff in my_bag.tagfile_entries())
    logging.info(f"Tag manifest updated ({len(tag_files)} files): {', '.join(tag_files)}")

    return my_bag
