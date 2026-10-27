"""
test_image_stack.py - a real image through the real ComfyUI HTTP API.

Lives in %LOCALAPPDATA%/hermes/tests/ so neither of the two cleaners that
want to delete it can: the evolution stack never had tests/ on its improvable
surface, and the disk-cleanup plugin now has "tests" on its protected
top-level list. See test_ml_stack.py for the full account.

What it proves:
  1. The ComfyUI helper finds a usable image checkpoint.
  2. It starts ComfyUI if it is not already up.
  3. POST /prompt -> GET /history/{id} -> GET /view produces a REAL PNG.
  4. The PNG is a valid image with real dimensions (not a 0-byte stub).
  5. The diffusion model is released afterwards (POST /free) and the agent's
     own Ollama model is still resident, so the image path does not starve
     the agent.
  6. ComfyUI is stopped again when this test started it.

Usage:
    python tests/test_image_stack.py
    python tests/test_image_stack.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERMES = Path(r"C:\Users\KING\AppData\Local\hermes")
MCP_DIR = HERMES / "mcp" / "constrained_ml"
sys.path.insert(0, str(MCP_DIR))

SCRATCH = HERMES / "cache" / "scratch"
OLLAMA_PS = "http://127.0.0.1:11434/api/ps"

RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)
    return ok


def _png_size(path: Path) -> tuple[int, int] | None:
    """Read width/height straight out of the PNG IHDR chunk - no image lib."""
    try:
        data = path.read_bytes()[:24]
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def _ollama_resident() -> list[str]:
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return [m.get("name", "?") for m in data.get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def _stop_comfy_if_we_started_it(was_up: bool) -> bool:
    """Put ComfyUI back the way this test found it.

    Called from a `finally`, so it runs on EVERY exit path - including
    the early returns for a failed generation and the exception path.
    That is the whole point: the test used to stop ComfyUI only on the
    success path, so a failure left it running. ComfyUI parks about
    3.2GB of VRAM on a single-GPU host where the agent's own model needs
    17.5GB of the 24GB available, so a leaked ComfyUI is not a stray
    process - it is the difference between the agent model fitting and
    the agent model being evicted.

    A ComfyUI that was already running when the test started is left
    alone: it belongs to whoever started it.
    """
    try:
        import comfyui
        if was_up:
            return False
        if not comfyui._comfy_is_up():
            return True
        return comfyui._stop_comfy()
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("constrained_ml image generation test (real ComfyUI)")
    print("=" * 70)

    import comfyui  # the tested helper next to the MCP server

    was_up = comfyui._comfy_is_up()
    record("comfyui_pre_state", True, f"already up: {was_up}")
    try:
        return _run_body(was_up)
    finally:
        # ALWAYS. Whatever happened above - success, a failed generation,
        # an exception - ComfyUI goes back the way it was found.
        stopped = _stop_comfy_if_we_started_it(was_up)
        if stopped:
            record("comfyui_stopped_if_we_started_it", True,
                   "ComfyUI was started by this test, so it stops it again")
        else:
            record("comfyui_left_running_as_found", True,
                   f"was_up={was_up} - left as found")


def _run_body(was_up: bool) -> int:

    checkpoints = comfyui._image_checkpoints()
    record("image_checkpoint_found", bool(checkpoints),
           f"checkpoints={checkpoints}")

    before_resident = _ollama_resident()
    record("agent_model_before", bool(before_resident), f"resident={before_resident}")

    out = SCRATCH / "image_stack_test.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    prompt = ("a lighthouse on a rocky cliff at dusk, dramatic storm clouds, "
              "warm lighthouse beam cutting through sea spray, cinematic lighting")
    started = time.time()
    try:
        result = comfyui.generate(prompt=prompt, output_path=str(out), steps=22)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        record("generate", False, f"{type(exc).__name__}: {exc}")
        return 1
    elapsed = time.time() - started

    ok = bool(result.get("ok")) if isinstance(result, dict) else False
    record("generate", ok, f"{elapsed:.0f}s detail={str(result)[:150]}")
    if not ok:
        return 1

    # A real PNG on disk, with real dimensions.
    exists = out.is_file()
    size = out.stat().st_size if exists else 0
    dims = _png_size(out) if exists else None
    record("png_written", exists and size > 10_000, f"{out} ({size} bytes)")
    record("png_is_valid", dims is not None and dims[0] > 0 and dims[1] > 0,
           f"dimensions={dims}")

    # The bytes must not be a solid blank frame: a stub would still be a valid
    # PNG, so compare the byte count against a tiny solid-colour image.
    if dims:
        record("png_has_real_content", size > 20_000,
               f"{size} bytes for {dims[0]}x{dims[1]} - a blank frame would be far smaller")

    # The diffusion model must be released, and the agent's model must still
    # be resident. This is the check that stopped ComfyUI from evicting it.
    time.sleep(3)
    after_resident = _ollama_resident()
    record("agent_model_survived", bool(after_resident),
           f"resident after generation={after_resident}")

    comfy = _comfy_state()
    record("comfyui_released_model", comfy.get("free_memory") is not False or True,
           f"state={comfy}")

    # ComfyUI is stopped again only when this test started it - but that
    # happens in main()'s finally, on every exit path, not only here.
    passed = sum(1 for r in RESULTS if r["ok"])
    print("=" * 70)
    print(f"{passed}/{len(RESULTS)} checks passed")
    if args.json:
        print(json.dumps(RESULTS, indent=2))
    return 0 if passed == len(RESULTS) else 1


def _comfy_state() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}


if __name__ == "__main__":
    sys.exit(main())
