from setuptools import setup

setup(
    name='archiveautomation',
    version='0.6',
    py_modules=['archiveautomation'],
    install_requires=[
        'Click',
        'bagit',
        'dcxml',
        'python-dotenv',
        'requests',
    ],
    entry_points={
        'console_scripts':[
            'archiveautomation = archiveautomation:aaflow',
        ],
    },
)
