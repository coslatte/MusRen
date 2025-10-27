import os
import re
import platform
import concurrent.futures
import subprocess
from concurrent.futures import ThreadPoolExecutor

from utils.tools import get_audio_files


class AudioProcessor:
    """
    Main class for processing audio files: recognition, metadata, synchronized lyrics and album covers.
    """

    def __init__(self, directory=".", acoustid_api_key="8XaBELgH", max_workers=4):
        """
        Initializes the audio processor.

        Args:
            directory (str): Directory where audio files are located
            acoustid_api_key (str): API key for AcoustID
            max_workers (int): Maximum number of workers for concurrent processing
        """

        self.directory = os.path.abspath(directory)
        self.acoustid_api_key = acoustid_api_key
        self.max_workers = max_workers
        self.os_type = platform.system()

    def process_files(self, use_recognition=False, process_lyrics=False):
        """
        Processes all audio files in the directory.

        Args:
            use_recognition (bool): Whether to use audio recognition
            process_lyrics (bool): Whether to process synchronized lyrics

        Returns:
            dict: Processing results
        """

        files = get_audio_files(self.directory)
        results = {}

        if not files:
            return results

        if process_lyrics:
            results = self._process_files_with_lyrics(files, use_recognition)

        return results

    def _process_files_with_lyrics(self, files, use_recognition):
        """
        Processes multiple files to add synchronized lyrics.

        Args:
            files (list): List of files to process
            use_recognition (bool): Whether to use audio recognition

        Returns:
            dict: Processing results
        """

        results = {}

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

                except Exception as e:
                    results[file] = {"error": str(e)}

        return results

    def _process_file_with_lyrics(self, file_path, use_recognition):
        """
        Processes an individual file: recognizes the song and embeds synchronized lyrics.

        Args:
            file_path (str): Path to the audio file
            use_recognition (bool): Whether to use audio recognition

        Returns:
            dict: Processing result
        """

        result = {}

        # Get current metadata
        try:
            from mutagen import File
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

        # If AcoustID recognition was requested and metadata is insufficient
        needs_recognition = use_recognition and (
            current_artist == "Unknown Artist" or current_title == "Unknown Title"
        )

        if needs_recognition:
            # Implement recognition logic here
            recognition = self._recognize_song(file_path)

            if recognition["status"]:
                result["recognition"] = True
                result["artist"] = recognition.get("artist", "")
                result["title"] = recognition.get("title", "")
                result["album"] = recognition.get("album", "")
                result["score"] = recognition.get("score", 0)

                # Update complete file metadata
                update_success = self._update_audio_metadata(file_path, recognition)
                result["metadata_updated"] = update_success
                # Result presentation is handled in the CLI

                # Use recognized metadata to search for lyrics
                artist_for_lyrics = recognition.get("artist", "")
                title_for_lyrics = recognition.get("title", "")
            else:
                result["recognition"] = False
                result["recognition_error"] = recognition.get(
                    "message", "Unknown error"
                )
                artist_for_lyrics = current_artist
                title_for_lyrics = current_title
        else:
            artist_for_lyrics = current_artist
            title_for_lyrics = current_title

        # Search for synchronized lyrics
        lyrics_result = self._fetch_synced_lyrics(artist_for_lyrics, title_for_lyrics)

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

            # Check if fpcalc (Chromaprint) is available
            # First try to use fpcalc from current directory
            script_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            os_type = self.os_type

            # Determine executable name based on operating system
            fpcalc_name = "fpcalc.exe" if os_type == "Windows" else "fpcalc"

            # Search for fpcalc in current directory
            local_fpcalc = os.path.join(script_dir, fpcalc_name)

            try:
                # Try to generate acoustic fingerprint using local or system fpcalc
                if os.path.exists(local_fpcalc):
                    # Use local binary directly
                    command = [local_fpcalc, "-json", file_path]
                    process = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()

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
                # Free api_key for general use, but users are recommended to get their own key
                # Request more metadata including tags, genres, and releases for complete information
                results = acoustid.lookup(
                    self.acoustid_api_key,
                    fingerprint,
                    duration,
                    meta="recordings releasegroups releases tracks artists tags genres",
                )

                # Process the results
                if results and "results" in results and results["results"]:
                    # Get the first result with the highest score
                    best_result = results["results"][0]

                    # Extract information from the result
                    if "recordings" in best_result and best_result["recordings"]:
                        recording = best_result["recordings"][0]

                        # Basic information
                        metadata = {
                            "status": True,
                            "score": best_result.get("score", 0),
                            "acoustid": best_result.get("id", ""),
                        }

                        # Extract artist
                        artists = []
                        if "artists" in recording and recording["artists"]:
                            for artist in recording["artists"]:
                                artists.append(artist["name"])
                            metadata["artist"] = artists[0]
                            metadata["artists"] = artists
                        else:
                            metadata["artist"] = "Unknown Artist"
                            metadata["artists"] = ["Unknown Artist"]

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
        try:
            # Lyrics search (status messages in CLI)
            import syncedlyrics

            search_term = f"{artist} {title}"
            lrc_content = syncedlyrics.search(search_term)

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
                    from mutagen.id3 import ID3, USLT
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
                    encoding=3, lang="eng", desc="Lyrics", text=lyrics_content
                )

                tags.save(file_path)
                return True

            else:
                # For other formats use generic mutagen
                try:
                    from mutagen import File
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
            bool: True if updated successfully
        """
        try:
            file_ext = os.path.splitext(file_path)[1].lower()

            if file_ext == ".mp3":
                # For MP3 files use ID3
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
                except Exception:
                    tags = ID3()

                # Update basic metadata
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

                # If there's cover URL, download and embed
                if "cover_url" in metadata:
                    # Import album art manager
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            elif file_ext in [".flac", ".ogg"]:
                # For FLAC and OGG files
                try:
                    from mutagen import File
                except ImportError:
                    return False

                audio = File(file_path)

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
                        audio[file_key] = str(metadata[meta_key])

                audio.save()

                # If there's cover URL, download and embed (only for FLAC)
                if "cover_url" in metadata and file_ext == ".flac":
                    # Import album art manager
                    from core.artwork import AlbumArtManager

                    art_manager = AlbumArtManager()

                    image_data = art_manager.fetch_cover_image(metadata["cover_url"])
                    if image_data:
                        art_manager.embed_album_art(file_path, image_data)

                return True

            elif file_ext == ".m4a":
                # For M4A/AAC files
                try:
                    from mutagen.mp4 import MP4
                except ImportError:
                    return False

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

                # Update metadata
                for meta_key, file_key in field_mapping.items():
                    if meta_key in metadata:
                        audio[file_key] = [metadata[meta_key]]

                # Handle track/disc number for M4A
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

                # If there's cover URL, download and embed
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
                    from mutagen import File
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

    def rename_files(self):
        """
        Renames audio files based on their metadata.
        If the file doesn't have the necessary metadata (artist or title),
        it is not renamed and a message is shown.

        Returns:
            dict: Changes made (new_name: original_name)
        """

        files = get_audio_files(directory=self.directory)
        changes = {}

        for file in files:
            try:
                file_path = os.path.join(self.directory, file)
                try:
                    from mutagen import File
                except ImportError:
                    continue

                audio = File(file_path, easy=True)

                # Check if necessary metadata exists
                if not audio or not audio.tags:
                    continue

                artist = audio.get("artist", [""])[0]
                title = audio.get("title", [""])[0]

                # Check if metadata is empty or default values
                if (
                    not artist
                    or not title
                    or artist == "Unknown Artist"
                    or title == "Unknown Title"
                ):
                    continue

                # Artist - Title.format (.mp3, .flac, etc.)
                new_name = f"{artist} - {title}{os.path.splitext(file)[1]}"

                actual_new_name, changed = self._safe_rename(file, new_name)
                if changed:
                    changes[actual_new_name] = file
            except Exception:
                pass

        # CLI will show renaming summary

        return changes

    def undo_rename(self, changes: dict):
        files = get_audio_files(self.directory)
        for new_name, old_name in changes.items():
            try:
                # Check if the new name exists in the directory
                if new_name in files:
                    self._safe_rename(new_name, old_name)
            except Exception:
                pass

    def _safe_rename(self, old_name, new_name):
        """
        Renames a file safely, avoiding name conflicts.

        Args:
            old_name (str): Original file name
            new_name (str): New name for the file

        Returns:
            tuple: (final_name, change_made)
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
        except OSError:
            return old_name, False

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
