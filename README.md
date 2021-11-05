# ArchiveAutomation

Automate digital archival preservation

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

## ArchivEra API Password

The API password is read from environment variable. So first set it (for example)

```
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation\src> $ENV:ARCHIVERA_API_PW='hello_mg'
(venv) mgarcia@mordor:~/Documents/Work/ArchiveAutomation/src$ export ARCHIVERA_API_PW="hello"
```
