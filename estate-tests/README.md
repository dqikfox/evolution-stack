# Estate tests

The house's real regression suite. These are NOT part of the evolution
loop's mutable surface (`scripts/` and `skills/`) - the loop may rewrite
those, and a rollback there must never be able to take a test with it.

They live in two places on purpose:

- `C:\Users\KING\AppData\Local\hermes\tests\` - where the estate gate
  RUNS them. That directory is protected from the disk-cleanup plugin,
  which otherwise classifies any `test_*` file outside a protected
  top-level tree as disposable and deletes it at session end.
- `estate-tests/` here - where they are VERSIONED. The hermes house
  directory is not a git repository, so without this the suite had no
  history at all.

Keep the two copies in sync. The canonical source is the hermes house
copy; mirror it here after a change.

The suite is real, not mocked:

- `test_ml_stack.py` - a real CatBoost train/predict round trip, the
  model listing, the SQL path, and the error paths, through the live
  `constrained_ml` MCP server.
- `test_image_stack.py` - a real ComfyUI generation through the live
  MCP server, checking the PNG is a real image with real content, that
  the diffusion model is released, and that the agent's own model
  survives it. ComfyUI is always given back, on every exit path.
