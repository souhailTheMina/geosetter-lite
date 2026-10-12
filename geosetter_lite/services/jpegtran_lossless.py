import shutil
import subprocess
from pathlib import Path
from typing import Optional

# An app bundle started from Finder does not inherit the shell's PATH, so look
# in the Homebrew locations too
_COMMON_PATHS = [
    '/opt/homebrew/bin/jpegtran',  # Homebrew Apple Silicon Mac
    '/usr/local/bin/jpegtran',  # Homebrew Intel Mac
    '/usr/bin/jpegtran',  # Linux system install
]


def _find_jpegtran() -> Optional[str]:
    """Return the jpegtran executable, or None if it is not installed"""
    found = shutil.which('jpegtran')
    if found:
        return found
    return next((p for p in _COMMON_PATHS if Path(p).is_file()), None)


def jpegtran_lossless_rotate(filepath: Path, degrees: int) -> bool:
    """Rotate a JPEG file losslessly using jpegtran. Returns True if successful."""
    assert degrees in (90, 180, 270), "Only 90, 180, 270 degrees supported"
    jpegtran = _find_jpegtran()
    if jpegtran is None:
        print("jpegtran is not installed")
        return False
    tmp_path = filepath.with_suffix('.rotating_tmp.jpg')
    try:
        result = subprocess.run([
            jpegtran, f'-rotate', str(degrees), '-copy', 'all', '-outfile', str(tmp_path), str(filepath)
        ], capture_output=True)
        if result.returncode == 0 and tmp_path.exists():
            tmp_path.replace(filepath)
            return True
        else:
            print(f"jpegtran failed: {result.stderr.decode()}")
            if tmp_path.exists():
                tmp_path.unlink()
            return False
    except Exception as e:
        print(f"jpegtran exception: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False
