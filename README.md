# ArchiveAutomation

Automate digital archival preservation

## Virtual Environment and Dependencies

Create a virtual environment for the project

```
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> python -m venv venv
```

Activate the virtual environment and install extra packages

```
PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> .\venv\Scripts\activate
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation> pip install requests
```

## ArchivEra API Password

The API password is read from environment variable. So first set it (for example)

```
(venv) PS C:\Users\garcm0b\OneDrive - KAUST\Documents\Work\ArchiveAutomation\src> $ENV:api_passwd='hello_mg'
```
