"""Optional, non-blocking sounds using the Windows standard library."""

from .config import PROJECT_ROOT


def play_sound(filename: str, *, enabled: bool = False) -> None:
    if not enabled:
        return
    path = PROJECT_ROOT / "assets" / "sound" / filename
    if not path.is_file():
        return
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except (ImportError, RuntimeError, OSError):
        pass
