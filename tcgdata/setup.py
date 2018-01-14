try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

    config = {
        'name': 'tcgdata',
        'description': 'Tools for creating, manipulating, and querying a database of Pokémon crds',
        'author': 'Justin Peavey',
        'url': 'URL to get it at.',
        'download_url': 'Where to download it.',
        'author_email': 'My email.',
        'version': '0.1',
        'scripts': []
    }

    setup(**config)
