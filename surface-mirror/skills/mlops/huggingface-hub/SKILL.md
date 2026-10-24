---
name: huggingface-hub
description: "HuggingFace hf CLI: search/download/upload models, datasets."
version: 1.0.1
author: Hugging Face
license: MIT
tags: [huggingface, hf, models, datasets, hub, mlops]
platforms: [linux, macos, windows]
---

# Hugging Face CLI (`hf`) Reference Guide

The `hf` command is the modern command-line interface for interacting with the Hugging Face Hub, providing tools to manage repositories, models, datasets, and Spaces.

> **IMPORTANT:** The `hf` command replaces the now deprecated `huggingface-cli` command.

## Quick Start
*   **Installation:** `curl -LsSf https://hf.co/cli/install.sh | bash -s`
*   **Help:** Use `hf --help` to view all available functions and real-world examples.
*   **Authentication:** Recommended via `HF_TOKEN` environment variable or the `--token` flag.

---

## Core Commands

### General Operations
*   `hf download REPO_ID`: Download files from the Hub.
*   `hf upload REPO_ID`: Upload files/folders (recommended for single-commit; also handles resumable uploads of large directories).
*   `hf upload-large-folder REPO_ID LOCAL_PATH`: **[Deprecated]** — use `hf upload` instead.
*   `hf sync`: Sync files between a local directory and a bucket.
*   `hf env` / `hf version`: View environment and version details.

### Authentication (`hf auth`)
*   `login` / `logout`: Manage sessions using tokens from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
*   `list` / `switch`: Manage and toggle between multiple stored access tokens.
*   `whoami`: Identify the currently logged-in account.

### Repository Management (`hf repos`)
*   `create` / `delete`: Create or permanently remove repositories.
*   `duplicate`: Clone a model, dataset, or Space to a new ID.
*   `move`: Transfer a repository between namespaces.
*   `branch` / `tag`: Manage Git-like references.
*   `delete-files`: Remove specific files using patterns.

---

## Specialized Hub Interactions

### Datasets & Models
*   **Datasets:** `hf datasets list`, `info`, and `parquet` (list parquet URLs).
*   **SQL Queries:** `hf datasets sql SQL` — Execute raw SQL via DuckDB against dataset parquet URLs.
*   **Models:** `hf models list` and `info`.
*   **Papers:** `hf papers ls` — View daily papers.

### Discussions & Pull Requests (`hf discussions`)
*   Manage the lifecycle of Hub contributions: `list`, `create`, `info`, `comment`, `close`, `reopen`, and `rename`.
*   `diff`: View changes in a PR.
*   `merge`: Finalize pull requests.

### Infrastructure & Compute
*   **Endpoints:** Deploy and manage Inference Endpoints (`deploy`, `pause`, `resume`, `scale-to-zero`, `catalog`).
*   **Jobs:** Run compute tasks on HF infrastructure. Includes `hf jobs uv` for running Python scripts with inline dependencies and `stats` for resource monitoring.
*   **Spaces:** Manage interactive apps. Includes `dev-mode` and `hot-reload` for Python files without full restarts.

### Storage & Automation
*   **Buckets:** Full S3-like bucket management (`create`, `cp`, `mv`, `rm`, `sync`).
*   **Cache:** Manage local storage with `list`, `prune` (remove detached revisions), and `verify` (checksum checks).
*   **Webhooks:** Automate workflows by managing Hub webhooks (`create`, `watch`, `enable`/`disable`).
*   **Collections:** Organize Hub items into collections (`add-item`, `update`, `list`).

---

## Token & Access Diagnostics

When a token is provided but downloads fail with "access restricted" or 401 errors, run this ordered check before concluding the token is invalid:

### 1. Validate the token identity
```bash
# Quick identity check via REST API
curl -s -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2 | jq .
# → {"name":"havikz","fullname":"fox","orgs":[],"type":"user"}
```

### 2. Verify token scope
```bash
# The legacy huggingface-cli (still present in venvs) shows token metadata
huggingface-cli whoami
# → Name: havikz  Token name: xytr  Permission: write  Billing: prepaid
```

### 3. Check gated model access
```bash
# Attempt a HEAD request on a file in a gated repo
curl -sI -H "Authorization: Bearer $HF_TOKEN" \
  https://huggingface.co/meta-llama/Llama-3.1-8B/resolve/main/config.json
# HTTP 200 means approved; HTTP 403 with {"access":"restricted"} means
# the token is valid but the user has not completed the model's gated-access
# request form on huggingface.co.
```

### 4. List user-owned repos
```bash
# Via REST API
curl -s -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/models?author=$(curl -s -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2 | jq -r .name)" \
  | jq -r '.[] | "\(.id)"'

# Via hf CLI
hf repos list --author havikz
```

**Pitfall:** A token with `write` permission can upload and create repos but still cannot download a gated model until the user explicitly requests access on the model card. The error `{"access":"restricted"}` means token-is-good-but-access-not-granted, not token-is-bad.

**Pitfall:** The `huggingface-cli login --token` command stores credentials in git-credential-manager, not just HF cache. On shared machines this can leak across user profiles — prefer `HF_TOKEN` env var for CI/automation and `op item get` for interactive use.

---

## Advanced Usage & Tips

### Global Flags
*   `--format json`: Produces machine-readable output for automation.
*   `-q` / `--quiet`: Limits output to IDs only.

### Extensions & Skills
*   **Extensions:** Extend CLI functionality via GitHub repositories using `hf extensions install REPO_ID`.
*   **Skills:** Manage AI assistant skills with `hf skills add`.