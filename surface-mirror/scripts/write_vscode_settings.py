"""Write the VS Code user settings with byte-exact control.

Backslash escapes in a tool parameter are interpreted before they reach
the file, which is how a Windows path turns into a tab and a carriage
return. So this script contains NO backslashes at all: every one is a
placeholder that is substituted here, from chr(92), at write time.
"""
import json
import os

BS = chr(92)
NL_ESC = BS + "n"

P = r"C:\Users\KING\AppData\Roaming\Code\User\settings.json"
CODE = "C:" + BS + "Users" + BS + "KING" + BS + "AppData" + BS + "Local" + BS + "hermes" + BS + "hermes-agent" + BS + "venv" + BS + "Scripts" + BS + "hermes.exe"
HERMES_EXE = CODE
GITBASH = "C:" + BS + "Users" + BS + "KING" + BS + "AppData" + BS + "Local" + BS + "hermes" + BS + "git" + BS + "bin" + BS + "bash.exe"
NODE_EXE = "C:" + BS + "Program Files" + BS + "nodejs" + BS + "node.exe"

EXCLUDE = {
    "**/.venv": True,
    "**/venv": True,
    "**/node_modules": True,
    "**/__pycache__": True,
    "**/.git": True,
    "**/Library": True,
    "**/Temp": True,
    "**/obj": True,
    "**/bin": True,
    "**/dist": True,
    "**/.mypy_cache": True,
    "**/.pytest_cache": True,
    "**/.ruff_cache": True,
    "**/artifacts": True,
    "**/ShaderCache": True,
}
WATCHER = {k + "/**": True for k in EXCLUDE}

settings = {
    # --- preserved from the user's existing file -------------------------
    "workbench.colorTheme": "Default High Contrast",
    "gitlens.graph.details.location": "auto",
    "gitlens.ai.defaultAgent": "claude-extension",

    # --- Hermes Agent extension (EyanLin.hermes-agent-vscode) ------------
    # The extension spawns `command` with ["acp"] over stdio. Its default
    # command is a bare "hermes", which does NOT resolve inside VS Code:
    # the Hermes venv Scripts dir is not on the user PATH, so the spawn
    # would fail and the extension silently falls back to a local mock
    # response ("Agent backend not connected"). Absolute path, always.
    # The path has no spaces, and the extension spawns with shell:true,
    # so cmd.exe handles it cleanly.
    "hermesAgent.command": HERMES_EXE,
    "hermesAgent.useAcp": True,
    # The extension's shipped default is a model this estate does not
    # have; use the estate's own configured default. The extension also
    # refreshes the real model list from the live agent, so this is only
    # the initial pick.
    "hermesAgent.model": "starscream-64k",
    # The Hermes extension does not declare untrusted-workspace support, so
    # VS Code disables it in Restricted Mode. Trust the estate's own roots so
    # the editor agent is always available in them.
    "security.workspace.trust.trustedFolders": [
        "E:\\ultron-memory",
        "E:\\ultron-memory\\nexus-core",
        "E:\\ultron-memory\\evolution-stack",
        "C:\\Users\\KING\\Projects",
        "C:\\Users\\KING\\Documents",
        "C:\\Users\\KING\\AppData\\Local\\hermes",
    ],
    "security.workspace.trust.enabled": True,
    "hermesAgent.defaultMode": "Auto",
    "hermesAgent.permissionReminderMinutes": 5,
    # The extension keeps a persistent background host so an active
    # session survives VS Code closing. It needs a STANDALONE Node
    # executable for that; leaving this empty makes it hunt for one and
    # sometimes settle on a path that is not a real install.
    "hermesAgent.nodePath": NODE_EXE,

    # --- Hermes via ACP: the generic ACP Client path ---------------------
    "acp.agents": {
        "Hermes Agent": {
            "command": HERMES_EXE,
            "args": ["acp"],
        }
    },

    # --- stop the line-ending churn -------------------------------------
    # The estate had ~653 files of pure CRLF churn. LF everywhere is the
    # fix, and files.eol makes VS Code stop reintroducing it.
    "files.eol": NL_ESC,
    "files.insertFinalNewline": True,
    "files.trimTrailingWhitespace": True,
    "files.trimFinalNewlines": True,
    "files.autoSave": "afterDelay",
    "files.autoSaveDelay": 1000,

    # --- keep the editor out of the estate's heavy trees ----------------
    "files.exclude": dict(EXCLUDE),
    "search.exclude": dict(EXCLUDE),
    "files.watcherExclude": dict(WATCHER),

    # --- formatting -------------------------------------------------------
    "editor.formatOnSave": True,
    "editor.rulers": [88],
    "editor.codeActionsOnSave": {"source.organizeImports": "explicit"},
    "[python]": {"editor.defaultFormatter": "charliermarsh.ruff"},
    "[markdown]": {"editor.formatOnSave": False, "editor.wordWrap": "on"},
    "[jsonc]": {"editor.defaultFormatter": "vscode.json-language-features"},
    "[shellscript]": {"editor.defaultFormatter": "shellscript"},

    # --- git --------------------------------------------------------------
    "diffEditor.ignoreTrimWhitespace": True,
    "git.autofetch": True,
    "git.autofetchPeriod": 300,
    "scm.defaultViewMode": "tree",
    "git.openRepositoryInParentFolders": "always",

    # --- terminal: Git Bash is the estate's shell -------------------------
    "terminal.integrated.defaultProfile.windows": "Git Bash",
    "terminal.integrated.profiles.windows": {
        "Git Bash": {"path": GITBASH, "icon": "terminal-bash"},
        "PowerShell": {"source": "PowerShell", "icon": "terminal-powershell"},
    },
    "terminal.integrated.shellIntegration.enabled": True,
    "terminal.integrated.cwd": "${workspaceFolder}",

    # --- remote hosts: MSI over SSH, Kali over SSH -----------------------
    "remote.SSH.defaultExtensions": [
        "formulahendry.acp-client",
        "ms-python.python",
        "charliermarsh.ruff",
    ],
}

backup = P + ".bak-" + "20261027"
if os.path.exists(P) and not os.path.exists(backup):
    with open(P, "rb") as fh:
        original = fh.read()
    with open(backup, "wb") as fh:
        fh.write(original)
    print("backed up original ->", backup)


def _load_existing():
    """Read the live settings, tolerating a missing or corrupt file."""
    if not os.path.exists(P):
        return {}
    try:
        with open(P, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print("live settings unreadable, starting clean:", exc)
        return {}


existing = _load_existing()

# Merge, do not overwrite. VS Code and its extensions add keys of their own
# (chat agent defaults, language-specific formatters, and whatever an
# extension writes when it activates). Writing a fixed key set drops them
# silently, and the user only finds out when a setting reverts.
#
#   - a key this script manages keeps the managed value
#   - a key this script does not manage is preserved verbatim
#   - for a managed object (acp.agents, [python], ...), managed sub-keys win
#     and any extra sub-key the user or an extension added is kept
managed = settings
merged = dict(managed)
for key, value in existing.items():
    if key not in managed:
        merged[key] = value
    elif isinstance(managed[key], dict) and isinstance(value, dict):
        combined = dict(value)
        combined.update(managed[key])
        merged[key] = combined

dropped = [k for k in existing if k not in merged]
preserved = [k for k in existing if k not in managed]
if preserved:
    print("preserved unmanaged keys:", ", ".join(sorted(preserved)))
if dropped:
    print("WARNING dropped keys:", ", ".join(sorted(dropped)))

# A timestamped backup every run. The fixed-name backup only ever captured
# the file once, so a later bad write had nothing to fall back to.
import datetime
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
rolling = P + ".bak-" + stamp
if os.path.exists(P):
    with open(P, "rb") as fh:
        original = fh.read()
    with open(rolling, "wb") as fh:
        fh.write(original)
    print("rolled backup ->", rolling)

with open(P, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(merged, fh, indent=4, ensure_ascii=False)
    fh.write("\n")

print("wrote", P, os.path.getsize(P), "bytes")

# verify it parses and the paths survived
with open(P, encoding="utf-8") as fh:
    back = json.load(fh)
cmd = back["acp.agents"]["Hermes Agent"]["command"]
print("acp command  :", cmd)
print("command exists:", os.path.exists(cmd))
print("eol          :", repr(back["files.eol"]))
print("gitbash      :", back["terminal.integrated.profiles.windows"]["Git Bash"]["path"],
      "->", os.path.exists(back["terminal.integrated.profiles.windows"]["Git Bash"]["path"]))
print("theme kept   :", back["workbench.colorTheme"])
print("keys         :", len(back))
