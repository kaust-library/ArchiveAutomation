
from cgitb import text
import os
from pickle import TRUE
import sys
from unittest import result
import requests
import bagit
import pathlib
import shutil
import configparser
import subprocess
import logging
import datetime as DT
from dotenv import load_dotenv
from dcxml import simpledc



def jhove_run(jhove_config, bag_path, acc_number):
    """Run Jhove"""

    jhove_exec_path = os.path.join(jhove_config['jhove_dir'], jhove_config['jhove_bin'])

    # Notice the extension to file name is missing. This will be added later.
    jhove_out_fname = os.path.join(bag_path, f"jhove_{acc_number}")

    bag_path_data = os.path.join(bag_path, "data")

    if jhove_config['jhove_xml'].upper() == "TRUE":
        jhove_cmd = f"{jhove_exec_path} -h xml -o {jhove_out_fname}.xml -m {jhove_config['jhove_module']} -kr {bag_path_data}"
    else:
        jhove_cmd = f"{jhove_exec_path} -o {jhove_out_fname}.txt -m {jhove_config['jhove_module']} -kr {bag_path_data}"

    try:
        print(f"Running jhove {jhove_cmd}")
        result = subprocess.run(jhove_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        result.check_returncode()
        print(result.stdout)
    except FileNotFoundError as ee:
        print(f"Error running jhove command: {ee}")
    except Exception as ee: 
        print(f"Generic Error running jhove: {ee}")

def droid_run(droid_config, bag_path, acc_number):
    """Run Droid on the destination folder"""

    #
    # Changing to working dir, that is, the "bag path"
    original_dir = os.getcwd()
    print(f"Changing from {original_dir} to {bag_path}\n")
    os.chdir(bag_path)

    #
    # Create a droid 'profile.'
    droid_exec_path = os.path.join(droid_config['droid_dir'], droid_config['droid_bin'])
    droid_bag_path = os.path.join(bag_path, "data")
    droid_cmd = f"{droid_exec_path} -a {droid_bag_path} -p {acc_number}.droid"
    print(f"Creating droid profile...")
    print(f"Running droid command {droid_cmd}")
    try:
        result = subprocess.run(droid_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        result.check_returncode()
        print(result.stdout)
        print("done.\n")

        #
        # Export profile in csv format.
        droid_csv = f"{droid_exec_path} -p {acc_number}.droid -e {acc_number}.csv"
        print(f"Exporting droid profile to csv...")
        print(f"Running droid command: {droid_csv}")
        result = subprocess.run(droid_csv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        result.check_returncode()
        print(result.stdout)
        print("done.\n")

    except FileNotFoundError as ee:
        print(f"Error running droid command: {ee}")

    except Exception as ee: 
        print(f"Error running droid: {ee}")

    try:
        # DEBUG
        if droid_config['keep_profile'].upper() == "FALSE":
            print(f"Removing droid profile {acc_number}.droid")
            os.remove(f"{acc_number}.droid")
    except FileNotFoundError as ff:
        print(f"Droid profile {acc_number}.droid not found!!")
        
    #
    # Before leaving, return to original dir.
    print(f"Returning to {original_dir}\n")

def check_infected(av_output):
    """Check if there is any infectd file on the log file of the anti virus"""

    is_infected = True
    text = av_output.strip().split('\n')
    total_line = text[-7]
    infect_line = text[-6]
    scanned_files = total_line.split()[-1]
    infect_field, infect_num = infect_line.split()[0], infect_line.split()[2]
    print(f"Scanned {scanned_files} files")
    if infect_field == "Infected" and int(infect_num) == 0:
        print(f"OK: no infected files")
        is_infected = False
    elif infect_line == "Infected" and int(infect_num) != 0:
        if int(infect_num) == 1:
            print(f"Caution: there is 1 infected file!!!!!")
        else:
            print(f"Caution: there are {infect_num} infected files!!!!!")
    else:
        print(f"Error: could not find 'Infected' line in the output")

    return is_infected

def check_quarantine(av_quarentine_file):
    """Check if the quarantine is over."""

    in_quarantine = True

    try:
        with open(av_quarentine_file, 'r', encoding="utf-8") as ff_av:
            text = ff_av.readline()

        quar_str, av_run_str = text.split(':')
        quarantine = int(quar_str)
        av_run = DT.date.fromisoformat(av_run_str.strip())

        av_quar_end = av_run + DT.timedelta(days=quarantine)
        av_today = DT.date.today()

        if av_today > av_quar_end:
            # Quarantine is over.
            in_quarantine = False
    
    except Exception as ee:
        logging.error(f"\nError {ee} while reading quarantine file {av_quarentine_file}.")
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

    clamav_quarentine_file = os.path.join(av_config['quarantine_dir'], 
        av_config['av_accession'])
    
    if not os.path.isfile(clamav_quarentine_file):
        logging.info(f'Quarentine file {clamav_quarentine_file} not found. Running first scan')
        _ = av_run(av_config)
        av_run_date = DT.datetime.today().strftime("%Y-%m-%d")
        clamav_status_line = f"{av_config['quarantine_days']}:{av_run_date}"
        with open(clamav_quarentine_file, 'w', encoding="utf-8") as ff_av:
            ff_av.write(clamav_status_line)
        logging.info(f"Starting quarantine of {av_config['quarantine_days']} for accession {av_config['av_accession']}")
        sys.exit(0)
    else:
        in_quarantine = check_quarantine(clamav_quarentine_file)
        if in_quarantine:
            logging.info(f"Accession {av_config['av_accession']} still in quarantine. Stopping.")
            sys.exit(0)
        else:
            logging.info(f"Quarantine of accession {av_config['av_accession']} is over")
            _ = av_run(av_config)
            # TODO: if quarantine is over, probably we can remove the quarantine file, 'clamav_quarentine_file'

def av_run(av_config):
    """Run the 'clamav' antivirus. The output is ClamAV log file, saved in 'av_logs_root' directory
    specified in the 'CLAMAV' session of the configuration file. If the ClamAV log file reports an
    infected file, the execution of the workflow will stop."""

    # The date when we run the antivirus check that will be used to form
    # the name of the output file of the run.
    av_run_date = DT.datetime.today().strftime("%Y%m%d")

    # Update the antivirus database    
    # pathlib.Path(av_check)
    av_update = pathlib.Path(f"{av_config['av_dir']}/{av_config['av_update']}")
    print(f"Antivirus update: {av_update}", end='... ')
    #
    # Testing the command line for AV. Remove after testing.
    if av_config['run_it'].upper() != "FALSE":
        result = subprocess.run(av_update, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print("done.")

    # Antivirus command line

    av_log_file = os.path.join(av_config['av_logs_root'], f"{av_config['av_accession']}_{av_run_date}.txt")
    clamav_bin_file = pathlib.Path( av_config['av_dir'], av_config['av_clamav'] )
    av_check = f" {clamav_bin_file} --recursive \"{av_config['av_location']}\" -v -a -l \"{av_log_file}\""
    av_cleck_list = av_check.split()
    print(f"av_cleck_list: {av_cleck_list}")
    print(f"Antivirus check: {av_check}", end='... ')
    result = subprocess.run(av_cleck_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print("done.")

    print(f"clamav log: {result.stdout}")

    # Preparing to check the amount of infected files
    print(f"Writing ClamAV output file {av_log_file}", end='... ')
    try:
        with open(av_log_file, 'w', encoding="utf-8") as ff:
            ff.writelines(result.stdout)
        print("done.")
        is_infected = check_infected(result.stdout)
        if is_infected:
            logging.critical("Caution!!!Possible infection!!!!")
            logging.critical("Aborting execution.")
            sys.exit(1)
    except Exception as ee:
        logging.error(f"Error {ee} writing ClamAV logs.")
        sys.exit(1)

def copy_src_dirs(source_dir, dest_dir):
    """Copy files from source directory to destination. The source can be multiple folders"""

    if os.path.exists(dest_dir):
        print(f"Directory {dest_dir} already exists. Remove it first.")
        sys.exit(1)

    try:
        if len(source_dir) == 1:
            source_dir = source_dir[0]
            print(f"Copying {source_dir} to {dest_dir}", end='... ')
            shutil.copytree(source_dir, dest_dir)
            print('done')
        else:
            dest_dir_orig = dest_dir
            for ii in source_dir:
                basename = pathlib.PurePath(ii).name
                dest_dir = pathlib.PurePath(dest_dir_orig).joinpath(basename)
                print(f"Copying from {pathlib.Path(ii)} to {dest_dir}", end='... ')
                shutil.copytree(ii, dest_dir)
                print('done')
    except FileExistsError:
        print(f"\nError: Destination folder '{dest_dir}' already exists. Remove the folder first. \nBye for now.")
        sys.exit(1)
    except Exception as ee:
        print(f"\nError {ee} while copying files. Aborting the script.")
        sys.exit(1)


def get_archivera_dc():
    """Return a dictionary Archivera to DC"""

    #dc_extra = ['contributors', 'coverage', 'languages', 'relations', 'rights']

    Archivera_DC = {
        'AU.AUCr.Term': 'sources',
        'ACCXAN': 'identifiers',
        'ACCDES': 'descriptions',
        'TI': 'titles',
        'ACCTIMPD': 'dates',
        'ACCBYP.BYPA.NAMESTRANS':'creators',
        'RTYPE.CodeDesc': 'types',
        'EXTT': 'formats',
        'sublc.term': 'subjects',
        'offln.term': 'publishers'
    }

    return Archivera_DC


def get_archivera_bagit():
    """Return a dictionary Archivera to BagIt"""

    Archivera_BagIt = {
        'AU.AUCr.Term': 'Source-Organization',
        'ACCXAN': 'External-Identifier',
        'ACCDES': 'Internal-Sender-Description',
        'TI': 'Title',
        'ACCTIMPD': 'Date-Start',
        'ACCBYP.BYPA.NAMESTRANS':'Record-Creators',
        'RTYPE.CodeDesc': 'Record-Type',
        'EXTT': 'Extend-Size',
        'sublc.term': 'Subjects',
        'offln.term': 'Office'
    }

    return Archivera_BagIt

def archivera_to_bagit(Archivera_BagIt, my_accession, bag_path):
    """Create a BagIt file from an ArchivEra accession"""

    # HACK: I think this block is missing checking for exception...
    # Create a simple BagIt file, and initialize the bag info with creation of the bag.
    my_bag = bagit.make_bag(bag_path, checksums=['sha256'])

    # HACK #2. Probably this part also need to for exception.
    # Update BagIt metadata
    for kk in Archivera_BagIt.keys():
        items_display = len(my_accession['records'][0][kk])
        if items_display > 1:
            my_bag.info[Archivera_BagIt[kk]] = ", ".join(
                [my_accession['records'][0][kk][vv]['display'] for vv in range(items_display)]
            )
        else:
            my_bag.info[Archivera_BagIt[kk]] = my_accession['records'][0][kk][0]['display']
    my_bag.save()

    return ""

def archivera_to_dc(Archivera_DC, my_accession, bag_path):
    """Returns a string with the XML of the accession
    Archivera_DC: dictionary ArchivEra to DC fields
    my_accession: accession details
    bag_path: path where to save the XML file (it's the same path as the BagIt file.)
    """

    # Add the following fields to dictionay, so we have a record compatible
    # with DC core.
    # "contributors, coverage, languages, relations, rights"
    #

    dc_data = dict(
        contributors = ['Contact KAUST'],
        coverage = ['KSA'],
        creators = ['KAUST'],
        dates = ['2002'],
        descriptions = ['Simple Dublin Core generation'],
        formats = ['application/xml'],
        identifiers = ['dublin-core'],
        languages = ['en'],
        publishers = ['KAUST'],
        relations = ['Library'],
        rights = ['MIT'],
        sources = ['Python'],
        subject = ['XML'],
        titles = ['Dublin Core XML'],
        types = ['Software'],    
    )

    # To make record DC-core complaint, create missing fields from ArchivEra 
    # with a generic text.
    #for kk in dc_extra:
    #    dc_data[kk] = ['Contact KAUST']

    for kk in Archivera_DC.keys():
        items_display = len(my_accession['records'][0][kk])
        if items_display > 1:
            dc_data[Archivera_DC[kk]] = [", ".join(
                [my_accession['records'][0][kk][vv]['display'] for vv in range(items_display)]
            )]
        else:
            dc_data[Archivera_DC[kk]] = [my_accession['records'][0][kk][0]['display']]

    dc_xml = simpledc.tostring(dc_data)

    return dc_xml


def get_accession(my_api_conf, my_headers, dt_acc):
    """Return an accession from a query with ArchivEra API."""

    # URL for the API.
    database = 'final'
    template = 'ACC'
    acc_url = f"{my_api_conf['url']}/_rest/databases/{database}/templates/{template}/search-result"

    # Dictionay for querying for accession ('ACC')
    dt_acc['page'] = 0
    dt_acc['page-size'] = 10

    my_accession = requests.get(acc_url, headers=my_headers, params=dt_acc)

    return my_accession.json()

def get_token(api_conf, api_headers):
    """Get the API access token from the 'api_conf' and 'api_headers' dictionaries."""
    my_token = ""
    path_token = '/_oauth/token'

    rr = requests.post(api_conf['url'] + path_token, headers=api_headers,
        data=api_conf).json()

    try:
        my_token = rr['access_token']
    except KeyError as keyError:
        print(f"Error getting access token: {keyError}")
        my_token = ""
    except:
        print("Something went wrong getting the token...")
        my_token = ""

    return my_token

def get_api_headers():
    """Return a dictionary with headers for API requests """
    my_headers = {}
    my_headers['accept'] = 'application/json'
    my_headers['content-type'] = 'application/x-www-form-urlencoded'

    return my_headers

def get_api_conf(my_config):
    """Get API configuration details, and return a dictionary."""

    api_config = configparser.ConfigParser()
    api_config.read(my_config)
    try:

        my_conf = {
            'url': api_config['API']['url'],
            'client_id': api_config['API']['client_id'],
            'grant_type': api_config['API']['grant_type'],
            'username': api_config['API']['username'],
            'database': api_config['API']['database']
        }
    except KeyError as ke:
        print('Key error reading API config')
        print(ke)
        my_conf = {}
    except:
        print("Error reading API config file.")
        my_conf = {}
    return my_conf

def get_api_passwd():
    """Read the password for ArchivEra API from environment variable"""
    api_passwd = ""
    try:
        api_passwd = os.environ['ARCHIVERA_API_PW']
    except KeyError as keyErr:
        print(f"Key error: no password defined. Error {keyErr}")
        api_passwd = ""
    except:
        print("Something went wrong getting API password...")
        api_passwd = ""

    return api_passwd

