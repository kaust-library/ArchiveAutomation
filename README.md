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
pip freeze > requirements.txt
```

In case of a _new_ environment, you can install the requirements by reading the file

```
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$ pip install -r requirements.txt
```

## ArchivEra API Password

The API password is read from environment variable. So first set it (for example)

```
# Windows
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation\src> $ENV:ARCHIVERA_API_PW='hello_mg'
# Linux
(venv) mgarcia@mordor:~/Documents/Work/ArchiveAutomation/src$ export ARCHIVERA_API_PW="hello"
```

## Running the Script

The takes 2 arguments: the accession number (ACCXAN), and the path to the files

```
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$ python archiveautomation.py 013_002_0026 /home/mgarcia/Documents/my_bag
Have a nice day.
(venv) mgarcia@wsl2:~/Documents/Work/ArchiveAutomation$
```

