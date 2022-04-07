# Automate the digital preservation workflow
# Read metadata from ArchivEra
# Create a "BagIt" file
# The file is uploaded to Preservica

import sys
#import requests
#import bagit
import pathlib
#import shutil
import configparser
import aalib
import click
#from datetime import datetime
from dotenv import load_dotenv
#from dcxml import simpledc

@click.command()
@click.argument('input', type=click.File('r'))
def aaflow(input):
    """Automate digital preservation workflow. 
    
    From INPUT creates a BagIt directory, and DC core complaint file.
    
    \b
    The INPUT contains the 
    * accession number, 
    * collection, 
    * CLAMAV configuration,
    * Droid configuration,
    * Jhove configuration
     """

    config = configparser.ConfigParser()
    config._interpolation = configparser.ExtendedInterpolation()
    config.read(input.name)

    # Adding variables to the antivirus section so we have everything 
    # we need in a single place before calling the function.
    config['CLAMAV'].update({'av_location': config['BAGGER']['source_dir']})
    config['CLAMAV'].update({'av_accession': config['ACCESSION']['accession_id']})
    _ = aalib.av_run(config['CLAMAV'])

    #
    # Define variables for convinience only.
    #
    acc_number = config['ACCESSION']['accession_id']
    bag_path = config['BAGGER']['dest_dir']
    source_list = [ii.strip() for ii in config['BAGGER']['source_dir'].split(',')]

    # Copy source folder(s) to destination (BagIt) folder.
    aalib.copy_src_dirs(source_list, bag_path)

    # load environment variables for 'python-dotenv
    load_dotenv()
    #
    # Define a dictionary with details of the API.
    # TODO: Config file can be defined as command line argument.
    api_config = pathlib.Path('etc/archiveautomation.cfg')
    my_api_conf = aalib.get_api_conf(api_config)

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


    # Run Droid on the "bag" folder
    _ = aalib.droid_run(config['DROID'], bag_path, acc_number)

    # The End
    print('Have a nice day.')
