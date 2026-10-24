# FastAPI + Pydantic v2: Union Return Type Pitfall

## Problem

FastAPI + Pydantic v2 (used by `fastapi>=0.100`) cannot generate response models from `Union[Response, dict]` return type annotations. This causes a startup crash with:

```
fastapi.exceptions.FastAPIError: Invalid args for response field!
Hint: check that starlette.responses.FileResponse | starlette.responses.JSONResponse
is a valid Pydantic field type.
```

## Trigger

```python
# Crashes at startup
from starlette.responses import FileResponse, JSONResponse

@app.get("/api/export/trace")
async def api_export_trace() -> FileResponse | JSONResponse:
    if not LOG_FILE.exists():
        return JSONResponse({"error": "No trace log"}, status_code=404)
    return FileResponse(LOG_FILE)
```

## Fix

Add `response_model=None` to the decorator to disable Pydantic response model generation from the type annotation:

```python
@app.get("/api/export/trace", response_model=None)
async def api_export_trace():
    if not LOG_FILE.exists():
        return JSONResponse({"error": "No trace log"}, status_code=404)
    return FileResponse(LOG_FILE)
```

## Other Patterns That Fail

```python
# FAILS
@app.get("/data") -> dict | None:

# WORKS
@app.get("/data", response_model=None) -> dict | None:
```

## Session Source

Vision (`github.com/dqikfox/vision`) `live_chat_app.py` line 2865. Patched during THRONE session 2026-08-17. The file uses many `-> JSONResponse` annotations that work fine, but `-> FileResponse | JSONResponse` crashes because Pydantic v2 cannot model `FileResponse` as a schema field.

## Verification

After patching, restart the server and verify no startup error. The endpoint should return either a file download or a JSON error response without FastAPI trying to validate either against a Pydantic model.
