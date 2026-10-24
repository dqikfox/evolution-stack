import os
import subprocess
import sys
from pathlib import Path

base = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\KING\AppData\Local"))
sh = base / "hermes" / "scripts" / "throne_health.sh"
cands = [
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(r"C:\Users\KING\AppData\Local\Programs\Git\bin\bash.exe"),
]
bash = next((str(c) for c in cands if c.exists()), "bash")
raise SystemExit(subprocess.call([bash, str(sh)]))
