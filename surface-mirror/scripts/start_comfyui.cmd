@echo off
REM ---------------------------------------------------------------------------
REM start_comfyui.cmd - the ONE documented launcher for ComfyUI.
REM
REM The portable distribution ships run_nvidia_gpu.bat, but that file ends with
REM "pause" and prints an unconditional c10.dll hint. Two problems followed:
REM
REM   1. A launcher invoked by the estate watchdog inherits the console, so
REM      "pause" waits for a keypress that never arrives. The heal burns its
REM      whole budget and then reports the service as still down, even though
REM      the launcher had worked. The c10.dll hint then gets logged as if it
REM      were the diagnosis.
REM
REM   2. The hint is printed whether or not there is a c10.dll problem, so
REM      it reads as an error when nothing is wrong.
REM
REM This launcher starts the same interpreter with the same arguments, in the
REM same working directory, but it never pauses and it never prints a
REM conditional-sounding hint. The MCP server (mcp/constrained_ml/comfyui.py)
REM and any manual operator both use this file, so there is exactly one
REM documented way to bring ComfyUI up.
REM
REM NOTE: ComfyUI is registered with start.heal = false. It parks about
REM 3.2 GB of CUDA context on the RTX 3090 and the agent's own starscream-64k
REM needs about 17.5 GB of the 24 GB available. It is on demand, never
REM auto-healed.
REM ---------------------------------------------------------------------------
setlocal
set "COMFY_ROOT=D:\ai\ComfyUI_windows_portable"
cd /d "%COMFY_ROOT%"
"%COMFY_ROOT%\python_embeded\python.exe" -s ComfyUI\main.py --windows-standalone-build
endlocal
