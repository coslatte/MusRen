import importlib


def test_import_app_has_main():
    mod = importlib.import_module("app")
    assert hasattr(mod, "main"), "app module should expose a main() function"


def test_import_core_modules():
    for name in ("core.audio_processor", "core.artwork", "core.install_covers"):
        mod = importlib.import_module(name)
        assert mod is not None, f"Failed to import {name}"


def test_utils_dependencies_functions():
    mod = importlib.import_module("utils.dependencies")
    assert hasattr(mod, "check_dependencies")
    assert hasattr(mod, "check_acoustid_needed")
    assert hasattr(mod, "check_acoustid_installation")

    # check_acoustid_needed should return a boolean
    val = mod.check_acoustid_needed()
    assert isinstance(val, bool)

    # check_acoustid_installation should return a tuple (installed: bool, message: str)
    res = mod.check_acoustid_installation()
    assert isinstance(res, tuple) and len(res) == 2
    assert isinstance(res[0], bool)
    assert isinstance(res[1], str)
