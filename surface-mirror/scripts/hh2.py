from __future__ import annotations
print("1-start", flush=True)
import json, os, socket, subprocess, sys, time, urllib.request
print("2-imports", flush=True)
from datetime import datetime, timezone
from pathlib import Path
print("3-path", flush=True)

def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

print("4-defs", flush=True)
services = {n: port_open(p) for n,p in {"ollama":11434,"openclaw":18789,"nexus":8650,"tesseract":8705}.items()}
print("5-services", services, flush=True)

def http_ok(url: str, timeout: float = 4.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(200).decode("utf-8", errors="ignore")
            return r.status == 200, body[:120]
    except Exception as e:
        return False, str(e)

print("6-http-nexus", http_ok("http://127.0.0.1:8650/health"), flush=True)
print("7-http-tess", http_ok("http://127.0.0.1:8705/health"), flush=True)

print("8-ps-begin", flush=True)
try:
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"],
        text=True, timeout=20, stderr=subprocess.DEVNULL,
    ).strip()
    print("9-cpu", out, flush=True)
except Exception as e:
    print("9-cpu-err", e, flush=True)

print("10-done", flush=True)
