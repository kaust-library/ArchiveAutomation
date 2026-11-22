from setuptools import setup

setup(
    name='archiveautomation',
    version='0.7',
    py_modules=['archiveautomation', 'aalib', 'aametadata', 'aavocab', 'aalibnova'],
    install_requires=[
        'Click',
        'bagit',
    ],
    entry_points={
        'console_scripts':[
            'archiveautomation = archiveautomation:aaflow',
            'archiveautomation-vocab = aavocab:main',
        ],
    },
)
