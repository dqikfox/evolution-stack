# Windows MCP Bridge (Telemetry Probe)

This reference documents the implementation of a Python-based telemetry bridge used to interface with the Windows host OS via MSYS2 bash environment. This allows the agent to perform hardware sensing (CPU usage, GPU temperature).

## Implementation Details
The bridge uses `subprocess` to invoke native Windows utilities like `powershell.exe` and `nvidia-s/mi`. 

**Crucial Requirement**: Because this runs within an MSYS2 shell context in the `terminal` tool, all path handling must be compatible with both Bash and Windows environments.

### The Telemetry Probe (`telemetry_probe.py`)
```python
import subprocess
import json
import sys

def get_cpu_usage():
    """Uses powershell to fetch total CPU usage."""
    cmd = ["powershell", "-Command", "Get-Counter '\\Processor(_Total)\\% Processor Time' | Select-Object -ExpandProperty CounterSamples | Select-Object -ExpandProperty CookedValue"]
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return float(result.strip())
    except Exception as e:
        return {"error": f"CPU probe failed: {str(e)}"}

def get_gpu_metrics():
    """Uses nvidia-smi to fetch GPU temperature and load."""
    try:
        cmd = ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        temp, util = output.split(',')
        return {"temperature": float(temp), "utilization": float(util)}
    except FileNotFoundError:
        return {"error": "nvidia-smi not found in PATH"}
    except Exception as e:
        return {"error": f"GPU probe failed: {str(e)}"}

def main():
    data = {
        "cpu_usage_percent": get_cpu_usage(),
        "gpu_metrics": get_gpu_metrics(),
    }
    print(json.dumps(data, indent=2))

if __name__ == "__main__':
    main()
```

## Verification Workflow
Always verify the bridge is operational by running it directly from the terminal to ensure `PATH` visibility for `nvidia-smi`:
1.  `python mcp/windows_native/telemetry_probe.py`
2.  Expect valid JSON output containing CPU and GPU metrics (or error messages if hardware probes fail).

## Deployment Context
This module lives in the TESSERACT codebase under `mcp/windows_native`. It marks our transition toward a **Unified Identity** where we monitor our own physical infrastructure via software sensors.
