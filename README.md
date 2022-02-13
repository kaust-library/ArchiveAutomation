# ArchiveAutomation

Automate digital archival preservation

## Clone the repository

Clone the repository

```
PS C:\Users\garcm0b\Work> git clone https://github.com/kaust-library/ArchiveAutomation.git
```

## Virtual Environment and Dependencies

Create a virtual environment for the project

```
# Windows
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> python -m venv venv
# Linux
mgarcia@mordor:~/Documents/Work/ArchiveAutomation$ python3 -m venv venv
```

Activate the virtual environment and install extra packages

```
# Windows
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> .\venv\Scripts\activate
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> pip install requests
# Linux
mgarcia@mordor:~/Documents/Work/ArchiveAutomation$ . venv/bin/activate
(venv) mgarcia@mordor:~/Documents/Work/ArchiveAutomation$ pip install requests
```

Creating the `requirements.txt` file with the modules used

```
(venv) PS C:\Users\garcm0b\Work\ArchiveAutomation> pip freeze > requirements.txt
```

In case of a _new_ environment, you can install the requirements by reading the file

```
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$ pip install -r requirements.txt
```

## Configuration File

The configuration details for the script are in the file `etc/archiveautomation.cfg.` When cloning the environment, the configuration file will be just a reminder (with an `example` extension) that it needs to be edited with the correct values, and save it as `archiveautomation.cfg.`

## ArchivEra API Password

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

## Running the Script

The takes 3 arguments: an accession number (ACCXAN), a path to where are the files, and a path to where the BagIt file will be created:

```
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$ python archiveautomation.py 013_002_0026 /home/mgarcia/Documents/boat_trip_pictures /home/mgarcia/Documents/my_bag
Have a nice day.
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$
```
