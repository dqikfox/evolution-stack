"""comfyui_launcher.py - start ComfyUI and wait for it to answer.

The one documented way to bring ComfyUI up. The house launcher
(scripts/start_comfyui.cmd) is what this drives: it starts the same
interpreter with the same arguments as the portable
run_nvidia_gpu.bat, but it does not end in "pause" and it does not print an
unconditional c10.dll hint. Both of those make the vendor .bat unusable
from an automated caller.

Why this exists: the estate watchdog needs a start path it can invoke
without a console, and a vendor .bat that waits for a keypress hangs the
heal until its budget expires and then reports a service that had actually
started as still down.

Note: ComfyUI is registered with start.heal = false. It parks about 3.2 GB
of CUDA context on the RTX 3090 and the agent's own starscream-64k needs
about 17.5 GB of the 24 GB available. It is on demand, never auto-healed.
"""
import subprocess
import socket
import sys
import time
from pathlib import Path

# The house launcher. The portable run_nvidia_gpu.bat ends in "pause" and
# prints an unconditional c10.dll hint, so an automated caller that drives
# it either hangs on a keypress or logs the hint as if it were the
# diagnosis.
LAUNCHER = Path(r"C:\Users\KING\AppData\Local\hermes\scripts\start_comfyui.cmd")
# Kept only to say so clearly if the house launcher is ever missing.
VENDOR_BAT = Path("D:/ai/ComfyUI_windows_portable/run_nvidia_gpu.bat")
PORT = 8188
# 180s, not 60s. ComfyUI takes about 65 seconds to bind :8188 on this host
# with a cold model load; the old 60s budget reported a service that was
# about to come up as having timed out.
START_WAIT = 180


def _port_answers() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def launch():
    if _port_answers():
        print(f'ComfyUI is already up on :{PORT}.')
        return True
    if not LAUNCHER.is_file():
        print(f'Error: the ComfyUI launcher is missing at {LAUNCHER}')
        if VENDOR_BAT.is_file():
            print(f'       the vendor launcher exists at {VENDOR_BAT}, but it '
                  f'ends in "pause" and must not be driven by an automated caller')
        return False
    try:
        # CREATE_NEW_CONSOLE ensures the process detaches from this script/agent,
        # preventing the 'detaching script success while real process dies' failure.
        # stdin is closed so a "pause" in any launcher can never block on a
        # keypress that is not coming.
        subprocess.Popen(
            ['cmd.exe', '/c', str(LAUNCHER)],
            cwd=str(LAUNCHER.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_CONSOLE)

        print(f'Waiting for ComfyUI to initialize on port {PORT}...')
        deadline = time.time() + START_WAIT
        while time.time() < deadline:
            time.sleep(2)
            if _port_answers():
                print('ComfyUI is up and running.')
                return True
        print(f'Timeout waiting for service availability on port {PORT}.')
        return False
    except Exception as e:
        print(f'Failed to launch ComfyUI: {e}')
        return False

if __name__ == '__main__':
    sys.exit(0 if launch() else 1)