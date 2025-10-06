import os
from constants.values import AUDIO_EXTENSIONS


def get_audio_files(directory):
    """
    Obtiene todos los archivos de audio en el directorio especificado.

    Returns:
        list: Lista de nombres de archivos de audio
    """

    audio_extensions = AUDIO_EXTENSIONS
    return [f for f in os.listdir(directory) if f.lower().endswith(audio_extensions)]
