# Dependency Discovery via Import Scanning

When `requirements.txt` or `pyproject.toml` are missing, follow this pattern to rebuild the environment:

1. **Identify Target Files**: Use `search_files(pattern="*.py", target="files")` to find all Python files in the project scope.
2. **Extract Imports**: Use `read_file` on discovered files and use a regular expression (e.g., `r"^(?:from|import)\s+([a-zA-Z0-9_]+)"`) to extract top-level module names.
3. **Filter Standard Library**: Use `sys.builtin_module_names` or common knowledge to filter out built-ins and only focus on third-party packages (e.g., `pandas`, `requests`, `numpy`).
4. **Verify against Environment**: Check the existing `.venv` using `uv pip list` to see which imported modules are already satisfied.
5. **Install Missing**: Use `uv pip install <package>` for any discrepancies found.

## Example Regex/Python Snippet for Scanning:
```python
import re
import pathlib

def get_third_party_imports(directory):
    found = set()
    for path in pathlib.Path(directory).rglob("*.py"):
        content = path.read_text()
        matches = re.findall(r"^(?:from|import)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE)
        found.update(matches)
    return found
```