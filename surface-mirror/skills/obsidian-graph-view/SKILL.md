---
name: obsidian-graph-view
description: Use when building an Obsidian-style force-directed graph.
---

# Obsidian-Style Graph View

A reusable recipe for building an Obsidian-aesthetic force-directed graph in any web project.

## When to use

- You have a graph of notes/entities (nodes + links) and want a visual explorer
- You want Obsidian's aesthetic: dark purple, cyan nodes, violet links
- You need sidebar controls: filters, grouping, display, force tuning
- Single-page HTML + JS, no build step

## Stack

- **D3.js v7** (CDN) — `https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js`
- **Vanilla JS** — no framework, no build
- **CSS variables** — for the dark theme

## Files to create

1. `templates/graph.html` (~155 lines) — page structure + sidebar
2. `static/graph.js` (~550 lines) — D3 force sim + controls
3. `static/graph.css` (~470 lines) — Obsidian dark theme

## Data shape

API endpoint returns:
```json
{
  "nodes": [
    {"id": "slug", "title": "Note Title", "folder": "source", "size": 1234, "tags": ["a", "b"]}
  ],
  "links": [
    {"source": "slug1", "target": "slug2"}
  ]
}
```

`size` controls node radius. `folder` is used for color grouping.

## Aesthetic — copy these CSS variables

```css
:root {
  --bg:           #1e1b2e;   /* deep purple */
  --bg-light:     #2a2740;   /* panel */
  --bg-overlay:   rgba(42, 39, 64, 0.95);
  --text:         #d6d2e8;   /* light lavender */
  --text-dim:     #8a83b8;   /* muted */
  --accent:       #6b4ca8;   /* purple */
  --accent-light: #b794f6;   /* light purple */
  --node:         #4fd1c5;   /* cyan/teal */
  --link:         #6b4ca8;   /* purple */
  --hit:          #fbbf24;   /* yellow for search */
}
```

## Sidebar layout

Four collapsible panels:
1. **Filters** — search input, hide orphans toggle, min degree slider
2. **Groups** — radio: None/Source/Folder/Tag, with live legend
3. **Display** — arrows toggle, text fade threshold, node size, link thickness, Animate button
4. **Forces** — charge strength, link distance, center strength, collide radius

## D3 force setup

```js
const sim = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d => d.id).distance(60).strength(0.5))
  .force('charge', d3.forceManyBody().strength(-180))
  .force('center', d3.forceCenter(w/2, h/2).strength(0.05))
  .force('collide', d3.forceCollide().radius(d => nodeRadius(d) + 5))
  .on('tick', tick);
```

## Arrowhead definition (in SVG <defs>)

```js
defs.append('marker')
  .attr('id', 'arrowhead')
  .attr('viewBox', '0 -5 10 10')
  .attr('refX', 18).attr('refY', 0)
  .attr('markerWidth', 6).attr('markerHeight', 6)
  .attr('orient', 'auto')
  .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#6b4ca8');
```

## Node radius formula

```js
function nodeRadius(d) {
  const base = Math.max(3, Math.min(20, Math.sqrt(d.size || 100) / 8));
  return base * settings.nodeSizeScale;
}
```

## Text fade by distance from center

```js
gNodes.selectAll('text').attr('opacity', d => {
  const dist = Math.hypot((d.x-cx), (d.y-cy)) / maxR;
  return d3.scaleLinear().domain([1+settings.fadeThreshold, 1]).range([0,1]).clamp(true)(dist);
});
```

## Gotchas

- **Q: drive is slow** for big vaults — reindex in background, not sync
- **Chroma dim mismatch** — if you see `expecting 768 got 384`, the reindex wrote to a different collection. Set `DEFAULT_COLLECTION=nexus` explicitly.
- **Open tag on connect** — D3 doesn't fire any "ready" event; call `render()` after `await loadGraph()` resolves
- **Drag pinning** — set `d.fx/d.fy` on drag, clear on timeout so nodes don't get stuck
- **First render = 1,000+ nodes** — set initial positions to a ring or scatter, don't let the simulation start from 0,0

## Time estimates

- HTML structure: 30 min
- CSS theme: 1 hour (matching Obsidian colors is the hard part)
- D3 force setup: 1 hour
- Sidebar controls: 2 hours (the live updates while dragging the slider is the tricky part)
- Bug fixing (Chroma dims, text fade, arrow markers): 1 hour

Total: ~5 hours for a polished version with all the controls.

## Verification

After building:
1. `curl http://127.0.0.1:PORT/graph` → 200, HTML contains all 4 panel names
2. `curl http://127.0.0.1:PORT/static/graph.js` → 200, application/javascript
3. `curl http://127.0.0.1:PORT/static/graph.css` → 200, text/css
4. `curl http://127.0.0.1:PORT/api/vault-graph` → JSON with `nodes` (each has id/title/folder/size/tags) and `links`

All 4 must pass before the page will render correctly.
