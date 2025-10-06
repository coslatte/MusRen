from setuptools import setup, find_packages

from constants.info import (
    MUSIC_RENAMER_NAME,
    MUSIC_RENAMER_VERSION,
    MUSIC_RENAMER_DESCRIPTION,
    MUSIC_RENAMER_AUTHOR,
    MUSIC_RENAMER_AUTHOR_EMAIL,
    MUSIC_RENAMER_MAINTAINER,
    MUSIC_RENAMER_MAINTAINER_EMAIL,
)

setup(
    name=MUSIC_RENAMER_NAME,
    version=MUSIC_RENAMER_VERSION,
    description=MUSIC_RENAMER_DESCRIPTION,
    author=MUSIC_RENAMER_AUTHOR,
    author_email=MUSIC_RENAMER_AUTHOR_EMAIL,
    maintainer=MUSIC_RENAMER_MAINTAINER,
    maintainer_email=MUSIC_RENAMER_MAINTAINER_EMAIL,
    packages=find_packages(),
    install_requires=[
        "mutagen",
        "requests",
        "syncedlyrics",
        "pyacoustid",
    ],
    entry_points={
        "console_scripts": [
            "music-renamer=app:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
