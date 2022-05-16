# ArchiveAutomation

Automate the digital preservation workflow. 

The workflow have the following steps:

1. Run the antivirus.
1. Create a _bag_ file from the source folders.
1. Create a XML file Dublin Core.
1. Run Droid for extraction of the metadata.
1. Run JHove as a complement of the metadata.

Next we describe the usage of the script, and the installation of dependencies are below

## Usage

The usage assumes that the repository is already cloned, and we are ready to run the script.

### Update Local Repository

Update the repository to latest version

```
mgarcia@arda:~/Documents/Work/ArchiveAutomation$ git pull
Already up to date.
mgarcia@arda:~/Documents/Work/ArchiveAutomation$ 
```

### Start Virtual Environment

Activate the virtual environment:

```
#
# Windows
#
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> .\venv\Scripts\activate
#
# Linux
#
mgarcia@mordor:~/Documents/Work/ArchiveAutomation$ . venv/bin/activate
```

### Workflow Input File

The takes a single argument: a file describing all information for the workflow. The steps in the workflow are represented by sections of the input file, like ACCESSION, BAGGER, CLAMAV, etc.

### Running the Script

Once the input file is ready, simply call the script with the input file as parameter.

```
(venv) PS C:\Users\garcm0b\Work\ArchiveAutomation> archiveautomation .\my_accession.cfg
Have a nice day.
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$
```

The script prints help message when no input file is provided

```
(venv) mgarcia@arda:~/Documents/Work/ArchiveAutomation$ archiveautomation 
Usage: archiveautomation [OPTIONS] INPUT
Try 'archiveautomation --help' for help.

Error: Missing argument 'INPUT'.
(venv) mgarcia@arda:~/Documents/Work/ArchiveAutomation$ 
```

Or the script can be called with the `--help` parameter

```
venv) mgarcia@arda:~/Documents/Work/ArchiveAutomation$ archiveautomation --help
Usage: archiveautomation [OPTIONS] INPUT

  Automate digital preservation workflow.

  From INPUT creates a BagIt directory, and DC core complaint file.
(...)
```

## Configuration

### Clone the repository

Clone the repository

```
PS C:\Users\garcm0b\Work> git clone https://github.com/kaust-library/ArchiveAutomation.git
```

### Virtual Environment and Dependencies

Create a virtual environment for the project

```
#
# Windows
#
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> python -m venv venv
#
# Linux
#
mgarcia@mordor:~/Documents/Work/ArchiveAutomation$ python3 -m venv venv
```

Setup the environment

```
pip install --editable .
```

This will install all dependencies listed in the section `install_requires` of the `setup.py` file.

### Configuration File

The configuration details for the script are in the file `etc/archiveautomation.cfg.` When cloning the environment, the configuration file will be just a reminder (with an `example` extension) that it needs to be edited with the correct values, and save it as `archiveautomation.cfg.`

### ArchivEra API Password

The API password is handled in 2 ways: declaring it as an environment variable, or via `.env` file. For first case, set password according to your operating system:

```
# Windows
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation\src> $ENV:ARCHIVERA_API_PW='hello_mg'
# Linux
(venv) mgarcia@mordor:~/Documents/Work/ArchiveAutomation/src$ export ARCHIVERA_API_PW="hello"
```

The second way of using the [password is via a `.env`](https://yuthakarn.medium.com/how-to-not-show-credential-in-jupyter-notebook-c349f9278466) in the same directory as the main program. The file is a simple `key=value` pair:

```
(venv) PS C:\Users\garcm0b\Work\ArchiveAutomation> cat .env
ARCHIVERA_API_PW='hello_world'
(venv) PS C:\Users\garcm0b\Work\ArchiveAutomation>
```

## Droid

Installing [`droid`](https://www.nationalarchives.gov.uk/information-management/manage-information/preserving-digital-records/droid/) on linux

```
mgarcia@arda:~/Downloads$ sudo mkdir /usr/share/droid
mgarcia@arda:~/Downloads$ ls -l droid-binary-6.5.2-bin.zip 
-rw-rw-r-- 1 mgarcia mgarcia 50272665 Mar 27 11:23 droid-binary-6.5.2-bin.zip
mgarcia@arda:~/Downloads$ 
mgarcia@arda:~/Downloads$ sudo unzip droid-binary-6.5.2-bin.zip -d /usr/share/droid/
```

To check if it's working, display `droid` help

```
garcia@arda:~/Downloads$ java -jar /usr/share/droid/droid-command-line-6.5.2.jar -h                    
2022-03-27T11:30:30,107  INFO [main] DroidCommandLine:140 - Starting DROID.    
usage: droid [options]                                                                                  
OPTIONS:
(...)
```

Adding resource to a profile and running it

```
/usr/share/droid/droid.sh -a "/home/mgarcia/Pictures/Wallpaper/" -p "wallpaper.droid" 
```

Exporting a profile in `csv` format

```
mgarcia@arda:~$ /usr/share/droid/droid.sh -p wallpaper.droid -e my_wallpaper.csv

mgarcia@arda:~$ more my_wallpaper.csv                                                                            
"ID","PARENT_ID","URI","FILE_PATH","NAME","METHOD","STATUS","SIZE","TYPE","EXT","LAST_MODIFIED","EXTENSION_MISMAT
CH","HASH","FORMAT_COUNT","PUID","MIME_TYPE","FORMAT_NAME","FORMAT_VERSION"                                      
"2","","file:/home/mgarcia/Pictures/Wallpaper/","/home/mgarcia/Pictures/Wallpaper","Wallpaper","","Done","","Fold
er","","2021-10-01T18:26:45","false","","","","","",""    
(...)
```

## Test

Test in `E:\ADMIN\TEST_FULL_WORKFLOW\mg_test`
