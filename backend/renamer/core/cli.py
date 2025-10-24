"""
Punto de entrada CLI para la aplicación Music Renamer.
Maneja los argumentos de línea de comandos y ejecuta las operaciones correspondientes.
"""

import os
import argparse
from constants.info import PARSER_DESCRIPTION
from core.audio_processor import AudioProcessor
from utils.dependencies import check_dependencies
from utils.tools import get_audio_files


class Cli:
    args: argparse.Namespace = None
    processor: AudioProcessor = None
    parser: argparse.ArgumentParser = None

    def __init__(self):
        self.parser = argparse.ArgumentParser(description=PARSER_DESCRIPTION)
        self._init_parser()
        self.args = self.parser.parse_args()
        self.processor = AudioProcessor(
            directory=self.args.directory, acoustid_api_key=self.args.acoustid_key
        )

    def _verify_sync_lyrics(self) -> None:
        use_acoustid = self.args.recognition

        start_lyrics = input(
            "¿Comenzar búsqueda e incrustación de letras? (Y/N): "
        ).lower()
        if start_lyrics == "y":
            lyrics_results = self.processor.process_files(
                use_recognition=use_acoustid, process_lyrics=True
            )

            # Mostrar estadísticas de procesamiento
            if lyrics_results:
                total = len(lyrics_results)
                recognized = sum(
                    1 for f, r in lyrics_results.items() if r.get("recognition", False)
                )
                lyrics_found = sum(
                    1 for f, r in lyrics_results.items() if r.get("lyrics_found", False)
                )
                lyrics_embedded = sum(
                    1
                    for f, r in lyrics_results.items()
                    if r.get("lyrics_embedded", False)
                )

                print("\nResumen:")
                print(f"Total de archivos procesados: {total}")
                if use_acoustid:
                    print(f"Canciones reconocidas: {recognized}")
                print(f"Letras encontradas: {lyrics_found}")
                print(f"Letras incrustadas correctamente: {lyrics_embedded}")

    def _add_covers(self) -> None:
        # Importar el procesador de portadas específico
        try:
            import core.install_covers as install_covers

            print("Ejecutando añadir portadas...")
            install_covers.main()
            return
        except ImportError:
            print("Error al importar el módulo de instalación de portadas.")
            return

    def _init_parser(self) -> None:
        self.parser.add_argument(
            "-d",
            "--directory",
            help="Directorio donde se encuentran los archivos de audio",
            default=".",
        )
        self.parser.add_argument(
            "-l",
            "--lyrics",
            help="Buscar e incrustar letras sincronizadas",
            action="store_true",
        )
        self.parser.add_argument(
            "--recognition",
            help="Usar reconocimiento de audio con AcoustID",
            action="store_true",
        )
        self.parser.add_argument(
            "--acoustid_key",
            help="AcoustID API key (opcional)",
            default="8XaBELgH",
        )
        self.parser.add_argument(
            "--only-covers",
            help="Solo añadir portadas de álbum",
            action="store_true",
        )

    def main(self) -> None:
        """Función principal de la interfaz de línea de comandos."""

        # Verificar dependencias
        print("Verificando dependencias...\n")
        if not check_dependencies():
            return

        directory = os.path.abspath(self.args.directory)
        print(f"Directorio de trabajo: {directory}")

        if not os.path.isdir(directory):
            print(f"El directorio especificado no existe: {directory}")
            input("Presiona Enter para salir...")
            return

        files = get_audio_files(directory)

        if not files:
            print("No se encontraron archivos de audio en este directorio.")
            input("Presiona Enter para salir...")
            return

        print(f"Se encontraron {len(files)} archivos de audio.")

        # Si solo queremos añadir portadas
        if self.args.only_covers:
            print("Modo: Solo añadir portadas de álbum")
            self._add_covers()

        # Verificar si debemos buscar letras sincronizadas
        if self.args.lyrics:
            print(
                "Se utilizará la función de búsqueda e incrustación de letras sincronizadas."
            )
            self._verify_sync_lyrics()

        # Renombrar archivos
        start_rename = input("¿Comenzar renombramiento de archivos? (Y/N): ").lower()
        if start_rename != "y":
            print("Operación de renombramiento cancelada.")
            input("Presiona Enter para salir...")
            return

        changes = self.processor.rename_files()

        if changes:
            keep_changes = input(
                "¿Desea mantener los cambios de nombre? (Y/N): "
            ).lower()
            if keep_changes != "y":
                self.processor.undo_rename(changes)
                print("Los cambios de nombre se han revertido.")
            else:
                print("Los cambios de nombre se han mantenido.")
        else:
            print("No se realizaron cambios de nombre.")

        print("El proceso ha concluido correctamente.")
        input("Presiona Enter para salir...")
