# Automate the digital preservation workflow
# Read metadata from ArchivEra
# Create a "BagIt" file
# The file is uploaded to Preservica

import os
import sys
import requests
import bagit
import pathlib
import shutil
import configparser
from datetime import datetime
from dotenv import load_dotenv
from dcxml import simpledc

def get_archivera_dc():
    """Return a dictionary Archivera to DC"""

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
    my_bag = bagit.make_bag(bag_path, {'Bagging-Date': datetime.now().isoformat()})

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

    dc_data = {}
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

if __name__ == "__main__":
    #
    # TODO: Better handling of parameters, like checking if path exists, etc.
    # Read the accession number that will be retrieved from ArchivEra.
    acc_number = sys.argv[1]
    # Read source directory with files to be archived.
    src_path = pathlib.Path(sys.argv[2])
    # Read path to BagIt (destination) directory.
    bag_path = pathlib.Path(sys.argv[3])

    #
    # Copy the files (tres) from source directory to destination where will be
    # the bag file.
    print(f"Copying files from {src_path} to {bag_path}...")
    shutil.copytree(src_path, bag_path)
    print("done.")

    # load environment variables for 'python-dotenv
    load_dotenv()

    #
    # Define a dictionary with details of the API.
    # TODO: Config file can be defined as command line argument.
    my_config = pathlib.Path('etc/archiveautomation.cfg')
    my_api_conf = get_api_conf(my_config)

    if not my_api_conf:
        print("Not API configuration. Check congfig file. Exiting...")
        sys.exit(1)

    # Define the headers for the API requests
    my_headers = get_api_headers()

    # Read the password from the environment variables. Raise an error if doesn't find it.
    api_pass = get_api_passwd()
    if not api_pass:
        print("Empty password for API. Script can't continue. Exiting...")
        sys.exit(1)
    else:
        my_api_conf['password'] = api_pass

    # Get access token
    my_token = get_token(my_api_conf, my_headers)
    if not my_token:
        print("No access token. Exiting...")
        sys.exit(1)
    else:
        my_headers['authorization'] = 'Bearer ' + my_token

    # print(f"my token is {my_token}")

    # Create a dictionay bagIt to Archivera
    Archivera_BagIt = get_archivera_bagit()

    # Read accession by accession number (ACCXAN)
    #acc_number = '013_001_0003'
    dt_acc = {}
    dt_acc['command'] = f"ACCXAN=='{acc_number}'"
    dt_acc['fields'] = ",".join([kk for kk in Archivera_BagIt.keys()])

    my_accession = get_accession(my_api_conf, my_headers, dt_acc)

    # Create BagIt file
    my_bag = archivera_to_bagit(Archivera_BagIt, my_accession, bag_path)

    # Save to accession in DC format
    Archivera_DC = get_archivera_dc()

    dc_text = archivera_to_dc(Archivera_DC, my_accession, bag_path)

    dc_file = f"{bag_path}/bag-info.xml"

    with open(dc_file, 'w') as ff_dc:
        ff_dc.write(dc_text)

    # The End
    print('Have a nice day.')
