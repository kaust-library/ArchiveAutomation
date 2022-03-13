# Automate the digital preservation workflow
# Read metadata from ArchivEra
# Create a "BagIt" file
# The file is uploaded to Preservica

import sys
import requests
import bagit
import pathlib
import shutil
import configparser
import aalib
from datetime import datetime
from dotenv import load_dotenv
from dcxml import simpledc

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
    try:
        print(f"Copying files from '{src_path}' to '{bag_path}'...")
        shutil.copytree(src_path, bag_path)
        print("done.")
    except FileExistsError:
        print(f"\nError: Destination folder '{bag_path}' already exists. Remove the folder first. \nBye for now.")
        sys.exit(1)
    except Exception as ee:
        print(f"\nError {ee} while copying files. Aborting the script.")
        sys.exit(1)

    # load environment variables for 'python-dotenv
    load_dotenv()

    #
    # Define a dictionary with details of the API.
    # TODO: Config file can be defined as command line argument.
    my_config = pathlib.Path('etc/archiveautomation.cfg')
    my_api_conf = aalib.get_api_conf(my_config)

    if not my_api_conf:
        print("Not API configuration. Check congfig file. Exiting...")
        sys.exit(1)

    # Define the headers for the API requests
    my_headers = aalib.get_api_headers()

    # Read the password from the environment variables. Raise an error if doesn't find it.
    api_pass = aalib.get_api_passwd()
    if not api_pass:
        print("Empty password for API. Script can't continue. Exiting...")
        sys.exit(1)
    else:
        my_api_conf['password'] = api_pass

    # Get access token
    my_token = aalib.get_token(my_api_conf, my_headers)
    if not my_token:
        print("No access token. Exiting...")
        sys.exit(1)
    else:
        my_headers['authorization'] = 'Bearer ' + my_token

    # print(f"my token is {my_token}")

    # Create a dictionay bagIt to Archivera
    Archivera_BagIt = aalib.get_archivera_bagit()

    # Read accession by accession number (ACCXAN)
    #acc_number = '013_001_0003'
    dt_acc = {}
    dt_acc['command'] = f"ACCXAN=='{acc_number}'"
    dt_acc['fields'] = ",".join([kk for kk in Archivera_BagIt.keys()])

    my_accession = aalib.get_accession(my_api_conf, my_headers, dt_acc)

    # Create BagIt file
    my_bag = aalib.archivera_to_bagit(Archivera_BagIt, my_accession, bag_path)

    # Save to accession in DC format
    Archivera_DC = aalib.get_archivera_dc()

    dc_text = aalib.archivera_to_dc(Archivera_DC, my_accession, bag_path)

    dc_file = f"{bag_path}/bag-info.xml"

    with open(dc_file, 'w') as ff_dc:
        ff_dc.write(dc_text)

    # The End
    print('Have a nice day.')
