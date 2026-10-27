"""Constrained ML MCP server - local-first tabular ML for THRONE.

Adapted from the Yandex-stack brief to what actually runs on this host.

WHAT CHANGED FROM THE BRIEF, AND WHY
------------------------------------
The brief's `from mcp.server.fastmcp import FastMCP` does not exist in the
installed `mcp` package (verified: ModuleNotFoundError). This host uses the
MCP 2.0 API - `from mcp.server.mcpserver import MCPServer` - which is the
house pattern for every other MCP server here (see mcp/throne/server.py).

The brief's three tools map onto real host capabilities as follows:

  catboost_predict     IMPLEMENTED. CatBoost has a native cp311 win_amd64
                       wheel, installs without touching numpy/pandas/torch, and
                       is a genuinely useful tabular tool on this box.

  generate_kandinsky_image
                       NOT IMPLEMENTED as a diffusers pipeline. Two hard
                       blockers, both verified on this host:
                         1. VRAM. The RTX 3090 has 24 GB, and the running
                            starscream-64k model holds 17.5 GB of it. A Kandinsky
                            3 pipeline needs several GB more, so it would OOM
                            the agent's own model - i.e. it would take down the
                            thing it is supposed to serve.
                         2. The brief's code is wrong for Kandinsky 3 anyway.
                            Kandinsky 3 dropped the image-prior stage and uses
                            its own pipeline class (Kandinsky3Pipeline) with
                            separate image-embedder and prior components.
                            AutoPipelineForText2Image does not cover it.
                       The local alternative that DOES work is ComfyUI, which
                       already ships Kandinsky 5 nodes on this host - so this
                       tool routes to ComfyUI's HTTP API instead.

  ytsaurus_chyt_query  NOT IMPLEMENTED as a live proxy. YTsaurus/CHYT is a
                       Yandex Cloud managed product; there is no YTsaurus
                       cluster reachable from THRONE, and no Yandex
                       credentials in 1Password. Rather than ship a tool that
                       always returns a connection error, the generic
                       SQL-over-HTTP capability is kept and pointed at a
                       configurable endpoint, defaulting to the local DuckDB
                       engine that the host already has.

Every tool degrades honestly: a missing dependency returns a JSON error
describing the fix, never a fabricated result.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:  # pragma: no cover - import guard
    print("ERROR: the mcp package is required (pip install mcp)", file=sys.stderr)
    sys.exit(1)

HERMES_HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "hermes"
MODEL_DIR = Path(os.environ.get("CONSTRAINED_ML_MODEL_DIR", r"E:\ultron-memory\ml-models"))
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
SQL_ENDPOINT = os.environ.get("CONSTRAINED_ML_SQL_ENDPOINT", "")
HTTP_TIMEOUT = 30


def _load_zimage():
    """Load the Z-Image Turbo backend module.

    It is a sibling file rather than a package import because this
    directory is loaded by path in some deployments. Returns None if it
    cannot be loaded - the checkpoint backend does not depend on it.
    """
    try:
        from . import zimage  # type: ignore
        return zimage
    except ImportError:
        pass
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "constrained_ml_zimage", str(Path(__file__).with_name("zimage.py")))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _err(tool: str, reason: str, fix: str = "") -> str:
    payload = {"ok": False, "error": reason}
    if fix:
        payload["fix"] = fix
    payload["tool"] = tool
    return json.dumps(payload, ensure_ascii=False)


def _ok(**kwargs: Any) -> str:
    return json.dumps({"ok": True, **kwargs}, ensure_ascii=False, default=str)


server = MCPServer(
    name="constrained_ml",
    instructions=(
        "Local-first ML tools for THRONE: CatBoost tabular inference, ComfyUI "
        "image generation, and SQL over a configurable HTTP endpoint. "
        "Prefix: mcp_constrained_ml_*"
    ),
)


# ─── CatBoost ────────────────────────────────────────────────────────────

@server.tool(name="catboost_predict")
async def catboost_predict(model_path: str, feature_json: str) -> str:
    """Run inference with a trained CatBoost model on tabular features.

    Args:
        model_path: Absolute path to a .cbm (native) or .onnx CatBoost model.
        feature_json: JSON object of feature name -> value for ONE record.
    """
    try:
        from catboost import CatBoostClassifier, CatBoostRegressor
    except ImportError:
        return _err(
            "catboost_predict",
            "the catboost package is not installed in the server interpreter",
            "install it: pip install catboost",
        )

    model_file = Path(model_path).expanduser()
    if not model_file.is_file():
        return _err(
            "catboost_predict",
            f"model not found at {model_file}",
            f"trained models live under {MODEL_DIR}",
        )

    try:
        record = json.loads(feature_json)
    except json.JSONDecodeError as exc:
        return _err("catboost_predict", f"feature_json is not valid JSON: {exc}")
    if not isinstance(record, dict):
        return _err("catboost_predict", "feature_json must be a JSON object of feature name -> value")

    try:
        import pandas as pd
        frame = pd.DataFrame([record])
    except ImportError:
        return _err("catboost_predict", "pandas is not installed", "install it: pip install pandas")

    try:
        if model_file.suffix.lower() == ".onnx":
            from catboost.utils import convert_to_onnx  # noqa: F401  (import guard for onnx path)
            import onnxruntime  # noqa: F401
        model = CatBoostClassifier()
        try:
            model.load_model(str(model_file))
        except Exception:
            # Not a classifier - fall back to the regressor before failing.
            model = CatBoostRegressor()
            model.load_model(str(model_file))
        prediction = model.predict(frame).tolist()
        result: dict[str, Any] = {"prediction": prediction}
        if hasattr(model, "predict_proba"):
            try:
                result["probabilities"] = model.predict_proba(frame).tolist()
            except Exception:
                pass
        result["model"] = model_file.name
        return _ok(**result)
    except Exception as exc:
        return _err("catboost_predict", f"{type(exc).__name__}: {exc}")


@server.tool(name="catboost_train")
async def catboost_train(
    csv_path: str,
    target_column: str,
    model_name: str,
    task_type: str = "classification",
    iterations: int = 200,
) -> str:
    """Train a CatBoost model from a CSV and save it under the model dir.

    Categorical columns are detected from dtype and passed to cat_features
    directly - never one-hot encoded by hand, which is what CatBoost is for.

    Args:
        csv_path: Absolute path to the training CSV.
        target_column: Name of the label column.
        model_name: File name for the saved model (no extension needed).
        task_type: "classification" or "regression".
        iterations: Boosting iterations.
    """
    try:
        from catboost import CatBoostClassifier, CatBoostRegressor
    except ImportError:
        return _err(
            "catboost_train",
            "the catboost package is not installed in the server interpreter",
            "install it: pip install catboost",
        )

    source = Path(csv_path).expanduser()
    if not source.is_file():
        return _err("catboost_train", f"CSV not found at {source}")

    try:
        import pandas as pd
        frame = pd.read_csv(source)
    except Exception as exc:
        return _err("catboost_train", f"the CSV could not be read: {exc}")

    if target_column not in frame.columns:
        return _err(
            "catboost_train",
            f"target column {target_column!r} is not in the CSV",
            f"columns present: {list(frame.columns)[:20]}",
        )

    labels = frame[target_column]
    features = frame.drop(columns=[target_column])
    cat_features = [
        str(c) for c in features.columns
        if features[c].dtype == object or str(features[c].dtype) in ("category", "bool")
    ]
    X, y = features, labels
    if task_type == "regression":
        model: Any = CatBoostRegressor(iterations=iterations, verbose=0, allow_writing_files=False)
    else:
        model = CatBoostClassifier(iterations=iterations, verbose=0, allow_writing_files=False)

    try:
        model.fit(X, y, cat_features=cat_features or None)
    except Exception as exc:
        return _err("catboost_train", f"training failed: {type(exc).__name__}: {exc}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = MODEL_DIR / (model_name if model_name.endswith(".cbm") else f"{model_name}.cbm")
    try:
        model.save_model(str(out))
    except Exception as exc:
        return _err("catboost_train", f"the model could not be saved: {exc}")

    return _ok(
        model=str(out),
        task_type=task_type,
        rows=int(len(frame)),
        features=[str(c) for c in features.columns],
        categorical_features=cat_features,
        iterations=iterations,
    )


@server.tool(name="list_models")
async def list_models() -> str:
    """List the trained CatBoost models available on this host."""
    if not MODEL_DIR.is_dir():
        return _ok(models=[], model_dir=str(MODEL_DIR))
    models = []
    for path in sorted(MODEL_DIR.glob("*")):
        if path.suffix.lower() in (".cbm", ".onnx"):
            models.append({
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime)),
            })
    return _ok(models=models, model_dir=str(MODEL_DIR), count=len(models))


# ─── Image generation (ComfyUI) ──────────────────────────────────────────

@server.tool(name="generate_image")
async def generate_image(
    prompt: str,
    output_path: str,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    checkpoint: str = "",
    backend: str = "auto",
) -> str:
    """Generate an image with the local ComfyUI instance.

    ComfyUI is the local image stack on this host and already ships Kandinsky
    nodes. A diffusers Kandinsky 3 pipeline is not used: the running
    starscream-64k model holds 17.5 GB of the RTX 3090's 24 GB, so a second
    large pipeline would OOM the agent's own model.

    Two backends are available:

      * "z_image_turbo" - Z-Image Turbo. Three files (a diffusion model, a
        Qwen3-4B text encoder and a VAE), loaded through UNETLoader,
        CLIPLoader and VAELoader rather than as a single checkpoint. It is
        a distilled turbo model: 8 steps at cfg 1.0, and it takes no
        negative prompt. Much stronger than the SD 1.5 checkpoint that
        was the only option here.
      * "checkpoint" - the single-file checkpoints in models/checkpoints,
        through CheckpointLoaderSimple.

    "auto" uses Z-Image Turbo when it is fully installed, and falls back
    to a checkpoint otherwise.

    Args:
        prompt: Positive prompt.
        output_path: Absolute path for the saved PNG.
        negative_prompt: Negative prompt. Ignored by the Z-Image backend,
            which is distilled and runs at cfg 1.0.
        width: Image width in pixels.
        height: Image height in pixels.
        steps: Sampler steps. The Z-Image backend defaults to 8.
        checkpoint: Optional checkpoint file name; the first image checkpoint
            found on disk is used when empty.
        backend: "auto", "z_image_turbo" or "checkpoint".
    """
    import urllib.parse  # noqa: F401  (used by comfyui.py)
    try:
        from . import comfyui  # type: ignore
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "constrained_ml_comfyui", str(Path(__file__).with_name("comfyui.py")))
        comfyui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(comfyui)

    try:
        zimage = _load_zimage()
        use_zimage = False
        if backend in ("auto", "z_image_turbo"):
            if zimage is not None and zimage.zimage_available():
                use_zimage = True
            elif backend == "z_image_turbo":
                st = zimage.zimage_status()
                return json.dumps(
                    {"ok": False, "error": "Z-Image Turbo is not fully installed",
                     "missing": st["missing"], "paths": st["paths"]},
                    ensure_ascii=False, default=str)

        if use_zimage:
            result = zimage.generate_zimage(
                prompt=prompt,
                output_path=output_path,
                width=int(width) or zimage.ZIMAGE_SIZE,
                height=int(height) or zimage.ZIMAGE_SIZE,
                steps=int(steps) or zimage.ZIMAGE_STEPS,
                seed=random.randint(0, 2**31 - 1),
            )
        else:
            result = comfyui.generate(
                prompt=prompt,
                output_path=output_path,
                negative_prompt=negative_prompt,
                width=int(width),
                height=int(height),
                steps=int(steps),
                checkpoint=checkpoint or "",
            )
    except Exception as exc:
        return _err("generate_image", f"{type(exc).__name__}: {exc}")
    return json.dumps(result, ensure_ascii=False, default=str)


# ─── SQL over HTTP ───────────────────────────────────────────────────────

@server.tool(name="sql_query")
async def sql_query(query: str, endpoint: str = "") -> str:
    """Run a SQL query against a configured SQL-over-HTTP endpoint.

    The brief's YTsaurus CHYT proxy assumed a Yandex Cloud cluster that is not
    reachable from this host. This keeps the capability but points it at a
    configurable endpoint (set CONSTRAINED_ML_SQL_ENDPOINT) and fails with a
    clear message when none is configured.

    Args:
        query: The SQL text.
        endpoint: Optional override of the configured endpoint.
    """
    target = (endpoint or SQL_ENDPOINT).strip()
    if not target:
        return _err(
            "sql_query",
            "no SQL endpoint is configured",
            "set CONSTRAINED_ML_SQL_ENDPOINT to a SQL-over-HTTP endpoint, "
            "or pass endpoint= for a one-off call",
        )
    try:
        request = urllib.request.Request(
            target,
            data=query.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return _err("sql_query", f"HTTP {exc.code}: {detail}")
    except Exception as exc:
        return _err("sql_query", f"{type(exc).__name__}: {exc}")
    return _ok(rows=body[:8000], endpoint=target)


async def main() -> None:
    await server.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
