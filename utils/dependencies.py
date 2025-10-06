"""
Módulo para verificar e instalar dependencias del programa.
"""

import os
import subprocess
import sys
import platform


def check_dependencies():
    """
    Verifica si las dependencias necesarias están instaladas y ofrece instalarlas.

    Returns:
        bool: True si todas las dependencias están disponibles o se instalaron correctamente.
    """
    missing_deps = []

    # Verificar mutagen
    try:
        import mutagen

        print("[OK] mutagen está instalado")
    except ImportError:
        missing_deps.append("mutagen")

    # Verificar requests
    try:
        import requests

        print("[OK] requests está instalado")
    except ImportError:
        missing_deps.append("requests")

    # Verificar syncedlyrics
    try:
        import syncedlyrics

        print("[OK] syncedlyrics está instalado")
    except ImportError:
        missing_deps.append("syncedlyrics")

    # Verificar pyacoustid
    try:
        import acoustid

        print("[OK] pyacoustid está instalado")
    except ImportError:
        missing_deps.append("pyacoustid")

    # Si hay dependencias faltantes, ofrecer instalarlas
    if missing_deps:
        print("\nFaltan las siguientes dependencias:")
        for dep in missing_deps:
            print(f"  - {dep}")

        install = input("\n¿Desea instalar las dependencias faltantes? (Y/N): ").lower()
        if install == "y":
            # Construir comando de instalación
            pip_cmd = [sys.executable, "-m", "pip", "install"]
            pip_cmd.extend(missing_deps)

            print(f"\nInstalando: {' '.join(missing_deps)}")
            try:
                subprocess.check_call(pip_cmd)
                print("\n[OK] Dependencias instaladas correctamente")

                # Si se instaló pyacoustid, verificar fpcalc
                if "pyacoustid" in missing_deps:
                    installed, message = check_acoustid_installation()
                    if not installed:
                        print(f"\n[AVISO] {message}")
                        print(
                            "\nAsegúrese de instalar Chromaprint (fpcalc) para usar la funcionalidad de reconocimiento de canciones."
                        )

                return True
            except Exception as e:
                print(f"\n[ERROR] Error al instalar dependencias: {str(e)}")
                return False
        else:
            print("\n[AVISO] El programa puede no funcionar correctamente sin estas dependencias.")
            return False

    # Si llegamos aquí, verificar la instalación de AcoustID
    if check_acoustid_needed():
        installed, message = check_acoustid_installation()
        print(f"\nChromaprint/AcoustID: {message}")

    return True


def check_acoustid_needed():
    """
    Verifica si es necesario comprobar la instalación de AcoustID.

    Returns:
        bool: True si debemos verificar AcoustID.
    """
    try:
        import acoustid

        return True
    except ImportError:
        return False


def check_acoustid_installation():
    """
    Verifica si Chromaprint (fpcalc) está correctamente instalado.

    Returns:
        tuple: (instalado, mensaje)
    """
    try:
        import acoustid

        # Verificar si fpcalc está disponible en el directorio actual
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        os_type = platform.system()

        # Determinar el nombre del ejecutable según el sistema operativo
        fpcalc_name = "fpcalc.exe" if os_type == "Windows" else "fpcalc"

        # Buscar fpcalc en el directorio actual
        local_fpcalc = os.path.join(script_dir, fpcalc_name)

        if os.path.exists(local_fpcalc):
            # Verificar si se puede ejecutar
            try:
                command = [local_fpcalc, "-version"]
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = process.communicate()

                if process.returncode == 0:
                    version = stdout.decode("utf-8", errors="ignore").strip()
                    return (
                        True,
                        f"Chromaprint está instalado localmente. Versión: {version}",
                    )
                else:
                    return (
                        False,
                        f"Chromaprint está presente pero no puede ejecutarse: {stderr.decode('utf-8', errors='ignore')}",
                    )
            except Exception as e:
                return False, f"Error al verificar fpcalc local: {str(e)}"

        # Si no se encuentra localmente, verificar en el PATH
        try:
            # Intentar obtener la versión de fpcalc
            acoustid.fingerprint_file_custom(["fpcalc", "-version"])
            return (
                True,
                "Chromaprint (fpcalc) está correctamente instalado en el PATH del sistema.",
            )
        except Exception() as e:
            if os.path.exists(local_fpcalc):
                # Si el archivo existe localmente pero no se puede ejecutar desde acoustid
                return (
                    False,
                    "Chromaprint (fpcalc) está presente en el directorio actual pero no puede ser utilizado. Asegúrese de que tiene permisos de ejecución.",
                )
            else:
                return (
                    False,
                    "Chromaprint (fpcalc) no está instalado. Coloque fpcalc en el mismo directorio que este script o instálelo en su sistema.",
                )
    except ImportError:
        return (
            False,
            "La biblioteca pyacoustid no está instalada. Instálela con 'pip install pyacoustid'.",
        )
