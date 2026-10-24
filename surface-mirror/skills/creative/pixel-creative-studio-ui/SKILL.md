---
name: pixel-creative-studio-ui
category: creative
description: First-load avatar+theme designer for local creative studios.
trigger: Build first-load designer, avatar system, or multi-theme visual polish.
---

# Pixel Creative Studio UI

Always-on rules for building the first-load designer, adaptive themes, avatar generation/upload preview, and visual system for a local creative studio.

## Core philosophy
- Simple, stylish, functional. No glitchy or overdone visual effects.
- Trust the design judgment of the implementer; do not replicate external looks unless explicitly asked.
- When the user says "KEEP BUILDING" or gives a vague continuation, identify the weakest/most-prominent gap and ship the next high-leverage set of features without asking.
- Production-grade at every step: verification + test + screenshot + commit + push after significant work.

## First-load designer (mandatory pattern)
1. Show a centered modal on first visit (localStorage flag `pixel-designer-seen`).
2. Live preview pane (avatar stage) that instantly reflects theme, color, and avatar choices.
3. Two avatar paths at the top: "Generate character" (calls local gen-image pipeline) and "Upload a photo" (DataURL preview, then real upload on enter).
4. 6+ adaptive themes with distinct palettes that recolor the entire studio via CSS variables on `:root`.
5. 5 accent colors with large swatches.
6. "Enter" applies the chosen theme/avatar to the main workspace, persists the avatar via existing `/api/avatar`, saves theme prefs, and never shows the designer again.
7. Skip button always available; flag is set on skip or enter.

## Theme system
- Themes are applied via `data-theme` on the stage and `:root[data-theme=NAME]` CSS variables.
- Each theme defines `--robot-light`, `--robot-dark`, `--bg`, `--panel`.
- Theme buttons must show `.active` state.
- The main avatar stage and designer preview must stay in sync.

## Avatar handling
- Generate path: queue `gen-image` job with a clean stylized prompt, poll until `completed`, use `resultAssetId` URL as preview.
- Upload path: FileReader DataURL for instant preview; on enter, convert to blob and POST to `/api/avatar`.
- Photo mode sets `data-avatar="photo"` and hides the SVG robot.
- Removing the photo falls back to the robot with original tagline.

## Pitfalls
- Designer SVG must be self-contained (inline defs) — never reference external `<defs>` or symbols that may be missing.
- Do not show the designer on subsequent loads; the localStorage flag is authoritative.
- When generating an avatar via the designer, surface honest status messages; do not block the UI for the full render.
- Theme changes must update both the designer preview and (after enter) the main stage in one consistent operation.
- Grep the test tree for the exact symbol before widening any helper signature that the designer or avatar flow touches — hand-rolled mocks reimplement the old shape.

## Verification checklist (always run)
- 33/33 tests green
- Live server responds with `localVideoGen: True` and correct `llmBackend`
- Designer modal opens on first load, preview updates live, enter applies changes
- Screenshot of the designer + main studio after theme/avatar application
- Commit + push with a message that names the delivered capability

## References
- references/first-load-designer.md — decision table for avatar generation vs upload flow
- references/theme-palette.md — the six canonical palettes and their variable values