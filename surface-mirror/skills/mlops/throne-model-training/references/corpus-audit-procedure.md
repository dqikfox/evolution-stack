# Corpus audit — finding training roots on a personal Windows box

How to enumerate every plausible SFT training root on THRONE before designing the harvest. Done once per machine, then re-run when a new top-level folder appears.

## Why this matters

Training data lives in more places than `Projects\`. A user-curated `unsloth_data/` directory in `Documents\` carries more signal than 1,946 files of auto-generated nexus-core notes. An audit pass before the first harvest surfaces sources the original pipeline missed.

## Procedure

### 1. Enumerate top-level directories under `C:\Users\<user>\`

```powershell
Get-ChildItem 'C:\Users\KING' -Directory |
  Select-Object Name,
    @{N='Size_MB'; E={ [math]::Round(
        ((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
          Measure-Object Length -Sum).Sum) / 1MB, 1) }},
    @{N='Files';  E={ (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue).Count }} |
  Sort-Object Size_MB -Descending |
  Format-Table -AutoSize
```

The user home is the canonical starting point. Each subdirectory at the first level is a candidate root.

### 2. Then `Documents\` and any other large tree

```powershell
Get-ChildItem 'C:\Users\KING\Documents' -Directory |
  Select-Object Name, @{N='Size_MB'; E={...}}, @{N='Files'; E={...}} |
  Sort-Object Size_MB -Descending | Format-Table -AutoSize
```

`Documents\` is where users keep personal scratch — Obsidian vaults, code-experiment folders, AI CLI session workspaces, training data they curated by hand. It deserves first-class attention.

### 3. For each candidate, sample content to classify

For each non-trivial subfolder, do a 3-level peek:

```powershell
Get-ChildItem '<path>' -Recurse -Depth 3 -File |
  Where-Object { $_.Extension -in '.md','.txt','.json','.py','.yaml','.yml','.toml','.ps1','.sh','.cmd','.ts','.tsx','.js','.jsx' } |
  Select-Object -First 10 FullName, Length |
  Format-Table -AutoSize
```

Classify each folder by the dominant file types and reading a few heads:

| Folder signal | Classification |
|---|---|
| Lots of `.md` with a `LLM Memory Index.md`, `Dashboard.md`, `Home.md` | Obsidian vault — high-signal notes |
| `.json` corpus dumps + `OPUS_CHANGELOG.md` + `HITCHYZ_OPUS.md` | Alchemy-style research corpus |
| `00_dataset_manifest.txt` + `01_user_system_profile.txt` + `04_*_persona_*` + `99_*_private_corpus.txt` | Purpose-built SFT data — highest impact per byte |
| `package-lock.json` dominating + `node_modules` 800+ MB + scattered `.ts/.tsx` | AI CLI session workspace (Codex CLI etc.) — filter node_modules |
| Lots of `.glb`/`.prefab` (Unity assets) | Skip — binary, no training signal |
| `.ps1` scripts + `.md` lessons | High-signal PowerShell lessons |
| `dist/`, `build/`, `.next/`, `node_modules/` | Skip — generated output |

### 4. Decide which to add to the harvest

For each high-signal folder, write a tuple into `01_harvest.py`'s `SOURCES` list:

```python
(root_path, kind_label, max_bytes_per_file, exts_override_or_None)
```

`exts_override` is required when the source has a non-default extension mix (e.g., `Codex` needs `.ts/.tsx/.js`; `unsloth_data` is `.txt`-only).

### 5. Pitfalls specific to this audit

- **Get-ChildItem -Recurse on `E:\ultron-memory\papers` hangs** — 10 GB of PDFs / thousands of files. Always time-bound the walk; use depth limits or sample the top-level only.
- **`Get-CimInstance` on `Win32_Process` returns a flat string array, not a hashtable** — filter with `Where-Object { $_ -match 'OLLAMA_' }`, never index by name.
- **`os.walk` and `Get-ChildItem -Recurse` on the SAME path produce different orderings** — rely on a sort step in the consumer, not on enumeration order.
- **Don't trust folder names alone** — `Codex`, `Obsidian`, and `.claudian` are all app-cache or session-fragment folders in disguise. Always sample before adding to the harvest.
- **A folder's name can hide its purpose** — `Documents\characters\` looked like roleplay notes but turned out to be Unity `.glb`/`.prefab` binary assets. Always classify by content, not name.
- **Skip `.obsidian`, `.copilot`, `.openai`, `.sites-runtime`** — these are app config and downloaded model catalogs. KEEP `.claudian` because it can hold conversation fragments.
- **Python triple-quoted string with `C:\Users\...` triggers `\U` unicode-escape error** — `'unicodeescape' codec can't decode bytes ... truncated \UXXXXXXXX escape`. Use a raw string (`r"""..."""`) or escape backslashes (`"C:\\Users\\..."`). Applies to any Python literal that embeds Windows paths.

## Output: the canonical source list on THRONE (verified 2026-09-29)

After running this audit on THRONE, the canonical training roots are 16 sources across `Projects\`, `Documents\`, `AppData\`, and `E:\ultron-memory\`. See `SKILL.md` § "Pick the corpus roots" for the full table.

The audit found:
- 4,068 files / 57.4 MB harvested (vs 3,063 / 43.9 MB before the audit — a +33% uplift)
- 10M training tokens (vs 8.2M — a +22% uplift)
- One missing source (`unsloth_data/`) that turned out to be the highest-impact source per byte
