import os
import re
import platform
import concurrent.futures
import subprocess

from utils.tools import (
    check_internet_connection,
    get_audio_files,
    suppress_noisy_loggers,
)

try:
    from core.shazam_processor import ShazamProcessor
except ImportError:
    ShazamProcessor = None


class AudioProcessor:
    """
    Main class for processing audio files: recognition, metadata, synchronized lyrics and album covers.
    """

    def __init__(
        self,
        directory=".",
        acoustid_api_key=None,
        max_workers=4,
        recursive=False,
        use_shazam=False,
    ):
        """
        Initializes the audio processor.

        Args:
            directory (str): Directorio donde se encuentran los archivos de audio
            acoustid_api_key (str): Clave API para AcoustID
            max_workers (int): Número máximo de trabajadores para procesamiento concurrente
        """

        self.directory = os.path.abspath(directory)
        # Si se pasa None, usar la clave por defecto
        self.acoustid_api_key = acoustid_api_key or os.environ.get("ACOUSTID_API_KEY")
        self.max_workers = max_workers
        self.recursive = recursive
        self.os_type = platform.system()
        self.use_shazam = use_shazam
        self.shazam_processor = None

        if self.use_shazam:
            # Reducir concurrencia para Shazam para evitar saturación y timeouts
            # ShazamIO es pesado y sensible a múltiples peticiones simultáneas
            self.max_workers = min(max_workers, 2)

            if ShazamProcessor:
                try:
                    self.shazam_processor = ShazamProcessor()
                except Exception as e:
                    print(f"Error inicializando Shazam: {e}")
                    self.use_shazam = False
            else:
                print("Advertencia: ShazamProcessor no disponible (instala shazamio).")
                self.use_shazam = False

    def process_files(
        self,
        use_recognition=False,
        process_lyrics=False,
        fetch_covers=False,
        progress_callback=None,
    ):
        """
        Processes all audio files in the directory.

        Args:
            use_recognition (bool): Si debe usar reconocimiento de audio
            process_lyrics (bool): Si debe procesar letras sincronizadas

        Returns:
            dict: Processing results
        """

        files = get_audio_files(self.directory, recursive=self.recursive)
        results = {}

        if not files:
            return results

        if process_lyrics or use_recognition or fetch_covers:
            results = self._process_files_batch(
                files, use_recognition, process_lyrics, fetch_covers, progress_callback
            )

        return results

    def _process_files_batch(
        self,
        files,
        use_recognition,
        process_lyrics,
        fetch_covers,
        progress_callback=None,
    ):
        """
        Procesa múltiples archivos para añadir letras sincronizadas.

        Args:
            files (list): Lista de archivos a procesar
            use_recognition (bool): Si debe usar reconocimiento de audio

        Returns:
            dict: Processing results
        """

        results = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_file = {
                executor.submit(
                    self._process_file,
                    # file is already absolute path from get_audio_files
                    file,
                    use_recognition,
                    process_lyrics,
                    fetch_covers,
                ): file
                for file in files
            }

            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    result = future.result()
                    results[file] = result
                    if progress_callback:
                        progress_callback(file, result)

                except Exception as e:
                    error_result = {"error": str(e)}
                    results[file] = error_result
                    if progress_callback:
                        progress_callback(file, error_result)

        return results

    def _process_file(
        self, file_path, use_recognition, process_lyrics, fetch_covers=False
    ):
        """
        Processes an individual file: recognizes the song and embeds synchronized lyrics.

        Args:
            file_path (str): Path to the audio file
            use_recognition (bool): Whether to use audio recognition
            process_lyrics (bool): Whether to process synchronized lyrics
            fetch_covers (bool): Whether to fetch and download covers

        Returns:
            dict: Processing result
        """

        result = {}

        # Get current metadata
        try:
            from mutagen import File  # type: ignore[attr-defined]
        except ImportError:
            return {
                "status": False,
                "message": "The mutagen library is not installed. Install it with 'pip install mutagen'.",
            }

        audio = File(file_path, easy=True)
        current_artist = (
            audio.get("artist", ["Unknown Artist"])[0] if audio else "Unknown Artist"
        )
        current_title = (
            audio.get("title", ["Unknown Title"])[0] if audio else "Unknown Title"
        )
        current_album = (
            audio.get("album", ["Unknown Album"])[0] if audio else "Unknown Album"
        )

        # Initialize variables for metadata tracking
        final_artist = current_artist
        final_title = current_title
        final_album = current_album
        metadata_to_update = {}
        should_update_metadata = False
        artist_for_lyrics = current_artist
        title_for_lyrics = current_title

        # If recognition is requested
        if use_recognition:
            # Use Shazam if configured and available
            if self.use_shazam and self.shazam_processor:
                recognition = self.shazam_processor.recognize(file_path)
            else:
                recognition = self._recognize_song(file_path)

            if recognition["status"]:
                result["recognition"] = True
                result["artist"] = recognition.get("artist", "")
                result["title"] = recognition.get("title", "")
                result["album"] = recognition.get("album", "")
                result["score"] = recognition.get("score", 0)

                final_artist = result["artist"]
                final_title = result["title"]
                final_album = result["album"]
                artist_for_lyrics = final_artist
                title_for_lyrics = final_title

                metadata_to_update.update(recognition)
                should_update_metadata = True
            else:
                result["recognition"] = False
                result["recognition_error"] = recognition.get(
                    "message", "Unknown error"
                )
                # If recognition fails, don't update metadata (not even covers)
                should_update_metadata = False

        # If covers were requested, search and add to metadata
        # Only if recognition was NOT requested (use current tags)
        # Or if it was requested AND succeeded (use recognized tags)
        if fetch_covers:
            # Check if artist is "Unknown" in various languages/formats
            unknown_variants = ["unknown artist", "artista desconocido", "unknown"]
            is_unknown = any(v in str(final_artist).lower() for v in unknown_variants)

            if (not use_recognition) or (
                use_recognition and result.get("recognition", False)
            ):
                if final_artist and final_album and not is_unknown:
                    try:
                        from core.artwork import AlbumArtManager

                        art_manager = AlbumArtManager()
                        cover_url = art_manager.fetch_album_cover(
                            final_artist, final_album
                        )
                        if cover_url:
                            metadata_to_update["cover_url"] = cover_url
                            should_update_metadata = True
                    except Exception as e:
                        result["cover_error"] = str(e)

        # Update complete file metadata if needed
        if should_update_metadata:
            update_result = self._update_audio_metadata(file_path, metadata_to_update)
            # Handle both tuple and bool return types
            if isinstance(update_result, tuple):
                update_success, update_error = update_result
            else:
                update_success = update_result
                update_error = ""
            result["metadata_updated"] = update_success
            if not update_success and update_error:
                result["metadata_error"] = update_error

        # Search for synchronized lyrics only if requested
        if process_lyrics:
            lyrics_result = self._fetch_synced_lyrics(
                artist_for_lyrics, title_for_lyrics
            )

            if lyrics_result["status"]:
                result["lyrics_found"] = True
                # Embed lyrics in the file
                if self._embed_lyrics(file_path, lyrics_result["lyrics"]):
                    result["lyrics_embedded"] = True
                else:
                    result["lyrics_embedded"] = False
                    result["embed_error"] = "Error embedding lyrics"
            else:
                result["lyrics_found"] = False
                result["lyrics_error"] = lyrics_result.get("message", "Unknown error")

        return result

    def _recognize_song(self, file_path):
        """
        Recognizes a song using Chromaprint/AcoustID.

        Args:
            file_path (str): Path to the audio file

        Returns:
            dict: Recognized song information
        """

        if not check_internet_connection():
            return {
                "status": False,
                "message": "No internet connection. Skipping recognition.",
            }

        try:
            # Song recognition (status messages in CLI)

            # Import acoustid
            try:
                import acoustid
            except ImportError:
                return {
                    "status": False,
                    "message": "The pyacoustid library is not installed. Install it with 'pip install pyacoustid'",
                }

            # Verificar si fpcalc (Chromaprint) está disponible
            # Primero intentamos usar el fpcalc del directorio del proyecto
            # __file__ = core/audio_processor.py
            # dirname(__file__) = core/
            # dirname(dirname(__file__)) = MusRen (project root)
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            os_type = self.os_type

            # Determine executable name based on operating system
            fpcalc_name = "fpcalc.exe" if os_type == "Windows" else "fpcalc"

            # Buscar fpcalc en el directorio actual
            local_fpcalc = os.path.join(script_dir, fpcalc_name)
            if not os.path.exists(local_fpcalc):
                local_fpcalc = os.path.join(os.getcwd(), fpcalc_name)

            try:
                # Try to generate acoustic fingerprint using local or system fpcalc
                if os.path.exists(local_fpcalc):
                    # Usar directamente el binario local
                    command = [local_fpcalc, "-json", file_path]
                    process = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    try:
                        stdout, stderr = process.communicate(timeout=60)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        return {
                            "status": False,
                            "message": "Tiempo de espera agotado al ejecutar fpcalc.",
                        }

                    if process.returncode != 0:
                        return {
                            "status": False,
                            "message": f"Error executing fpcalc: {stderr.decode('utf-8', errors='ignore')}",
                        }

                    # Parse JSON output
                    import json

                    result = json.loads(stdout.decode("utf-8", errors="ignore"))
                    duration = result.get("duration", 0)
                    fingerprint = result.get("fingerprint", "")

                    if not fingerprint:
                        return {
                            "status": False,
                            "message": "Could not obtain the acoustic fingerprint of the file.",
                        }
                else:
                    # Use standard library function
                    duration, fingerprint = acoustid.fingerprint_file(file_path)
            except Exception as e:
                return {
                    "status": False,
                    "message": f"Could not generate acoustic fingerprint: {str(e)}. Make sure Chromaprint (fpcalc) is installed.",
                }

            # Search for matches in AcoustID database with extended metadata
            try:
                # api_key gratuita para uso general, pero se recomienda que los usuarios obtengan su propia clave
                # Solicitamos más metadatos incluyendo tags, genres, y releases para obtener información completa
                results = acoustid.lookup(
                    self.acoustid_api_key,
                    fingerprint,
                    duration,
                    meta="recordings releasegroups releases tracks artists tags genres",
                )

                # Check for API errors in the response
                if results and results.get("status") == "error":
                    error_info = results.get("error", {})
                    error_message = error_info.get("message", "Unknown API error")
                    error_code = error_info.get("code", "")
                    if error_code == 4 or "invalid" in error_message.lower():
                        return {
                            "status": False,
                            "message": "Invalid AcoustID API key. Please get a valid API key at https://acoustid.org/login and use it with the -k option.",
                        }
                    return {
                        "status": False,
                        "message": f"AcoustID API error: {error_message}",
                    }

                # Process the results
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

                        # Extract title
                        metadata["title"] = recording.get("title", "Unknown Title")

                        # Extract album
                        if "releasegroups" in recording and recording["releasegroups"]:
                            releasegroup = recording["releasegroups"][0]
                            metadata["album"] = releasegroup.get(
                                "title", "Unknown Album"
                            )

                            # Album artist
                            if "artists" in releasegroup and releasegroup["artists"]:
                                metadata["albumartist"] = releasegroup["artists"][0][
                                    "name"
                                ]

                            # Album type
                            if "type" in releasegroup:
                                metadata["albumtype"] = releasegroup.get("type")

                            # Release date
                            if "releases" in recording and recording["releases"]:
                                # Search for all releases of this releasegroup
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
                                        # Use the earliest date as album date
                                        metadata["date"] = min(release_dates)
                        else:
                            metadata["album"] = "Unknown Album"

                        # Extract track and disc number
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

                        # Extract genre
                        genres = []
                        if "genres" in recording:
                            for genre in recording["genres"]:
                                genres.append(genre["name"])
                            if genres:
                                metadata["genre"] = genres[0]
                                metadata["genres"] = genres

                        # Extract additional tags
                        tags = []
                        if "tags" in recording:
                            for tag in recording["tags"]:
                                tags.append(tag["name"])
                            if tags:
                                metadata["tags"] = tags

                        # After extracting metadata, search for album cover using an alternative service
                        if "artist" in metadata and "album" in metadata:
                            try:
                                # Import album art manager
                                from core.artwork import AlbumArtManager

                                art_manager = AlbumArtManager()

                                cover_url = art_manager.fetch_album_cover(
                                    metadata["artist"], metadata["album"]
                                )
                                if cover_url:
                                    metadata["cover_url"] = cover_url
                            except Exception:
                                # If cover fetching fails, continue without it
                                pass

                        return metadata

                # If no matches were found
                return {
                    "status": False,
                    "message": "No matches found in the database",
                }

            except acoustid.WebServiceError as e:
                try:
                    key = self.acoustid_api_key or ""
                except Exception:
                    key = ""
                if key:
                    if len(key) > 8:
                        masked_key = f"{key[:4]}...{key[-4:]}"
                    else:
                        masked_key = f"{key[:2]}...{key[-2:]}"
                else:
                    masked_key = "(none)"
                message = (
                    f"AcoustID web service error: {str(e)} (Key used: {masked_key})"
                )
                if "invalid API key" in str(e):
                    message += ". Please get a valid API Key at https://acoustid.org/login and use it with the -k option"
                return {
                    "status": False,
                    "message": f"AcoustID web service error: {str(e)}",
                }

        except Exception as e:
            return {
                "status": False,
                "message": f"Error recognizing the song: {str(e)}",
            }

    def _fetch_synced_lyrics(self, artist, title):
        """
        Searches for synchronized lyrics using the syncedlyrics library.

        Args:
            artist (str): Artist name
            title (str): Song title

        Returns:
            dict: Synchronized lyrics or error message
        """
        if not check_internet_connection():
            return {
                "status": False,
                "message": "No internet connection. Skipping lyrics search.",
            }

        try:
            suppress_noisy_loggers()
            import syncedlyrics

            search_term = f"{artist} {title}"
            lrc_content = syncedlyrics.search(search_term)
            suppress_noisy_loggers()

            if lrc_content and len(lrc_content) > 0:
                return {"status": True, "lyrics": lrc_content}
            else:
                return {
                    "status": False,
                    "message": "No synchronized lyrics found",
                }

        except ImportError:
            return {
                "status": False,
                "message": "The syncedlyrics library is not installed. Install it with 'pip install syncedlyrics'",
            }
        except Exception as e:
            return {
                "status": False,
                "message": f"Error searching for synchronized lyrics: {str(e)}",
            }

    def _embed_lyrics(self, file_path, lyrics_content, is_synced=True):
        """
        Embeds lyrics in the audio file.

        Args:
            file_path (str): Path to the audio file
            lyrics_content (str): Lyrics content
            is_synced (bool): Whether lyrics are synchronized

        Returns:
            bool: True if embedded successfully
        """
        try:
            # Embedding lyrics (status messages in CLI)

            if file_path.lower().endswith(".mp3"):
                # For MP3 files use ID3
                try:
                    from mutagen.id3 import ID3, USLT  # type: ignore[attr-defined]
                except ImportError:
                    return False

                try:
                    tags = ID3(file_path)
                except Exception:
                    tags = ID3()

                # Remove existing lyrics
                if len(tags.getall("USLT")) > 0:
                    tags.delall("USLT")

                # Add new lyrics
                tags["USLT::'eng'"] = USLT(
                    encoding=1, lang="eng", desc="Lyrics", text=lyrics_content
                )

                tags.save(file_path)
                return True

            else:
                # For other formats use generic mutagen
                try:
                    from mutagen import File  # type: ignore[attr-defined]
                except ImportError:
                    return False

                audio = File(file_path)
                if audio is not None:
                    if "lyrics" in audio:
                        del audio["lyrics"]

                    audio["lyrics"] = lyrics_content
                    audio.save()
                    return True
                else:
                    return False

        except Exception:
            return False

    def _update_audio_metadata(self, file_path, metadata):
        """
        Updates all available metadata in the audio file.

        Args:
            file_path (str): Path to the audio file
            metadata (dict): Metadata to update

        Returns:
            tuple: (success: bool, error: str) or bool for backward compatibility
        """
        try:
            file_ext = os.path.splitext(file_path)[1].lower()

            if file_ext == ".mp3":
                # For MP3 files use ID3
                try:
                    from mutagen.id3 import ID3
                    from mutagen.id3._frames import (
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
                except ImportError:
                    return False, "mutagen.id3 not available"

                try:
                    tags = ID3(file_path)
                except Exception:
                    tags = ID3()

                changed = False

                def update_tag(frame_id, frame_cls, value):
                    nonlocal changed
                    # Force update to ensure correct encoding (UTF-16 for Windows compatibility)
                    tags[frame_id] = frame_cls(encoding=1, text=str(value))
                    changed = True

                # Update basic metadata
                if "title" in metadata:
                    update_tag("TIT2", TIT2, metadata["title"])
                if "artist" in metadata:
                    update_tag("TPE1", TPE1, metadata["artist"])
                if "album" in metadata:
                    update_tag("TALB", TALB, metadata["album"])
                if "date" in metadata:
                    update_tag("TDRC", TDRC, metadata["date"])
                if "genre" in metadata:
                    update_tag("TCON", TCON, metadata["genre"])
                if "tracknumber" in metadata:
                    track_value = metadata["tracknumber"]
                    if "totaltracks" in metadata:
                        track_value = f"{track_value}/{metadata['totaltracks']}"
                    update_tag("TRCK", TRCK, track_value)
                if "discnumber" in metadata:
                    disc_value = metadata["discnumber"]
                    if "totaldiscs" in metadata:
                        disc_value = f"{disc_value}/{metadata['totaldiscs']}"
                    update_tag("TPOS", TPOS, disc_value)
                if "albumartist" in metadata:
                    update_tag("TPE2", TPE2, metadata["albumartist"])
                if "composer" in metadata:
                    update_tag("TCOM", TCOM, metadata["composer"])

                if changed:
                    tags.save(file_path, v2_version=3)

                # If there is a cover URL, download and embed
                if "cover_url" in metadata:
                    # Import album art manager
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True, ""

            elif file_ext in [".flac", ".ogg"]:
                # For FLAC and OGG files
                try:
                    from mutagen import File  # type: ignore[attr-defined]
                except ImportError:
                    return False, "Mutagen not installed"

                audio = File(file_path)
                if audio is None:
                    return False, "Could not open audio file"
                changed = False

                # Field mapping
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

                # Update metadata
                for meta_key, file_key in field_mapping.items():
                    if meta_key in metadata:
                        new_val = str(metadata[meta_key])
                        current_val = audio.get(file_key, [""])[0]
                        if current_val != new_val:
                            audio[file_key] = new_val
                            changed = True

                if changed:
                    audio.save()

                # If there is a cover URL, download and embed (only for FLAC)
                if "cover_url" in metadata and file_ext == ".flac":
                    # Import album art manager
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True, ""

            elif file_ext == ".m4a":
                # For M4A/AAC files
                try:
                    from mutagen.mp4 import MP4
                except ImportError:
                    return False, "Mutagen not installed"

                audio = MP4(file_path)

                # Field mapping for M4A
                field_mapping = {
                    "title": "\xa9nam",
                    "artist": "\xa9ART",
                    "album": "\xa9alb",
                    "date": "\xa9day",
                    "genre": "\xa9gen",
                    "albumartist": "aART",
                    "composer": "\xa9wrt",
                }

                changed = False

                # Update metadata
                for meta_key, file_key in field_mapping.items():
                    if meta_key in metadata:
                        audio[file_key] = [metadata[meta_key]]
                        changed = True

                # Handle track/disc number for M4A
                if "tracknumber" in metadata:
                    try:
                        trkn = int(metadata["tracknumber"])
                        total = int(metadata.get("totaltracks", 0))
                        audio["trkn"] = [(trkn, total)]
                        changed = True
                    except ValueError:
                        pass

                if "discnumber" in metadata:
                    try:
                        disk = int(metadata["discnumber"])
                        total = int(metadata.get("totaldiscs", 0))
                        audio["disk"] = [(disk, total)]
                        changed = True
                    except ValueError:
                        pass

                if changed:
                    audio.save()

                # If there is a cover URL, download and embed
                if "cover_url" in metadata:
                    # Import album art manager
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            else:
                # For other formats, use generic handling
                try:
                    from mutagen._file import File
                except ImportError:
                    return False

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
                            continue  # Skip metadata that is not for the file
                        if isinstance(value, list):
                            value = value[0] if value else ""
                        audio[key] = value
                    audio.save()
                    return True

                return False

        except Exception:
            return False

    def rename_files(
        self,
        progress_callback=None,
        rename_format="1",
        scan_callback=None,
    ):
        """
        Renames audio files based on their metadata.
        If the file doesn't have the necessary metadata (artist or title),
        it is not renamed and a message is shown.

        For files that belong to an album (more than 2 tracks with same album),
        the track number is prepended: "NN - Artist - Title.ext"

        Args:
            progress_callback (callable): Function to call upon completing each file
            rename_format (str): Format for renaming:
                "1" = artist - title
                "2" = title
                "3" = track_number - artist - title (if album, otherwise artist - title)
            scan_callback (callable): Optional callback for scan phase progress

        Returns:
            dict: Changes made (new_name: original_name)
        """

        files = get_audio_files(directory=self.directory, recursive=self.recursive)
        changes = {}

        try:
            from mutagen import File  # type: ignore[attr-defined]
        except ImportError:
            for file in files:
                if progress_callback:
                    progress_callback(
                        file, {"status": False, "error": "Mutagen missing"}
                    )
            return changes

        # First pass: collect album info and track numbers
        album_counts = {}
        file_metadata = {}

        for file in files:
            if scan_callback:
                scan_callback(file)
            file_path = file
            try:
                audio = File(file_path, easy=True)
                if not audio or not audio.tags:
                    file_metadata[file] = None
                    continue

                artist = audio.get("artist", [""])[0]
                title = audio.get("title", [""])[0]
                album = audio.get("album", [""])[0]
                tracknumber = audio.get("tracknumber", [""])[0]

                if (
                    not artist
                    or not title
                    or artist == "Unknown Artist"
                    or title == "Unknown Title"
                ):
                    file_metadata[file] = None
                    continue

                album_label = (
                    album.strip() if album and album.strip() else "__no_album__"
                )
                album_counts[album_label] = album_counts.get(album_label, 0) + 1
                file_metadata[file] = {
                    "artist": artist,
                    "title": title,
                    "album": album_label,
                    "tracknumber": tracknumber,
                }
            except Exception:
                file_metadata[file] = None

        # Second pass: rename
        for file in files:
            try:
                meta = file_metadata.get(file)
                if meta is None:
                    if progress_callback:
                        progress_callback(
                            file,
                            {
                                "status": False,
                                "skipped": True,
                                "reason": "Missing metadata",
                            },
                        )
                    continue

                artist = meta["artist"]
                title = meta["title"]
                album = meta["album"]
                tracknumber = meta["tracknumber"]
                is_album = album != "__no_album__" and album_counts.get(album, 0) > 2
                ext = os.path.splitext(file)[1]

                if rename_format == "2":
                    new_name = f"{title}{ext}"
                elif rename_format == "3" and is_album and tracknumber:
                    try:
                        track_num = int(tracknumber.split("/")[0].split(".")[0])
                        new_name = f"{track_num:02d} - {artist} - {title}{ext}"
                    except (ValueError, IndexError):
                        new_name = f"{artist} - {title}{ext}"
                else:
                    new_name = f"{artist} - {title}{ext}"

                actual_new_path, changed, error = self._safe_rename(file, new_name)
                if error:
                    if progress_callback:
                        progress_callback(
                            file,
                            {"status": False, "error": error},
                        )
                elif changed:
                    changes[actual_new_path] = file
                    if progress_callback:
                        progress_callback(
                            file,
                            {
                                "status": True,
                                "renamed": True,
                                "new_name": os.path.basename(actual_new_path),
                            },
                        )
                else:
                    if progress_callback:
                        progress_callback(
                            file,
                            {
                                "status": True,
                                "renamed": False,
                                "reason": "No change needed",
                            },
                        )
            except Exception as e:
                if progress_callback:
                    progress_callback(file, {"status": False, "error": str(e)})

        return changes

    def undo_rename(self, changes: dict, progress_callback=None):
        """
        Reverts file renames.

        Args:
            changes (dict): {new_absolute_path: old_absolute_path}
            progress_callback (callable): Function to call upon completing each file
        """
        for new_path, old_path in changes.items():
            try:
                if os.path.exists(new_path):
                    if not os.path.exists(old_path):
                        os.rename(new_path, old_path)
                        if progress_callback:
                            progress_callback(
                                new_path, {"status": True, "restored": True}
                            )
                    else:
                        if progress_callback:
                            progress_callback(
                                new_path, {"status": False, "error": "Target exists"}
                            )
                else:
                    if progress_callback:
                        progress_callback(
                            new_path, {"status": False, "error": "Source missing"}
                        )
            except Exception as e:
                if progress_callback:
                    progress_callback(new_path, {"status": False, "error": str(e)})

    def _safe_rename(self, old_name, new_name):
        """
        Renames a file safely, avoiding name conflicts.

        Args:
            old_name (str): Original filename
            new_name (str): New filename

        Returns:
            tuple: (final_name, change_made, error)
        """

        if os.path.isabs(old_name):
            old_path = old_name
            directory = os.path.dirname(old_name)
        else:
            old_path = os.path.join(self.directory, old_name)
            directory = self.directory

        new_name = self._sanitize_filename(new_name)
        new_path = os.path.join(directory, new_name)

        if os.path.normcase(old_path) == os.path.normcase(new_path):
            return new_path, False, None

        if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(
            old_path
        ):
            if self._are_files_identical(old_path, new_path):
                try:
                    os.remove(old_path)
                    return new_path, True, None
                except OSError as e:
                    return old_path, False, str(e)

        base, extension = os.path.splitext(new_name)
        counter = 1

        while os.path.exists(new_path):
            if os.path.normcase(new_path) == os.path.normcase(old_path):
                break

            new_name = f"{base} ({counter}){extension}"
            new_path = os.path.join(directory, new_name)
            counter += 1

        if os.path.normcase(new_path) == os.path.normcase(old_path):
            return new_path, False, None

        try:
            os.rename(old_path, new_path)
            return new_path, True, None
        except OSError as e:
            return old_path, False, str(e)

    def _are_files_identical(self, path1, path2):
        """
        Compara dos archivos para ver si son idénticos (tamaño y contenido).
        """
        try:
            if os.path.getsize(path1) != os.path.getsize(path2):
                return False

            # Comparar contenido en bloques
            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                while True:
                    b1 = f1.read(8192)
                    b2 = f2.read(8192)
                    if b1 != b2:
                        return False
                    if not b1:
                        return True
        except OSError:
            return False

    def _sanitize_filename(self, filename):
        """
        Sanitizes the filename according to the operating system.

        Args:
            filename (str): Filename to sanitize

        Returns:
            str: Sanitized filename
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
