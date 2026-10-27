"""Image generation for the constrained_ml MCP server, against ComfyUI's real API.

ComfyUI has NO /hermes/generate route. Its actual HTTP contract is:
    POST /prompt        - submit a workflow graph, returns {"prompt_id": ...}
    GET  /history/{id}  - poll until the output slot is populated
    GET  /view          - fetch the image bytes by filename

The graph below is a minimal txt2img chain:
    CheckpointLoaderSimple -> CLIPTextEncode (pos/neg) -> EmptyLatentImage
    -> KSampler -> VAEDecode -> SaveImage

Two host constraints are honoured here:

  * VRAM. The RTX 3090 (24 GB) has the agent's own model (starscream-64k,
    17.5 GB) resident. A diffusion model must fit in what is LEFT, so the
    sampler steps, resolution and batch are deliberately conservative and the
    tool reports the actual free VRAM before it starts. ComfyUI is started
    with --lowvram when this host asks for it.

  * Checkpoint selection. This host's ComfyUI ships a VIDEO checkpoint
    (ltx-video-2b) and the Kandinsky5 NODES but no Kandinsky weights, so the
    tool picks a real image checkpoint that is actually on disk and says so
    plainly when there is none.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

IS_WINDOWS = os.name == "nt"
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_ROOT = Path(os.environ.get("COMFYUI_ROOT", r"D:\ai\ComfyUI_windows_portable"))
CHECKPOINT_DIR = COMFYUI_ROOT / "ComfyUI" / "models" / "checkpoints"
# The house launcher, not the portable run_nvidia_gpu.bat: the .bat ends
# in "pause" and prints an unconditional c10.dll hint, so a caller that
# inherits the console waits for a keypress and misreads the hint as the
# diagnosis. scripts/start_comfyui.cmd starts the same thing and returns.
LAUNCHER = Path(r"C:\Users\KING\AppData\Local\hermes\scripts\start_comfyui.cmd")
START_WAIT = 180

# The GPU budget this has to live inside. The card is 24 GB. The
# agent's own model (starscream-64k, 64K context) is resident in
# Ollama and parks 17.5 GB of it, and a second local endpoint
# (llama.cpp serving Qwen2.5-7B on :8082) parks most of what is
# left. ComfyUI needs roughly 3.2 GB of CUDA context before it has
# loaded anything at all.
#
# So ComfyUI sometimes cannot start - and the symptom is a long,
# unhelpful wait: "ComfyUI did not answer /system_stats within 180s".
# The process was not broken. It was waiting for memory that was
# already spoken for.
FREE_VRAM_NEEDED_GB = 5.0
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def _free_vram_gb() -> float:
    """Free VRAM on the card, in GB. -1 when it cannot be read."""
    if not IS_WINDOWS:
        return -1.0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip().splitlines()
        if not out:
            return -1.0
        return float(out[0].strip()) / 1024.0
    except Exception:
        return -1.0


def _release_vram_for_comfy() -> str:
    """Free enough VRAM for ComfyUI to start, if it is needed.

    The house already has this pattern - scripts/mem_guard.py unloads
    a resident model with keep_alive=0 - but nothing called it before
    ComfyUI started, so the image path failed intermittently on a
    machine with plenty of total VRAM and none of it free.

    The agent's model is unloaded, not the other local endpoint:
    llama.cpp serves a fixed model on a fixed port and is part of the
    estate's published surface, while the Ollama model is reloaded on
    demand by the router. Unloading it costs a reload; not unloading
    it costs the image path entirely.
    """
    free = _free_vram_gb()
    if free < 0 or free >= FREE_VRAM_NEEDED_GB:
        return f"free VRAM {free:.1f} GB - no release needed"
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=10) as response:
            models = json.loads(response.read().decode("utf-8", "replace")).get("models", [])
    except Exception as exc:  # noqa: BLE001
        return f"could not read the resident models ({exc})"
    resident = [m for m in models if m.get("name")]
    if not resident:
        return f"free VRAM {free:.1f} GB and no resident model to release"
    for model in resident:
        name = model.get("name")
        try:
            request = urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=json.dumps({"model": name, "keep_alive": 0}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=20):
                pass
        except Exception:  # noqa: BLE001
            continue
    # VRAM comes back asynchronously, so wait for it rather than
    # starting ComfyUI into the same wall.
    for _ in range(20):
        time.sleep(3)
        now = _free_vram_gb()
        if now >= FREE_VRAM_NEEDED_GB:
            return (f"released {resident[0].get('name')} - free VRAM went "
                    f"{free:.1f} GB -> {now:.1f} GB")
    return (f"released {resident[0].get('name')} - free VRAM is {now:.1f} GB, "
            f"still under the {FREE_VRAM_NEEDED_GB} GB ComfyUI needs")


def _http_get(path: str, timeout: int = 15) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"{COMFYUI_URL}{path}", timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception:
        return 0, b""


def _http_post_json(path: str, payload: dict[str, Any], timeout: int = 30) -> tuple[int, Any]:
    try:
        request = urllib.request.Request(
            f"{COMFYUI_URL}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, body
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(detail)
        except json.JSONDecodeError:
            return exc.code, detail
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def _comfy_is_up() -> bool:
    status, _ = _http_get("/system_stats", timeout=4)
    return status == 200


def _release_comfy_memory() -> None:
    """Ask ComfyUI to unload its models and free cached VRAM.

    ComfyUI is a long-lived process and holds its diffusion model in VRAM
    between jobs. On this host the agent's own model (starscream-64k) needs
    17.5 GB of the RTX 3090's 24 GB, so a retained diffusion model starves
    the agent - the model gets evicted by Ollama and every turn pays a
    multi-GB reload. Releasing after each job keeps the agent resident.
    """
    _http_post_json("/free", {"unload_models": True, "free_memory": True}, timeout=20)


def _free_vram_mb() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        return int(result.stdout.strip().splitlines()[0])
    except Exception:
        return None


def _start_comfy() -> tuple[bool, str]:
    """Start ComfyUI through its documented launcher, and wait for readiness."""
    if not LAUNCHER.is_file():
        return False, f"the ComfyUI launcher is missing at {LAUNCHER}"
    # Free the memory ComfyUI needs BEFORE it starts. Starting it into
    # a full card produces a long wait and then a misleading "did not
    # answer /system_stats" - the process was fine, it was starved.
    released = _release_vram_for_comfy()
    print(f"[comfyui] {released}")
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(LAUNCHER)],
            cwd=str(COMFYUI_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    except Exception as exc:
        return False, f"ComfyUI could not be started: {exc}"
    deadline = time.time() + START_WAIT
    while time.time() < deadline:
        if _comfy_is_up():
            return True, f"ComfyUI is up ({released})"
        time.sleep(3)
    return False, f"ComfyUI did not answer /system_stats within {START_WAIT}s ({released})"


def _restore_agent_model() -> str:
    """Put the agent's model back after ComfyUI has had the card.

    The release is not free: the estate's own check wants the agent's
    model RESIDENT, and a local inference on a cold model pays a
    reload. So whatever takes the memory has to give it back when it
    is done, or the image path silently becomes the thing that
    degrades the agent.

    Ollama has no "load" endpoint - a model is loaded by being used -
    so the restore is a minimal generation with a keep_alive, which
    is what the house's own watchdog does (30m).
    """
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=10) as response:
            models = json.loads(response.read().decode("utf-8", "replace")).get("models", [])
    except Exception as exc:  # noqa: BLE001
        return f"could not read the resident models ({exc})"
    if models:
        return f"{models[0].get('name')} is still resident - nothing to restore"
    name = os.environ.get("HERMES_LOCAL_MODEL", "starscream-64k:latest")
    try:
        request = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps({
                "model": name, "prompt": " ", "stream": False,
                "options": {"num_predict": 1}, "keep_alive": "30m",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180):
            pass
    except Exception as exc:  # noqa: BLE001
        return f"could not reload {name}: {exc}"
    return f"reloaded {name}"


def _stop_comfy() -> bool:
    """Stop the ComfyUI process this module started.

    A running ComfyUI parks ~3.2 GB of CUDA context on the RTX 3090 even with
    no model loaded, and the agent's own starscream-64k needs 17.5 GB of the
    24 GB the card has. Leaving ComfyUI running for the convenience of a
    faster next call squeezes the agent's model. ComfyUI is therefore started
    on demand and stopped again when this module is the one that started it.
    """
    if not IS_WINDOWS:
        return False
    stopped = False
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' }; "
             "if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; "
             "'stopped' } else { 'absent' }"],
            capture_output=True, text=True, timeout=60,
        )
        stopped = "stopped" in (result.stdout or "")
    except Exception:
        stopped = False
    # ComfyUI had the card. Give it back, or the agent's model stays
    # unloaded and the next local inference pays for a cold start.
    try:
        restored = _restore_agent_model()
    except Exception as exc:  # noqa: BLE001
        restored = f"could not restore the agent's model: {exc}"
    print(f"[comfyui] stopped ComfyUI; {restored}")
    return stopped


def _image_checkpoints() -> list[str]:
    """Checkpoints on disk that can actually produce a still image.

    A VIDEO checkpoint (ltx-video) is excluded: it is not loadable by
    CheckpointLoaderSimple for a txt2img graph.
    """
    if not CHECKPOINT_DIR.is_dir():
        return []
    names = []
    for path in sorted(CHECKPOINT_DIR.glob("*.safetensors")):
        if "ltx" in path.stem.lower() or "video" in path.stem.lower():
            continue
        names.append(path.name)
    return names


def _build_graph(checkpoint: str, prompt: str, negative: str,
                 width: int, height: int, steps: int, seed: int) -> dict[str, Any]:
    """A minimal txt2img workflow graph in ComfyUI's API format."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {
                  "seed": seed, "steps": steps, "cfg": 7.0,
                  "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                  "model": ["1", 0], "positive": ["2", 0],
                  "negative": ["3", 0], "latent_image": ["4", 0],
              }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "hermes_constrained_ml", "images": ["6", 0]}},
    }


def generate(prompt: str, output_path: str, negative_prompt: str = "",
             width: int = 512, height: int = 512, steps: int = 20,
             checkpoint: str = "") -> dict[str, Any]:
    """Generate one image through ComfyUI. Returns a result dict (never raises)."""
    started_comfy = False
    if not _comfy_is_up():
        ok, detail = _start_comfy()
        if not ok:
            return {"ok": False, "error": detail,
                    "fix": "start ComfyUI manually, or set COMFYUI_ROOT to the portable install"}
        started_comfy = True

    available = _image_checkpoints()
    if not available:
        return {
            "ok": False,
            "error": (
                f"no image checkpoint is present in {CHECKPOINT_DIR} "
                f"(only video checkpoints were found)"
            ),
            "fix": "place an image checkpoint (.safetensors) in ComfyUI/models/checkpoints",
        }
    chosen = checkpoint or available[0]
    if chosen not in available:
        return {"ok": False, "error": f"checkpoint {chosen!r} is not on disk",
                "available": available}

    free = _free_vram_mb()
    graph = _build_graph(chosen, prompt, negative_prompt, width, height, steps, random.randint(0, 2**31 - 1))
    status, body = _http_post_json("/prompt", {"prompt": graph})
    if status != 200:
        return {"ok": False, "error": f"ComfyUI rejected the workflow (HTTP {status})",
                "detail": str(body)[:600]}
    if not isinstance(body, dict) or "prompt_id" not in body:
        return {"ok": False, "error": "ComfyUI did not return a prompt_id", "detail": str(body)[:600]}
    prompt_id = body["prompt_id"]

    deadline = time.time() + 600
    images: list[dict[str, Any]] = []
    while time.time() < deadline:
        status, hist = _http_get(f"/history/{prompt_id}")
        if status == 200:
            try:
                entry = json.loads(hist).get(prompt_id, {})
            except json.JSONDecodeError:
                entry = {}
            for node_output in (entry.get("outputs") or {}).values():
                for image in node_output.get("images", []) or []:
                    images.append(image)
            if images:
                break
            status_meta = (entry.get("status") or {}).get("status_str")
            if status_meta in ("error",):
                _release_comfy_memory()
                return {"ok": False, "error": "the ComfyUI workflow failed",
                        "detail": json.dumps(entry.get("status"))[:600]}
        time.sleep(2)
    if not images:
        _release_comfy_memory()
        return {"ok": False, "error": "the ComfyUI job produced no image within 600s"}

    first = images[0]
    query = f"/view?filename={urllib.parse.quote(first['filename'])}"
    if first.get("subfolder"):
        query += f"&subfolder={urllib.parse.quote(first['subfolder'])}"
    query += f"&type={urllib.parse.quote(first.get('type', 'output'))}"
    status, data = _http_get(query, timeout=60)
    if status != 200 or not data:
        return {"ok": False, "error": f"the image could not be fetched (HTTP {status})"}

    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    # Hand the VRAM back to the agent's model (see _release_comfy_memory).
    try:
        _release_comfy_memory()
    except Exception:
        pass
    stopped = False
    if started_comfy:
        # This module started it, so this module stops it. A ComfyUI someone
        # else launched is left running.
        stopped = _stop_comfy()
    return {
        "ok": True,
        "image": str(target),
        "size_bytes": len(data),
        "checkpoint": chosen,
        "width": width,
        "height": height,
        "steps": steps,
        "free_vram_mb_before": free,
        "comfyui_started": started_comfy,
        "comfyui_stopped": stopped,
    }
