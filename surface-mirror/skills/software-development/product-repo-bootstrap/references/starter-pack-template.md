# Starter pack template

Use this as the skeleton for any new `starter_pack_<name>()` function in `lib/starter_packs.sh`. Copy + adapt. Place the new function BEFORE `apply_starter_pack()`.

```bash
starter_pack_<name>() {
    local repo_path="$1" package="$2"

    # ----- 1. Create the directory tree -----
    mkdir -p "$repo_path/src/$package"/{subpkg1,subpkg2,training}
    mkdir -p "$repo_path"/{docs,scripts,tests,assets}

    # ----- 2. Write each file via heredoc -----
    # IMPORTANT: use <<'EOF2' (single-quoted) so $variables in the generated
    # code are NOT substituted by bash. The EOF2 marker is the convention used
    # throughout idea-forge.

    cat > "$repo_path/src/$package/__init__.py" <<'EOF2'
"""<Product name> — <one-line description>."""
__version__ = "0.1.0"
EOF2

    cat > "$repo_path/src/$package/engine.py" <<'EOF2'
"""Core engine: <responsibilities>."""

def hello() -> str:
    return "hello from <name>"
EOF2

    # ----- 3. CLI + server entrypoints (if applicable) -----
    cat > "$repo_path/src/$package/cli.py" <<'EOF2'
import argparse
from .engine import hello

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="world")
    args = ap.parse_args()
    print(hello())
EOF2

    cat > "$repo_path/src/$package/server.py" <<'EOF2'
"""HTTP server: <endpoints>."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

class H(BaseHTTPRequestHandler):
    def log_message(self, *a, **k): pass
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200); self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8511), H)
    server.serve_forever()
EOF2

    # ----- 4. Tests -----
    cat > "$repo_path/tests/test_engine.py" <<'EOF2'
from <package>.engine import hello

def test_hello():
    assert hello() == "hello from <name>"
EOF2

    cat > "$repo_path/tests/test_smoke.py" <<'EOF2'
def test_smoke():
    assert True
EOF2

    # ----- 5. Brand-bible style doc (optional, recommended for products) -----
    cat > "$repo_path/docs/BIBLE.md" <<'EOF2'
# <Product name>

<one-paragraph story + brand summary>

## What ships
- <feature 1>
- <feature 2>
EOF2

    # ----- 6. .gitignore (only if missing) -----
    [ -f "$repo_path/.gitignore" ] || cat > "$repo_path/.gitignore" <<'EOF2'
# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Lummings-style
*.sqlite
*.sqlite-journal
EOF2
}
```

## Common patterns

### Multiple files, single function

Each `cat > path <<'EOF2' ... EOF2` block is independent. A starter pack with 20 files = 20 heredoc blocks.

### Subpackages

For products with multiple subpackages, put each in its own subdirectory and `cat` the files into `$repo_path/src/$package/subpkg/`.

### Data files (JSON / YAML)

Same heredoc pattern, but the EOF body is JSON. No interpolation issues since `EOF2` disables `$`.

```bash
cat > "$repo_path/data/config.json" <<'EOF2'
{
  "version": "1.0",
  "name": "<product>"
}
EOF2
```

### Binary files

Heredocs cannot write binary reliably. If the product needs a small binary asset (icon, sound), skip it in the starter pack and add a `assets/README.md` explaining how to add it. Generate PNGs/SVGs via Python at runtime or check them into git after bootstrap.

## Verification recipe

After writing the starter pack function:

```bash
# 1. doctor says clean
bash bin/forge doctor <repo>

# 2. bootstrap to a temp dir
bash bin/forge bootstrap <repo> --root /tmp/test --owner dqikfox --no-github

# 3. Smoke test
cd /tmp/test/<repo>
python -m pip install -e .
python -m pytest tests/ -v
python -m <package> --help
```
