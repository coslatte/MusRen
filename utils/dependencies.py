"""
Module for checking and installing program dependencies.
"""

import os
import subprocess
import sys
import platform
import importlib.util
import shutil


def check_dependencies(use_recognition=False):
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
            print(f"[OK] {mod} is installed")
        else:
            missing_deps.append(MODULE_TO_PIP.get(mod, mod))

    # If there are missing dependencies, offer to install them
    if missing_deps:
        print("\nMissing the following dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")

        install = input("\nDo you want to install the missing dependencies? (Y/N): ").lower()
        if install == "y":
            # Build installation command
            pip_cmd = [sys.executable, "-m", "pip", "install"]
            pip_cmd.extend(missing_deps)

            print(f"\nInstalling: {' '.join(missing_deps)}")
            try:
                subprocess.check_call(pip_cmd)
                print("\n[OK] Dependencies installed successfully")

                # If pyacoustid was installed, check fpcalc
                if "pyacoustid" in missing_deps or "acoustid" in missing_deps:
                    installed, message = check_acoustid_installation()
                    if not installed:
                        print(f"\n[WARNING] {message}")
                        print(
                            "\nMake sure to install Chromaprint (fpcalc) to use song recognition functionality."
                        )

                return True
            except Exception as e:
                print(f"\n[ERROR] Error installing dependencies: {str(e)}")
                return False
        else:
            print(
                "\n[WARNING] The program may not work correctly without these dependencies."
            )
            return False

    # If we reach here, check AcoustID installation (if present and recognition is used)
    if use_recognition and check_acoustid_needed():
        installed, message = check_acoustid_installation()
        print(f"\nChromaprint/AcoustID: {message}")

    return True


def check_acoustid_needed():
    """
    Checks if it is necessary to verify AcoustID installation.

    Returns:
        bool: True if we should verify AcoustID.
    """
    return importlib.util.find_spec("acoustid") is not None


def check_acoustid_installation():
    """
    Checks if Chromaprint (fpcalc) is correctly installed.

    Returns:
        tuple: (installed, message)
    """
    try:
        # First, check in PATH
        fp_in_path = shutil.which("fpcalc") or shutil.which("fpcalc.exe")
        if fp_in_path:
            try:
                result = subprocess.run(
                    [fp_in_path, "-version"], capture_output=True, text=True, check=True
                )
                version = result.stdout.strip() or result.stderr.strip()
                return (
                    True,
                    f"Chromaprint is installed at: {fp_in_path} (version: {version})",
                )
            except Exception:
                return True, f"Chromaprint is present in PATH: {fp_in_path}"

        # Search for fpcalc in project locations
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
                    process = subprocess.Popen(
                        [c, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        version = stdout.decode("utf-8", errors="ignore").strip()
                        return (
                            True,
                            f"Chromaprint is installed locally. Version: {version}",
                        )
                    else:
                        return (
                            False,
                            f"Chromaprint is present but cannot be executed: {stderr.decode('utf-8', errors='ignore')}",
                        )
                except Exception as e:
                    return False, f"Error verifying local fpcalc: {str(e)}"

        return (
            False,
            "Chromaprint (fpcalc) is not installed. Place fpcalc.exe in the project root directory or in the utils/ folder, or install Chromaprint on the system.",
        )
    except Exception as e:
        return False, f"Error verifying Chromaprint: {str(e)}"
