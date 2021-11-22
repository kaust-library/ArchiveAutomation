# Automate the digital preservation workflow
# Read metadata from ArchivEra
# Create a "BagIt" file
# The file is uploaded to Preservica

import os
import sys
import requests
import bagit
import pathlib
from datetime import datetime

def archivera_to_bagit(BagIt_to_Archivera, my_accession, bag_path):
    """Create a BagIt file from an ArchivEra accession"""

    # HACK: I think this block is missing checking for exception...
    # Create a simple BagIt file, and initialize the bag info with creation of the bag.
    my_bag = bagit.make_bag(bag_path, {'Bagging-Date': datetime.now().isoformat()})

    # HACK #2. Probably this part also need to for exception.
    # Update BagIt metadata
    for kk in BagIt_to_Archivera.keys():
        my_bag.info[BagIt_to_Archivera[kk]] = my_accession['records'][0][kk][0]['display']
    my_bag.save()

    return ""

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

def get_api_conf():
    """Get API configuration details, and return a dictionary."""

    # TODO: move the configuration to a file so the end user can edit it.
    my_conf = {}
    my_conf['url'] = 'https://7050.sydneyplus.com/public'
    my_conf['client_id'] = 'apitest'
    my_conf['grant_type'] = 'password'
    my_conf['username'] = 'APIUser'
    my_conf['database'] = 'final'

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
    # Read path to files (directory)
    bag_path = pathlib.Path(sys.argv[2])

    #
    # Define a dictionary with details of the API.
    my_api_conf = get_api_conf()

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
    BagIt_to_Archivera = {
        'AU.AUCr.Term': 'Source-Organization',
        'ACCXAN': 'External-Identifier',
        'ACCDES': 'Internal-Sender-Description',
        'TI': 'Title',
        'ACCTIMPD': 'Date-Start',
        'ACCBYP.BYPA.NAMESTRANS':'Record-Creators',
        'RTYPE.CodeDesc': 'Record-Type'
    }

    # Read accession by accession number (ACCXAN)
    #acc_number = '013_001_0003'
    dt_acc = {}
    dt_acc['command'] = f"ACCXAN=='{acc_number}'"
    dt_acc['fields'] = ",".join([kk for kk in BagIt_to_Archivera.keys()])

    my_accession = get_accession(my_api_conf, my_headers, dt_acc)

    # Create BagIt file
    my_bag = archivera_to_bagit(BagIt_to_Archivera, my_accession, bag_path)

    # The End
    print('Have a nice day.')