# FastAPI Pydantic v2 Union Return Type Pitfall

## Problem

FastAPI route handlers that use Python 3.10+ union syntax for return types (`-> FileResponse | JSONResponse`) crash at startup under Pydantic v2 with:

```
fastapi.exceptions.FastAPIError: Invalid args for response field! Hint: check that
starlette.responses.FileResponse | starlette.responses.JSONResponse
is a valid Pydantic field type. If you are using a return type annotation that is not
a valid Pydantic field (e.g. Union[Response, dict, None]) you can disable generating
the response model from the type annotation with the path operation decorator parameter
response_model=None.
```

## When It Happens

- FastAPI 0.115+ with Pydantic v2
- Route handlers returning different response types conditionally
- Code written for Pydantic v1 (where this worked) or older FastAPI versions

## Example From Vision

Vision's `live_chat_app.py` had this route:

```python
# BEFORE (crashes on startup)
@app.get("/api/export/trace")
async def api_export_trace() -> FileResponse | JSONResponse:
    if not LOG_FILE.exists():
        return JSONResponse({"error": "No trace log available yet"}, status_code=404)
    return FileResponse(LOG_FILE, media_type="text/plain")
```

## Fix

Add `response_model=None` to disable Pydantic response model generation:

```python
# AFTER (works)
@app.get("/api/export/trace", response_model=None)
async def api_export_trace():
    if not LOG_FILE.exists():
        return JSONResponse({"error": "No trace log available yet"}, status_code=404)
    return FileResponse(LOG_FILE, media_type="text/plain")
```

## Why This Works

Pydantic v2 cannot generate a response model from `FileResponse | JSONResponse` because these are not valid Pydantic field types. By setting `response_model=None`, FastAPI skips response model validation and accepts any return type.

## Finding Affected Routes

```bash
# Search for union return types in FastAPI route handlers
grep -n "-> .*|.*Response" live_chat_app.py
```

## Session Source

Discovered during THRONE session 2026-08-17 while launching Vision (`github.com/dqikfox/vision`) as part of NEXUS CORE integration. The error blocked startup until patched.
