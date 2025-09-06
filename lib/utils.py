import os
from pathlib import Path


def _no_console_kwargs() -> dict:
    try:
        import sys
        import subprocess as _sp

        if sys.platform.startswith("win"):
            si = _sp.STARTUPINFO()
            si.dwFlags |= _sp.STARTF_USESHOWWINDOW
            return {"startupinfo": si, "creationflags": _sp.CREATE_NO_WINDOW}
    except Exception:
        pass
    return {}


def fmt_bytes(n: int | None) -> str:
    if not n or n <= 0:
        return "N/A"
    return f"{n / (1024 * 1024):.2f} MB"


def fmt_hms(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "N/A"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"


def is_video(path: Path, exts: tuple[str, ...]) -> bool:
    return path.suffix.lower() in set(exts)


def pad2(text: str) -> str | None:
    try:
        return f"{int(text):02d}"
    except Exception:
        return None


class PathTools:
    @staticmethod
    def normalize(p: Path) -> str:
        try:
            abs_path = os.path.abspath(str(p))
        except Exception:
            abs_path = str(p)
        return os.path.normcase(abs_path)
