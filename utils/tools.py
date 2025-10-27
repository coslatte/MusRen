import os
from constants.settings import AUDIO_EXTENSIONS


def get_audio_files(directory):
    """
    Gets all audio files in the specified directory.

    Returns:
        list: List of audio file names
    """

    audio_extensions = AUDIO_EXTENSIONS
    return [f for f in os.listdir(directory) if f.lower().endswith(audio_extensions)]
