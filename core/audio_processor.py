import os
import re
import platform
import concurrent.futures
import subprocess
from concurrent.futures import ThreadPoolExecutor
from mutagen import File
from mutagen.id3 import ID3, USLT
from mutagen.mp4 import MP4

from utils.tools import get_audio_files


class AudioProcessor:
    """
    Clase principal para procesar archivos de audio: reconocimiento,
    metadatos, letras sincronizadas y portadas de álbum.
    """

    def __init__(self, directory=".", acoustid_api_key="8XaBELgH", max_workers=4):
        """
        Inicializa el procesador de audio.

        Args:
            directory (str): Directorio donde se encuentran los archivos de audio
            acoustid_api_key (str): Clave API para AcoustID
            max_workers (int): Número máximo de trabajadores para procesamiento concurrente
        """

        self.directory = os.path.abspath(directory)
        self.acoustid_api_key = acoustid_api_key
        self.max_workers = max_workers
        self.os_type = platform.system()

    def process_files(self, use_recognition=False, process_lyrics=False):
        """
        Procesa todos los archivos de audio en el directorio.

        Args:
            use_recognition (bool): Si debe usar reconocimiento de audio
            process_lyrics (bool): Si debe procesar letras sincronizadas

        Returns:
            dict: Resultados del procesamiento
        """

        files = self.get_audio_files()
        results = {}

        if not files:
            print("No se encontraron archivos de audio en este directorio.")
            return results

        print(f"Se encontraron {len(files)} archivos de audio.")

        if process_lyrics:
            results = self._process_files_with_lyrics(files, use_recognition)

        return results

    def _process_files_with_lyrics(self, files, use_recognition):
        """
        Procesa múltiples archivos para añadir letras sincronizadas.

        Args:
            files (list): Lista de archivos a procesar
            use_recognition (bool): Si debe usar reconocimiento de audio

        Returns:
            dict: Resultados del procesamiento
        """

        results = {}
        print(f"Procesando {len(files)} archivos para añadir letras sincronizadas...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(
                    self._process_file_with_lyrics,
                    os.path.join(self.directory, file),
                    use_recognition,
                ): file
                for file in files
            }

            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    result = future.result()
                    results[file] = result

                    # Mostrar resumen del resultado
                    if result.get("recognition", False):
                        print(
                            f"[OK] Reconocido: {file} -> {result.get('artist', '')} - {result.get('title', '')}"
                        )

                    if result.get("lyrics_found", False) and result.get(
                        "lyrics_embedded", False
                    ):
                        print(f"[OK] Letras incrustadas: {file}")
                    elif not result.get("lyrics_found", False):
                        print(f"[ERROR] No se encontraron letras para: {file}")
                    elif not result.get("lyrics_embedded", False):
                        print(f"[ERROR] Error al incrustar letras en: {file}")

                except Exception as e:
                    print(f"Error al procesar {file}: {str(e)}")
                    results[file] = {"error": str(e)}

        return results

    def _process_file_with_lyrics(self, file_path, use_recognition):
        """
        Procesa un archivo individual: reconoce la canción y le incrusta letras sincronizadas.

        Args:
            file_path (str): Ruta al archivo de audio
            use_recognition (bool): Si debe usar reconocimiento de audio

        Returns:
            dict: Resultado del procesamiento
        """

        result = {}

        # Obtener metadatos actuales
        audio = File(file_path, easy=True)
        current_artist = (
            audio.get("artist", ["Unknown Artist"])[0] if audio else "Unknown Artist"
        )
        current_title = (
            audio.get("title", ["Unknown Title"])[0] if audio else "Unknown Title"
        )

        # Si se solicitó reconocimiento por AcoustID y los metadatos son insuficientes
        needs_recognition = use_recognition and (
            current_artist == "Unknown Artist" or current_title == "Unknown Title"
        )

        if needs_recognition:
            # Implementar la lógica de reconocimiento aquí
            recognition = self._recognize_song(file_path)

            if recognition["status"]:
                result["recognition"] = True
                result["artist"] = recognition.get("artist", "")
                result["title"] = recognition.get("title", "")
                result["album"] = recognition.get("album", "")
                result["score"] = recognition.get("score", 0)

                # Actualizar metadatos completos del archivo
                print(f"Actualizando metadatos para: {os.path.basename(file_path)}")
                update_success = self._update_audio_metadata(file_path, recognition)
                result["metadata_updated"] = update_success

                if update_success:
                    print(f"[OK] Metadatos actualizados: {os.path.basename(file_path)}")

                    # Mensajes informativos sobre metadatos encontrados
                    metadata_fields = []
                    for field in [
                        "artist",
                        "title",
                        "album",
                        "date",
                        "genre",
                        "tracknumber",
                        "discnumber",
                        "albumartist",
                    ]:
                        if field in recognition:
                            metadata_fields.append(field)

                    if metadata_fields:
                        print(f"  Campos actualizados: {', '.join(metadata_fields)}")

                    if "cover_url" in recognition:
                        print("    Portada del álbum: encontrada e incrustada")
                else:
                    print(
                        f"[ERROR] Error al actualizar metadatos: {os.path.basename(file_path)}"
                    )

                # Usar los metadatos reconocidos para buscar letras
                artist_for_lyrics = recognition.get("artist", "")
                title_for_lyrics = recognition.get("title", "")
            else:
                result["recognition"] = False
                result["recognition_error"] = recognition.get(
                    "message", "Error desconocido"
                )
                artist_for_lyrics = current_artist
                title_for_lyrics = current_title
        else:
            artist_for_lyrics = current_artist
            title_for_lyrics = current_title

        # Buscar letras sincronizadas
        lyrics_result = self._fetch_synced_lyrics(artist_for_lyrics, title_for_lyrics)

        if lyrics_result["status"]:
            result["lyrics_found"] = True
            # Incrustar letras en el archivo
            if self._embed_lyrics(file_path, lyrics_result["lyrics"]):
                result["lyrics_embedded"] = True
            else:
                result["lyrics_embedded"] = False
                result["embed_error"] = "Error al incrustar letras"
        else:
            result["lyrics_found"] = False
            result["lyrics_error"] = lyrics_result.get("message", "Error desconocido")

        return result

    def _recognize_song(self, file_path):
        """
        Reconoce una canción utilizando Chromaprint/AcoustID.

        Args:
            file_path (str): Ruta al archivo de audio

        Returns:
            dict: Información de la canción reconocida
        """

        try:
            print(f"Reconociendo canción: {os.path.basename(file_path)}...")

            # Importar acoustid
            try:
                import acoustid
            except ImportError:
                return {
                    "status": False,
                    "message": "La biblioteca pyacoustid no está instalada. Instálela con 'pip install pyacoustid'",
                }

            # Verificar si fpcalc (Chromaprint) está disponible
            # Primero intentamos usar el fpcalc del directorio actual
            script_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            os_type = self.os_type

            # Determinar el nombre del ejecutable según el sistema operativo
            fpcalc_name = "fpcalc.exe" if os_type == "Windows" else "fpcalc"

            # Buscar fpcalc en el directorio actual
            local_fpcalc = os.path.join(script_dir, fpcalc_name)

            try:
                # Intentar generar la huella acústica usando el fpcalc local o del sistema
                if os.path.exists(local_fpcalc):
                    print(f"Usando fpcalc local: {local_fpcalc}")
                    # Usar directamente el binario local
                    command = [local_fpcalc, "-json", file_path]
                    process = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()

                    if process.returncode != 0:
                        return {
                            "status": False,
                            "message": f"Error al ejecutar fpcalc: {stderr.decode('utf-8', errors='ignore')}",
                        }

                    # Parsear la salida JSON
                    import json

                    result = json.loads(stdout.decode("utf-8", errors="ignore"))
                    duration = result.get("duration", 0)
                    fingerprint = result.get("fingerprint", "")

                    if not fingerprint:
                        return {
                            "status": False,
                            "message": "No se pudo obtener la huella acústica del archivo.",
                        }
                else:
                    # Usar la función estándar de la biblioteca
                    duration, fingerprint = acoustid.fingerprint_file(file_path)
            except Exception as e:
                return {
                    "status": False,
                    "message": f"No se pudo generar la huella acústica: {str(e)}. Asegúrese de que Chromaprint (fpcalc) esté instalado.",
                }

            # Buscar coincidencias en la base de datos de AcoustID con metadatos extendidos
            try:
                # api_key gratuita para uso general, pero se recomienda que los usuarios obtengan su propia clave
                # Solicitamos más metadatos incluyendo tags, genres, y releases para obtener información completa
                results = acoustid.lookup(
                    self.acoustid_api_key,
                    fingerprint,
                    duration,
                    meta="recordings releasegroups releases tracks artists tags genres",
                )

                # Procesar los resultados
                if results and "results" in results and results["results"]:
                    # Obtener el primer resultado con la mayor puntuación
                    best_result = results["results"][0]

                    # Extraer información del resultado
                    if "recordings" in best_result and best_result["recordings"]:
                        recording = best_result["recordings"][0]

                        # Información básica
                        metadata = {
                            "status": True,
                            "score": best_result.get("score", 0),
                            "acoustid": best_result.get("id", ""),
                        }

                        # Extraer artista
                        artists = []
                        if "artists" in recording and recording["artists"]:
                            for artist in recording["artists"]:
                                artists.append(artist["name"])
                            metadata["artist"] = artists[0]
                            metadata["artists"] = artists
                        else:
                            metadata["artist"] = "Artista Desconocido"
                            metadata["artists"] = ["Artista Desconocido"]

                        # Extraer título
                        metadata["title"] = recording.get("title", "Título Desconocido")

                        # Extraer álbum
                        if "releasegroups" in recording and recording["releasegroups"]:
                            releasegroup = recording["releasegroups"][0]
                            metadata["album"] = releasegroup.get(
                                "title", "Álbum Desconocido"
                            )

                            # Artista del álbum
                            if "artists" in releasegroup and releasegroup["artists"]:
                                metadata["albumartist"] = releasegroup["artists"][0][
                                    "name"
                                ]

                            # Tipo de álbum
                            if "type" in releasegroup:
                                metadata["albumtype"] = releasegroup.get("type")

                            # Fecha de lanzamiento
                            if "releases" in recording and recording["releases"]:
                                # Buscar todas las releases de este releasegroup
                                matching_releases = [
                                    r
                                    for r in recording["releases"]
                                    if r.get("releasegroup-id")
                                    == releasegroup.get("id")
                                ]

                                if matching_releases:
                                    release_dates = [
                                        r.get("date")
                                        for r in matching_releases
                                        if r.get("date")
                                    ]
                                    if release_dates:
                                        # Usar la fecha más antigua como fecha del álbum
                                        metadata["date"] = min(release_dates)
                        else:
                            metadata["album"] = "Álbum Desconocido"

                        # Extraer número de pista y disco
                        if "releases" in recording and recording["releases"]:
                            for release in recording["releases"]:
                                if "mediums" in release:
                                    for medium in release["mediums"]:
                                        if "tracks" in medium:
                                            for track in medium["tracks"]:
                                                if track.get("id") == recording.get(
                                                    "id"
                                                ):
                                                    metadata["tracknumber"] = track.get(
                                                        "position", ""
                                                    )
                                                    metadata["discnumber"] = medium.get(
                                                        "position", ""
                                                    )
                                                    metadata["totaltracks"] = (
                                                        medium.get("track-count", "")
                                                    )
                                                    metadata["totaldiscs"] = (
                                                        release.get("medium-count", "")
                                                    )

                        # Extraer género
                        genres = []
                        if "genres" in recording:
                            for genre in recording["genres"]:
                                genres.append(genre["name"])
                            if genres:
                                metadata["genre"] = genres[0]
                                metadata["genres"] = genres

                        # Extraer etiquetas adicionales
                        tags = []
                        if "tags" in recording:
                            for tag in recording["tags"]:
                                tags.append(tag["name"])
                            if tags:
                                metadata["tags"] = tags

                        # Después de extraer los metadatos, buscar la portada del álbum usando un servicio alternativo
                        if "artist" in metadata and "album" in metadata:
                            try:
                                # Importar el gestor de portadas
                                from core.artwork import AlbumArtManager

                                art_manager = AlbumArtManager()

                                cover_url = art_manager.fetch_album_cover(
                                    metadata["artist"], metadata["album"]
                                )
                                if cover_url:
                                    metadata["cover_url"] = cover_url
                            except Exception as e:
                                print(f"Error al buscar portada: {str(e)}")
                                # Si falla la obtención de la portada, continuamos sin ella
                                pass

                        return metadata

                # Si no se encontraron coincidencias
                return {
                    "status": False,
                    "message": "No se encontraron coincidencias en la base de datos",
                }

            except acoustid.WebServiceError as e:
                return {
                    "status": False,
                    "message": f"Error del servicio web AcoustID: {str(e)}",
                }

        except Exception as e:
            return {
                "status": False,
                "message": f"Error al reconocer la canción: {str(e)}",
            }

    def _fetch_synced_lyrics(self, artist, title):
        """
        Busca letras sincronizadas usando la biblioteca syncedlyrics.

        Args:
            artist (str): Nombre del artista
            title (str): Título de la canción

        Returns:
            dict: Letras sincronizadas o mensaje de error
        """
        try:
            print(f"Buscando letras sincronizadas para: {artist} - {title}...")
            import syncedlyrics

            search_term = f"{artist} {title}"
            lrc_content = syncedlyrics.search(search_term)

            if lrc_content and len(lrc_content) > 0:
                return {"status": True, "lyrics": lrc_content}
            else:
                return {
                    "status": False,
                    "message": "No se encontraron letras sincronizadas",
                }

        except ImportError:
            return {
                "status": False,
                "message": "La biblioteca syncedlyrics no está instalada. Instálela con 'pip install syncedlyrics'",
            }
        except Exception as e:
            return {
                "status": False,
                "message": f"Error al buscar letras sincronizadas: {str(e)}",
            }

    def _embed_lyrics(self, file_path, lyrics_content, is_synced=True):
        """
        Incrusta letras en el archivo de audio.

        Args:
            file_path (str): Ruta al archivo de audio
            lyrics_content (str): Contenido de las letras
            is_synced (bool): Si las letras están sincronizadas

        Returns:
            bool: True si se incrustaron correctamente
        """
        try:
            print(f"Incrustando letras en: {os.path.basename(file_path)}...")

            if file_path.lower().endswith(".mp3"):
                # Para archivos MP3 usar ID3
                try:
                    tags = ID3(file_path)
                except Exception:
                    tags = ID3()

                # Eliminar letras existentes
                if len(tags.getall("USLT")) > 0:
                    tags.delall("USLT")

                # Agregar nuevas letras
                tags["USLT::'eng'"] = USLT(
                    encoding=3, lang="eng", desc="Lyrics", text=lyrics_content
                )

                tags.save(file_path)
                return True

            else:
                # Para otros formatos usar mutagen genérico
                audio = File(file_path)
                if audio is not None:
                    if "lyrics" in audio:
                        del audio["lyrics"]

                    audio["lyrics"] = lyrics_content
                    audio.save()
                    return True
                else:
                    return False

        except Exception as e:
            print(f"Error al incrustar letras: {str(e)}")
            return False

    def _update_audio_metadata(self, file_path, metadata):
        """
        Actualiza todos los metadatos disponibles en el archivo de audio.

        Args:
            file_path (str): Ruta al archivo de audio
            metadata (dict): Metadatos a actualizar

        Returns:
            bool: True si se actualizaron correctamente
        """
        try:
            file_ext = os.path.splitext(file_path)[1].lower()

            if file_ext == ".mp3":
                # Para archivos MP3 usar ID3
                try:
                    from mutagen.id3 import (
                        ID3,
                        TIT2,
                        TPE1,
                        TALB,
                        TDRC,
                        TCON,
                        TRCK,
                        TPOS,
                        TPE2,
                        TCOM,
                    )

                    tags = ID3(file_path)
                except Exception as e:
                    print(e)
                    tags = ID3()

                # Actualizar metadatos básicos
                if "title" in metadata:
                    tags["TIT2"] = TIT2(encoding=3, text=metadata["title"])
                if "artist" in metadata:
                    tags["TPE1"] = TPE1(encoding=3, text=metadata["artist"])
                if "album" in metadata:
                    tags["TALB"] = TALB(encoding=3, text=metadata["album"])
                if "date" in metadata:
                    tags["TDRC"] = TDRC(encoding=3, text=metadata["date"])
                if "genre" in metadata:
                    tags["TCON"] = TCON(encoding=3, text=metadata["genre"])
                if "tracknumber" in metadata:
                    track_value = metadata["tracknumber"]
                    if "totaltracks" in metadata:
                        track_value = f"{track_value}/{metadata['totaltracks']}"
                    tags["TRCK"] = TRCK(encoding=3, text=track_value)
                if "discnumber" in metadata:
                    disc_value = metadata["discnumber"]
                    if "totaldiscs" in metadata:
                        disc_value = f"{disc_value}/{metadata['totaldiscs']}"
                    tags["TPOS"] = TPOS(encoding=3, text=disc_value)
                if "albumartist" in metadata:
                    tags["TPE2"] = TPE2(encoding=3, text=metadata["albumartist"])
                if "composer" in metadata:
                    tags["TCOM"] = TCOM(encoding=3, text=metadata["composer"])

                tags.save(file_path)

                # Si hay URL de portada, descargar e incrustar
                if "cover_url" in metadata:
                    # Importar el gestor de portadas
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            elif file_ext in [".flac", ".ogg"]:
                # Para archivos FLAC y OGG
                audio = File(file_path)

                # Mapeo de campos
                field_mapping = {
                    "title": "title",
                    "artist": "artist",
                    "album": "album",
                    "date": "date",
                    "genre": "genre",
                    "tracknumber": "tracknumber",
                    "discnumber": "discnumber",
                    "albumartist": "albumartist",
                    "totaltracks": "totaltracks",
                    "totaldiscs": "totaldiscs",
                    "composer": "composer",
                }

                # Actualizar metadatos
                for meta_key, file_key in field_mapping.items():
                    if meta_key in metadata:
                        audio[file_key] = str(metadata[meta_key])

                audio.save()

                # Si hay URL de portada, descargar e incrustar (solo para FLAC)
                if "cover_url" in metadata and file_ext == ".flac":
                    # Importar el gestor de portadas
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            elif file_ext == ".m4a":
                # Para archivos M4A/AAC
                audio = MP4(file_path)

                # Mapeo de campos para M4A
                field_mapping = {
                    "title": "\xa9nam",
                    "artist": "\xa9ART",
                    "album": "\xa9alb",
                    "date": "\xa9day",
                    "genre": "\xa9gen",
                    "albumartist": "aART",
                    "composer": "\xa9wrt",
                }

                # Actualizar metadatos
                for meta_key, file_key in field_mapping.items():
                    if meta_key in metadata:
                        audio[file_key] = [metadata[meta_key]]

                # Manejar número de pista/disco para M4A
                if "tracknumber" in metadata:
                    try:
                        track = int(metadata["tracknumber"])
                        total = int(metadata.get("totaltracks", 0))
                        if total > 0:
                            audio["trkn"] = [(track, total)]
                        else:
                            audio["trkn"] = [(track, 0)]
                    except (ValueError, TypeError):
                        pass

                if "discnumber" in metadata:
                    try:
                        disc = int(metadata["discnumber"])
                        total = int(metadata.get("totaldiscs", 0))
                        if total > 0:
                            audio["disk"] = [(disc, total)]
                        else:
                            audio["disk"] = [(disc, 0)]
                    except (ValueError, TypeError):
                        pass

                audio.save()

                # Si hay URL de portada, descargar e incrustar
                if "cover_url" in metadata:
                    # Importar el gestor de portadas
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            else:
                # Para otros formatos, usar manejo genérico
                audio = File(file_path)
                if audio:
                    for key, value in metadata.items():
                        if key in [
                            "status",
                            "score",
                            "cover_url",
                            "tags",
                            "genres",
                            "artists",
                            "acoustid",
                        ]:
                            continue  # Saltar metadatos que no son para el archivo
                        if isinstance(value, list):
                            value = value[0] if value else ""
                        audio[key] = value
                    audio.save()
                    return True

                return False

        except Exception as e:
            print(f"Error al actualizar metadatos: {str(e)}")
            return False

    def rename_files(self):
        """
        Renombra los archivos de audio basándose en sus metadatos.
        Si el archivo no tiene los metadatos necesarios (artista o título),
        no se renombra y se muestra un mensaje.

        Returns:
            dict: Cambios realizados (nuevo_nombre: nombre_original)
        """

        files = get_audio_files(directory=self.directory)
        changes = {}

        for file in files:
            try:
                file_path = os.path.join(self.directory, file)
                audio = File(file_path, easy=True)

                # Verificar si existen los metadatos necesarios
                if not audio or not audio.tags:
                    print(
                        f"[ADVERTENCIA] No se renombró {file}: No se encontraron metadatos"
                    )
                    continue

                artist = audio.get("artist", [""])[0]
                title = audio.get("title", [""])[0]

                # Verificar si los metadatos están vacíos o son los valores por defecto
                if (
                    not artist
                    or not title
                    or artist == "Unknown Artist"
                    or title == "Unknown Title"
                ):
                    print(
                        f"[ADVERTENCIA] No se renombró {file}: Faltan metadatos de artista o título"
                    )
                    continue

                # Artista - Título.formato (.mp3, .flac, etc..)
                new_name = f"{artist} - {title}{os.path.splitext(file)[1]}"

                actual_new_name, changed = self._safe_rename(file, new_name)
                if changed:
                    changes[actual_new_name] = file
                    print(f"[OK] Renombrado: {file} -> {actual_new_name}")
            except Exception as e:
                print(f"[ERROR] Error al procesar {file}: {str(e)}")

        if not changes:
            print(
                "\nNo se realizó ningún renombrado. Todos los archivos carecían de metadatos necesarios."
            )

        return changes

    def undo_rename(self, changes: dict):
        files = self.get_audio_files()
        for new_name, old_name in changes.items():
            try:
                # Verificar si el nuevo nombre existe en el directorio
                if new_name in files:
                    print(f"Deshaciendo renombrado: {new_name} -> {old_name}")
                    self._safe_rename(new_name, old_name)
                else:
                    print(
                        f"El archivo {new_name} no existe para deshacer el renombrado."
                    )
            except Exception as e:
                print(f"Error al deshacer renombrado: {str(e)}")

    def _safe_rename(self, old_name, new_name):
        """
        Renombra un archivo de forma segura, evitando conflictos de nombres.

        Args:
            old_name (str): Nombre original del archivo
            new_name (str): Nuevo nombre para el archivo

        Returns:
            tuple: (nombre_final, cambio_realizado)
        """

        old_path = os.path.join(self.directory, old_name)
        new_path = os.path.join(self.directory, new_name)

        if old_path == new_path:
            return old_name, False

        new_name = self._sanitize_filename(new_name)
        new_path = os.path.join(self.directory, new_name)
        base, extension = os.path.splitext(new_name)
        counter = 1

        while os.path.exists(new_path):
            new_name = f"{base} ({counter}){extension}"
            new_path = os.path.join(self.directory, new_name)
            counter += 1

        try:
            os.rename(old_path, new_path)
            return new_name, True
        except OSError as e:
            print(f"No se pudo renombrar '{old_name}' a '{new_name}'. Error: {e}")
            return old_name, False

    def _sanitize_filename(self, filename):
        """
        Sanitiza el nombre del archivo según el sistema operativo.

        Args:
            filename (str): Nombre del archivo a sanitizar

        Returns:
            str: Nombre sanitizado
        """
        if self.os_type == "Windows":
            invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
            sanitized = re.sub(invalid_chars, "", filename)
            forbidden_names = {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                "COM1",
                "COM2",
                "COM3",
                "COM4",
                "COM5",
                "COM6",
                "COM7",
                "COM8",
                "COM9",
                "LPT1",
                "LPT2",
                "LPT3",
                "LPT4",
                "LPT5",
                "LPT6",
                "LPT7",
                "LPT8",
                "LPT9",
            }
            if sanitized.upper() in forbidden_names:
                sanitized = "_" + sanitized
        else:
            sanitized = re.sub(r"/", "-", filename)
            sanitized = sanitized.strip(".")

        sanitized = sanitized.strip()
        max_length = 255
        base, ext = os.path.splitext(sanitized)

        if len(sanitized) > max_length:
            base = base[: max_length - len(ext) - 1]
            sanitized = base + ext

        if not base:
            sanitized = f"audio_file{ext}"

        return sanitized
