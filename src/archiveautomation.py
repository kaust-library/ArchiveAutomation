# Automate the digital preservation workflow
# Read metadata from ArchivEra
# Create a "BagIt" file
# The file is uploaded to Preservica

import os

def get_api_passwd():
    """Read the password for ArchivEra API from environment variable"""
    try:
        api_passwd = os.environ['archivera_api_passwd']
    except OSError:
        print("Error reading ArchivEra API password. Is it set as environment variable?")
        api_passwd = ""
    
    return api_passwd

if __name__ == "__main__":
    # As a test print the password from the environment variable.
    print('hello')
    api_pass = get_api_passwd()