"""Z-Image Turbo as a second image backend for the constrained_ml MCP server.

Z-Image Turbo is not a checkpoint. It is THREE files that ComfyUI loads
through three different nodes:

    models/diffusion_models/z_image_turbo_bf16.safetensors  -> UNETLoader
    models/text_encoders/qwen_3_4b.safetensors               -> CLIPLoader
    models/vae/ae.safetensors                                -> VAELoader

so it cannot be driven by the CheckpointLoaderSimple graph that
comfyui.py builds. It also has a different sampling contract: it is a
distilled turbo model, so it runs 8 steps at cfg 1.0 with
res_multistep/simple, and it takes NO negative prompt - the same
conditioning goes into both slots.

The recipe is ComfyUI's own blueprint, "Text to Image
(Z-Image-Turbo)", so this is the workflow ComfyUI ships rather than
one invented here.

The backend is only used when all three files are present AND the
caller asks for it (or when it is the only backend available). The
existing checkpoint path is untouched.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_ROOT = Path(os.environ.get("COMFYUI_ROOT", r"D:\ai\ComfyUI_windows_portable"))
MODELS = COMFYUI_ROOT / "ComfyUI" / "models"

# The diffusion model, the text encoder and the VAE. All three are
# required: a Z-Image graph with any one of them missing is rejected
# by ComfyUI at prompt time, so a partial install must not be offered.
ZIMAGE_UNET = "z_image_turbo_bf16.safetensors"
ZIMAGE_CLIP = "qwen_3_4b.safetensors"
ZIMAGE_VAE = "ae.safetensors"

# A distilled turbo model: 8 steps, cfg 1.0, res_multistep/simple.
# This is what ComfyUI's blueprint uses.
ZIMAGE_STEPS = 8
ZIMAGE_CFG = 1.0
ZIMAGE_SAMPLER = "res_multistep"
ZIMAGE_SCHEDULER = "simple"
ZIMAGE_SIZE = 1024


def _http_get(path: str, timeout: int = 30) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(COMFYUI_URL + path, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b""


def _http_post_json(path: str, payload: dict, timeout: int = 60) -> tuple[int, Any]:
    req = urllib.request.Request(
        COMFYUI_URL + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def zimage_available() -> bool:
    """True when all three Z-Image files are on disk."""
    return all([
        (MODELS / "diffusion_models" / ZIMAGE_UNET).is_file(),
        (MODELS / "text_encoders" / ZIMAGE_CLIP).is_file(),
        (MODELS / "vae" / ZIMAGE_VAE).is_file(),
    ])


def zimage_status() -> dict[str, Any]:
    """What is on disk, and what is missing."""
    files = {
        "unet": MODELS / "diffusion_models" / ZIMAGE_UNET,
        "clip": MODELS / "text_encoders" / ZIMAGE_CLIP,
        "vae": MODELS / "vae" / ZIMAGE_VAE,
    }
    present = {k: v.is_file() for k, v in files.items()}
    return {
        "available": all(present.values()),
        "present": present,
        "missing": [k for k, ok in present.items() if not ok],
        "paths": {k: str(v) for k, v in files.items()},
    }


def build_zimage_graph(prompt: str, width: int, height: int,
                       seed: int, steps: int = ZIMAGE_STEPS,
                       filename_prefix: str = "hermes_zimage") -> dict[str, Any]:
    """The Z-Image-Turbo txt2img graph, in ComfyUI's API format.

    The negative slot is wired to the SAME conditioning as the positive
    one. Z-Image is distilled and runs at cfg 1.0, where the negative
    branch has no effect - but the KSampler still requires both inputs,
    and feeding it the positive twice is what ComfyUI's own blueprint
    does.
    """
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": ZIMAGE_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": ZIMAGE_CLIP, "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": ZIMAGE_VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {
                  "seed": seed, "steps": steps, "cfg": ZIMAGE_CFG,
                  "sampler_name": ZIMAGE_SAMPLER, "scheduler": ZIMAGE_SCHEDULER,
                  "denoise": 1.0,
                  "model": ["1", 0], "positive": ["4", 0],
                  "negative": ["4", 0], "latent_image": ["5", 0],
              }},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]}},
    }


def generate_zimage(prompt: str, output_path: str, width: int = ZIMAGE_SIZE,
                    height: int = ZIMAGE_SIZE, steps: int = ZIMAGE_STEPS,
                    seed: int = 0, timeout_s: int = 900) -> dict[str, Any]:
    """Generate one image with Z-Image Turbo. Returns a result dict (never raises)."""
    if not zimage_available():
        st = zimage_status()
        return {"ok": False, "error": "Z-Image Turbo is not fully installed",
                "missing": st["missing"], "paths": st["paths"]}

    graph = build_zimage_graph(prompt, width, height, seed, steps)
    status, body = _http_post_json("/prompt", {"prompt": graph})
    if status != 200:
        return {"ok": False, "error": f"ComfyUI rejected the Z-Image workflow (HTTP {status})",
                "detail": str(body)[:600]}
    if not isinstance(body, dict) or "prompt_id" not in body:
        return {"ok": False, "error": "ComfyUI did not return a prompt_id",
                "detail": str(body)[:600]}
    prompt_id = body["prompt_id"]

    deadline = time.time() + timeout_s
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
            if status_meta == "error":
                return {"ok": False, "error": "the Z-Image workflow failed",
                        "detail": json.dumps(entry.get("status"))[:600]}
        time.sleep(2)
    if not images:
        return {"ok": False,
                "error": f"the Z-Image job produced no image within {timeout_s}s"}

    first = images[0]
    query = f"/view?filename={urllib.parse.quote(first['filename'])}"
    if first.get("subfolder"):
        query += f"&subfolder={urllib.parse.quote(first['subfolder'])}"
    query += f"&type={urllib.parse.quote(first.get('type', 'output'))}"
    status, data = _http_get(query, timeout=120)
    if status != 200 or not data:
        return {"ok": False, "error": f"the image could not be fetched (HTTP {status})"}

    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "ok": True,
        "image": str(target),
        "size_bytes": len(data),
        "backend": "z_image_turbo",
        "model": ZIMAGE_UNET,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": ZIMAGE_CFG,
        "sampler": ZIMAGE_SAMPLER,
        "scheduler": ZIMAGE_SCHEDULER,
        "seed": seed,
        "prompt_id": prompt_id,
    }
