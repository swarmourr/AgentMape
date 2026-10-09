"""
Post-install script for pegasus-healer.
Creates ~/.pegasus/healer.env from the bundled example if it does not exist.
Called by the Makefile dev/install targets after pip install.
"""
import os
import shutil
import stat
from pathlib import Path

EXAMPLE = Path(__file__).parents[1] / "src" / "Pegasus" / "healer" / "healer.env.example"
TARGET  = Path.home() / ".pegasus" / "healer.env"

if TARGET.exists():
    print(f"[healer] ~/.pegasus/healer.env already exists — not overwritten")
else:
    TARGET.parent.mkdir(exist_ok=True)
    shutil.copy(EXAMPLE, TARGET)
    TARGET.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
    print(f"[healer] Created {TARGET}")
    print(f"[healer] Edit it and set LLM_MODEL + LLM_API_KEY before use.")
