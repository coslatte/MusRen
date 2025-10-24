"""
Módulo para manejar portadas de álbumes: búsqueda, descarga e incrustación.
"""

import os

from constants.info import MUSIC_RENAMER_VERSION


class AlbumArtManager:
    """
    Clase para manejar todas las operaciones relacionadas con portadas de álbumes.
    """

    def __init__(self):
        """Inicializa el gestor de portadas de álbumes."""
        pass

    def fetch_album_cover(self, artist, album):
        """
        Intenta obtener la URL de la portada del álbum mediante múltiples servicios.

        El proceso de búsqueda sigue estos pasos:
        1. Primero intenta con MusicBrainz si está disponible
        2. Si no encuentra resultados o MusicBrainz no está disponible, intenta con iTunes
        3. Como último recurso, intenta con Deezer

        Args:
            artist (str): Nombre del artista
            album (str): Nombre del álbum

        Returns:
            str: URL de la portada del álbum o None si no se encuentra
        """
        try:
            # Intentar con MusicBrainz
            try:
                import musicbrainzngs

                # Configurar el agente de usuario para MusicBrainz (requerido)
                musicbrainzngs.set_useragent(
                    "musicRenamer",
                    MUSIC_RENAMER_VERSION,
                    "https://github.com/coslatte/musicRenamer",
                )

                # Buscar el álbum en MusicBrainz
                print(f"Buscando información para: {artist} - {album}")
                result = musicbrainzngs.search_releases(
                    release=album, artist=artist, limit=1
                )

                if result and "release-list" in result and result["release-list"]:
                    release = result["release-list"][0]
                    release_id = release["id"]

                    # Obtener la URL de la portada desde Cover Art Archive
                    cover_url = (
                        f"https://coverartarchive.org/release/{release_id}/front"
                    )

                    # Verificar si la portada realmente existe antes de devolverla
                    try:
                        # requests es opcional; importarlo localmente
                        try:
                            import requests
                        except ImportError:
                            print("requests no está instalado; no se puede verificar Cover Art Archive")
                            raise

                        cover_response = requests.head(cover_url, timeout=5)
                        if cover_response.status_code == 200:
                            return cover_url
                        else:
                            print(
                                f"Portada no encontrada en Cover Art Archive (código {cover_response.status_code}). Intentando servicios alternativos..."
                            )
                    except Exception as e:
                        print(
                            f"Error al verificar portada en Cover Art Archive: {str(e)}. Intentando servicios alternativos..."
                        )

                    # No volvemos aquí - seguimos con los otros métodos
            except ImportError:
                print("MusicBrainz no disponible, intentando alternativas...")
            except Exception as e:
                print(f"Error al buscar en MusicBrainz: {str(e)}")

            # Método con iTunes
            print("Intentando con iTunes...")
            search_term = f"{artist} {album}".replace(" ", "+")
            url = f"https://itunes.apple.com/search?term={search_term}&entity=album&limit=1"

            try:
                import requests
            except ImportError:
                print("requests no está instalado; no se puede buscar en iTunes")
                response = None
            else:
                response = requests.get(url)
            if response and response.status_code == 200:
                data = response.json()
                if data.get("resultCount", 0) > 0:
                    result = data["results"][0]
                    # Obtener la URL de la imagen y reemplazar el tamaño para obtener mejor calidad
                    cover_url = result.get("artworkUrl100", "").replace(
                        "100x100", "600x600"
                    )
                    return cover_url

            # Método con Deezer
            print("No se encontró en iTunes, intentando con Deezer...")
            search_term = f"{artist} {album}".replace(" ", "+")
            url = f"https://api.deezer.com/search/album?q={search_term}&limit=1"

            try:
                import requests
            except ImportError:
                print("requests no está instalado; no se puede buscar en Deezer")
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
            print(f"Error al buscar portada: {str(e)}")
            return None

    def fetch_cover_image(self, url):
        """
        Descarga una imagen desde una URL y devuelve los datos binarios.

        Args:
            url (str): URL de la imagen a descargar

        Returns:
            bytes: Datos binarios de la imagen o None si falla
        """

        try:
            print(f"Descargando portada desde: {url}")
            try:
                import requests
            except ImportError:
                print("requests no está instalado; no se puede descargar la portada")
                return None
            response = requests.get(url)
            if response.status_code == 200:
                content_length = len(response.content)
                print(f"Portada descargada. Tamaño: {content_length} bytes")
                if content_length < 100:
                    print(
                        "ADVERTENCIA: La imagen descargada es muy pequeña, podría no ser válida"
                    )
                return response.content
            else:
                print(f"Error al descargar portada. Código: {response.status_code}")
            return None
        except Exception as e:
            print(f"Error al descargar portada: {str(e)}")
            return None

    def embed_album_art(self, file_path, image_data):
        """
        Incrusta la portada del álbum en el archivo de audio.

        Esta función detecta automáticamente el formato del archivo de audio (.mp3, .flac, .m4a)
        y el formato de la imagen (JPEG, PNG). Utiliza diferentes métodos para cada formato
        de archivo, preservando los metadatos existentes.

        Args:
            file_path (str): Ruta al archivo de audio
            image_data (bytes): Datos binarios de la imagen

        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """

        if not image_data:
            print("No hay datos de imagen para incrustar")
            return False

        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            print(
                f"Incrustando portada en {os.path.basename(file_path)} (formato: {file_ext})"
            )

            if file_ext == ".mp3":
                return self._embed_mp3_art(file_path, image_data)
            elif file_ext == ".flac":
                return self._embed_flac_art(file_path, image_data)
            elif file_ext == ".m4a":
                return self._embed_m4a_art(file_path, image_data)
            else:
                print(f"Formato de archivo no soportado para portadas: {file_ext}")
                return False

        except Exception as e:
            print(f"Error general al incrustar portada: {str(e)}")
            return False

    def _embed_mp3_art(self, file_path, image_data):
        """
        Incrusta portada en archivo MP3 usando ID3.

        Args:
            file_path (str): Ruta al archivo MP3
            image_data (bytes): Datos de la imagen

        Returns:
            bool: True si tuvo éxito
        """
        try:
            # Primera comprobamos las etiquetas existentes para preservarlas
            original_tags = {}
            try:
                from mutagen.id3 import ID3
                existing_tags = ID3(file_path)
                print("Leyendo metadatos existentes para preservarlos")
                # Guardar todos los frames excepto APIC
                for frame_key in existing_tags.keys():
                    if not frame_key.startswith("APIC"):
                        original_tags[frame_key] = existing_tags[frame_key]
            except Exception as e:
                print(f"No hay etiquetas previas que preservar: {str(e)}")

            # Crear nuevas etiquetas
            from mutagen.id3 import ID3, APIC
            tags = ID3()

            # Restaurar etiquetas originales
            for key, value in original_tags.items():
                tags[key] = value

            # Determinar tipo MIME
            mime_type = "image/jpeg"  # Asumir JPEG por defecto
            if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"

            # Agregar nueva portada
            tags["APIC"] = APIC(
                encoding=3,  # UTF-8
                mime=mime_type,
                type=3,  # Portada frontal
                desc="Cover",
                data=image_data,
            )

            # Guardar archivo
            tags.save(file_path)
            print(f"Portada incrustada correctamente (formato: {mime_type})")
            return True

        except Exception as e:
            print(f"Error al incrustar portada MP3: {str(e)}")
            return False

    def _embed_flac_art(self, file_path, image_data):
        """
        Incrusta portada en archivo FLAC.

        Args:
            file_path (str): Ruta al archivo FLAC
            image_data (bytes): Datos de la imagen

        Returns:
            bool: True si tuvo éxito
        """
        try:
            from mutagen.flac import FLAC, Picture
            audio = FLAC(file_path)

            # Eliminar imágenes existentes
            existing_pics = len(audio.pictures)
            print(f"Eliminando {existing_pics} imágenes existentes en FLAC")
            audio.clear_pictures()

            # Agregar nueva imagen
            picture = Picture()
            picture.type = 3  # Portada frontal

            # Detectar tipo de imagen
            if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                picture.mime = "image/png"
            else:
                picture.mime = "image/jpeg"

            picture.desc = "Cover"
            picture.data = image_data
            print(f"Portada agregada como {picture.mime}")

            audio.add_picture(picture)
            audio.save()
            print("Archivo FLAC guardado con portada")
            return True
        except Exception as e:
            print(f"Error en portada FLAC: {str(e)}")
            return False

    def _embed_m4a_art(self, file_path, image_data):
        """
        Incrusta portada en archivo M4A/AAC.

        Args:
            file_path (str): Ruta al archivo M4A
            image_data (bytes): Datos de la imagen

        Returns:
            bool: True si tuvo éxito
        """
        try:
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(file_path)

            # Eliminar portadas existentes
            if "covr" in audio:
                print("Eliminando portada existente en M4A")
                del audio["covr"]

            # Agregar nueva portada - detectar formato
            try:
                # Determinar formato
                format_type = MP4Cover.FORMAT_JPEG  # Por defecto
                if image_data[:8].startswith(b"\x89PNG\r\n\x1a\n"):
                    format_type = MP4Cover.FORMAT_PNG
                    print("Detectado formato PNG")
                else:
                    print("Detectado formato JPEG")

                cover = MP4Cover(image_data, format_type)
                audio["covr"] = [cover]
                audio.save()
                print("Archivo M4A guardado con portada")
                return True
            except Exception as e:
                print(f"Error al guardar portada M4A: {str(e)}")
                # Intentar con el otro formato como último recurso
                try:
                    alt_format = (
                        MP4Cover.FORMAT_PNG
                        if format_type == MP4Cover.FORMAT_JPEG
                        else MP4Cover.FORMAT_JPEG
                    )
                    print(f"Intentando con formato alternativo: {alt_format}")
                    cover = MP4Cover(image_data, alt_format)
                    audio["covr"] = [cover]
                    audio.save()
                    print("Archivo M4A guardado con formato alternativo")
                    return True
                except Exception as e2:
                    print(f"Error al guardar con formato alternativo: {str(e2)}")
                    return False
        except Exception as e:
            print(f"Error general en portada M4A: {str(e)}")
            return False
