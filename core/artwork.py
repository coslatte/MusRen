"""
Module for handling album artwork: searching, downloading and embedding.
"""

import os

from constants.info import MUSIC_RENAMER_VERSION


class AlbumArtManager:
    """
    Class for handling all album artwork operations.
    """

    def __init__(self):
        """Initializes the album artwork manager."""
        pass

    def fetch_album_cover(self, artist, album):
        """
        Attempts to obtain the album cover URL through multiple services.

        The search process follows these steps:
        1. First tries MusicBrainz if available
        2. If no results are found or MusicBrainz is not available, tries iTunes
        3. As a last resort, tries Deezer

        Args:
            artist (str): Artist name
            album (str): Album name

        Returns:
            str: Album cover URL or None if not found
        """
        try:
            # Try with MusicBrainz
            try:
                import musicbrainzngs

                # Configure user agent for MusicBrainz (required)
                musicbrainzngs.set_useragent(
                    "musicRenamer",
                    MUSIC_RENAMER_VERSION,
                    "https://github.com/coslatte/musicRenamer",
                )

                # Search for album in MusicBrainz
                print(f"Searching for info: {artist} - {album}")
                result = musicbrainzngs.search_releases(
                    release=album, artist=artist, limit=1
                )

                if result and "release-list" in result and result["release-list"]:
                    release = result["release-list"][0]
                    release_id = release["id"]

                    # Get the cover URL from Cover Art Archive
                    cover_url = (
                        f"https://coverartarchive.org/release/{release_id}/front"
                    )

                    # Verify if the cover actually exists before returning it
                    try:
                        # requests es opcional; importarlo localmente
                        try:
                            import requests
                        except ImportError:
                            print("requests not installed; cannot verify Cover Art Archive")
                            raise

                        cover_response = requests.head(cover_url, timeout=5)
                        if cover_response.status_code == 200:
                            return cover_url
                        else:
                            print(
                                f"Cover not found in Cover Art Archive (code {cover_response.status_code}). Trying alternative services..."
                            )
                    except Exception as e:
                        print(
                            f"Error verifying cover in Cover Art Archive: {str(e)}. Trying alternative services..."
                        )

                    # We don't return here - we continue with other methods
            except ImportError:
                print("MusicBrainz not available, trying alternatives...")
            except Exception as e:
                print(f"Error searching in MusicBrainz: {str(e)}")

            # Method with iTunes
            print("Trying with iTunes...")
            search_term = f"{artist} {album}".replace(" ", "+")
            url = f"https://itunes.apple.com/search?term={search_term}&entity=album&limit=1"

            try:
                import requests
            except ImportError:
                print("requests not installed; cannot search in iTunes")
                response = None
            else:
                response = requests.get(url)
            if response and response.status_code == 200:
                data = response.json()
                if data.get("resultCount", 0) > 0:
                    result = data["results"][0]
                    # Get the image URL and replace the size to get better quality
                    cover_url = result.get("artworkUrl100", "").replace(
                        "100x100", "600x600"
                    )
                    return cover_url

            # Method with Deezer
            print("Not found in iTunes, trying with Deezer...")
            search_term = f"{artist} {album}".replace(" ", "+")
            url = f"https://api.deezer.com/search/album?q={search_term}&limit=1"

            try:
                import requests
            except ImportError:
                print("requests not installed; cannot search in Deezer")
                return None
            response = requests.get(url)
            if response and response.status_code == 200:
                data = response.json()
                if data.get("total", 0) > 0 and data.get("data"):
                    result = data["data"][0]
                    cover_url = (
                        result.get("cover_xl")
                        or result.get("cover_big")
                        or result.get("cover")
                    )
                    return cover_url

            return None

        except Exception as e:
            print(f"Error searching for cover: {str(e)}")
            return None

    def fetch_cover_image(self, url):
        """
        Downloads an image from a URL and returns the binary data.

        Args:
            url (str): URL of the image to download

        Returns:
            bytes: Binary data of the image or None if it fails
        """

        try:
            print(f"Downloading cover from: {url}")
            try:
                import requests
            except ImportError:
                print("requests not installed; cannot download cover")
                return None
            response = requests.get(url)
            if response.status_code == 200:
                content_length = len(response.content)
                print(f"Cover downloaded. Size: {content_length} bytes")
                if content_length < 100:
                    print(
                        "WARNING: The downloaded image is very small, it might not be valid"
                    )
                return response.content
            else:
                print(f"Error downloading cover. Code: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error downloading cover: {str(e)}")
            return None

    def embed_album_art(self, file_path, image_data):
        """
        Embeds the album cover in the audio file.

        This function automatically detects the audio file format (.mp3, .flac, .m4a)
        and image format (JPEG, PNG). It uses different methods for each file format,
        preserving existing metadata.

        Args:
            file_path (str): Path to the audio file
            image_data (bytes): Binary data of the image

        Returns:
            bool: True if the operation was successful, False otherwise
        """

        if not image_data:
            print("No image data to embed")
            return False

        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            print(
                f"Embedding cover in {os.path.basename(file_path)} (format: {file_ext})"
            )

            if file_ext == ".mp3":
                return self._embed_mp3_art(file_path, image_data)
            elif file_ext == ".flac":
                return self._embed_flac_art(file_path, image_data)
            elif file_ext == ".m4a":
                return self._embed_m4a_art(file_path, image_data)
            else:
                print(f"File format not supported for covers: {file_ext}")
                return False

        except Exception as e:
            print(f"General error embedding cover: {str(e)}")
            return False

    def _embed_mp3_art(self, file_path, image_data):
        """
        Embeds cover in MP3 file using ID3.

        Args:
            file_path (str): Path to MP3 file
            image_data (bytes): Image data

        Returns:
            bool: True if successful
        """
        try:
            # First check existing tags to preserve them
            original_tags = {}
            try:
                from mutagen.id3 import ID3
                existing_tags = ID3(file_path)
                print("Reading existing metadata to preserve it")
                # Save all frames except APIC
                for frame_key in existing_tags.keys():
                    if not frame_key.startswith("APIC"):
                        original_tags[frame_key] = existing_tags[frame_key]
            except Exception as e:
                print(f"No previous tags to preserve: {str(e)}")

            # Create new tags
            from mutagen.id3 import ID3, APIC
            tags = ID3()

            # Restore original tags
            for key, value in original_tags.items():
                tags[key] = value

            # Determine MIME type
            mime_type = "image/jpeg"  # Assume JPEG by default
            if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"

            # Add new cover
            tags["APIC"] = APIC(
                encoding=3,  # UTF-8
                mime=mime_type,
                type=3,  # Front cover
                desc="Cover",
                data=image_data,
            )

            # Save file
            tags.save(file_path)
            print(f"Cover embedded successfully (format: {mime_type})")
            return True

        except Exception as e:
            print(f"Error embedding MP3 cover: {str(e)}")
            return False

    def _embed_flac_art(self, file_path, image_data):
        """
        Embeds cover in FLAC file.

        Args:
            file_path (str): Path to FLAC file
            image_data (bytes): Image data

        Returns:
            bool: True if successful
        """
        try:
            from mutagen.flac import FLAC, Picture
            audio = FLAC(file_path)

            # Remove existing images
            existing_pics = len(audio.pictures)
            print(f"Removing {existing_pics} existing images in FLAC")
            audio.clear_pictures()

            # Add new image
            picture = Picture()
            picture.type = 3  # Front cover

            # Detect image type
            if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                picture.mime = "image/png"
            else:
                picture.mime = "image/jpeg"

            picture.desc = "Cover"
            picture.data = image_data
            print(f"Cover added as {picture.mime}")

            audio.add_picture(picture)
            audio.save()
            print("FLAC file saved with cover")
            return True
        except Exception as e:
            print(f"Error in FLAC cover: {str(e)}")
            return False

    def _embed_m4a_art(self, file_path, image_data):
        """
        Embeds cover in M4A/AAC file.

        Args:
            file_path (str): Path to M4A file
            image_data (bytes): Image data

        Returns:
            bool: True if successful
        """
        try:
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(file_path)

            # Remove existing covers
            if "covr" in audio:
                print("Removing existing cover in M4A")
                del audio["covr"]

            # Add new cover - detect format
            try:
                # Determine format
                format_type = MP4Cover.FORMAT_JPEG  # Default
                if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                    format_type = MP4Cover.FORMAT_PNG
                    print("PNG format detected")
                else:
                    print("JPEG format detected")

                cover = MP4Cover(image_data, format_type)
                audio["covr"] = [cover]
                audio.save()
                print("M4A file saved with cover")
                return True
            except Exception as e:
                print(f"Error saving M4A cover: {str(e)}")
                # Try with the other format as last resort
                try:
                    alt_format = (
                        MP4Cover.FORMAT_PNG
                        if format_type == MP4Cover.FORMAT_JPEG
                        else MP4Cover.FORMAT_JPEG
                    )
                    print(f"Trying with alternative format: {alt_format}")
                    cover = MP4Cover(image_data, alt_format)
                    audio["covr"] = [cover]
                    audio.save()
                    print("M4A file saved with alternative format")
                    return True
                except Exception as e2:
                    print(f"Error saving with alternative format: {str(e2)}")
                    return False
        except Exception as e:
            print(f"General error in M4A cover: {str(e)}")
            return False
