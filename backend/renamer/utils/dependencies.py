"""
Módulo para verificar e instalar dependencias del programa.
"""

import os
import subprocess
import sys
import platform
import importlib.util
import shutil


def check_dependencies():
    """
    Verifica si las dependencias necesarias están instaladas y ofrece instalarlas.

    Returns:
        bool: True si todas las dependencias están disponibles o se instalaron correctamente.
    """
    # Map Python import names to pip package names when they differ
    MODULE_TO_PIP = {
        "mutagen": "mutagen",
        "requests": "requests",
        "syncedlyrics": "syncedlyrics",
        "acoustid": "pyacoustid",
        "musicbrainzngs": "musicbrainzngs",
    }

    def is_installed(module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    missing_deps = []

    for mod in ("mutagen", "requests", "syncedlyrics", "acoustid"):
        if is_installed(mod):
            print(f"[OK] {mod} está instalado")
        else:
            missing_deps.append(MODULE_TO_PIP.get(mod, mod))

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
                if "pyacoustid" in missing_deps or "acoustid" in missing_deps:
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
            print(
                "\n[AVISO] El programa puede no funcionar correctamente sin estas dependencias."
            )
            return False

    # Si llegamos aquí, verificar la instalación de AcoustID (si está presente)
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
    return importlib.util.find_spec("acoustid") is not None


def check_acoustid_installation():
    """
    Verifica si Chromaprint (fpcalc) está correctamente instalado.

    Returns:
        tuple: (instalado, mensaje)
    """
    try:
        # Primero, comprobar en PATH
        fp_in_path = shutil.which("fpcalc") or shutil.which("fpcalc.exe")
        if fp_in_path:
            try:
                result = subprocess.run([fp_in_path, "-version"], capture_output=True, text=True, check=True)
                version = result.stdout.strip() or result.stderr.strip()
                return True, f"Chromaprint está instalado en: {fp_in_path} (versión: {version})"
            except Exception:
                return True, f"Chromaprint está presente en PATH: {fp_in_path}"

        # Buscar fpcalc en ubicaciones del proyecto
        script_dir = os.path.abspath(os.path.dirname(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, ".."))
        os_type = platform.system()
        fpcalc_name = "fpcalc.exe" if os_type == "Windows" else "fpcalc"
        candidates = [
            os.path.join(script_dir, fpcalc_name),
            os.path.join(project_root, fpcalc_name),
            os.path.join(project_root, "utils", fpcalc_name),
            os.path.join(os.getcwd(), fpcalc_name),
        ]

        for c in candidates:
            if os.path.exists(c):
                try:
                    process = subprocess.Popen([c, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        version = stdout.decode("utf-8", errors="ignore").strip()
                        return True, f"Chromaprint está instalado localmente. Versión: {version}"
                    else:
                        return False, f"Chromaprint está presente pero no puede ejecutarse: {stderr.decode('utf-8', errors='ignore')}"
                except Exception as e:
                    return False, f"Error al verificar fpcalc local: {str(e)}"

        return False, "Chromaprint (fpcalc) no está instalado. Coloque fpcalc.exe en el directorio raíz del proyecto o en la carpeta utils/, o instale Chromaprint en el sistema."
    except Exception as e:
        return False, f"Error verificando Chromaprint: {str(e)}"
