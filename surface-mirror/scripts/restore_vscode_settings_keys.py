"""Restore the user-scoped VS Code keys that the settings generator dropped.

VS Code's Local History (User/History) keeps every saved version of a file
that was open in an editor. It recovered two keys the fixed-key-set
generator silently removed:

    "@azure.argTenant": ""            - Azure Account extension placeholder
    "chat.byokUtilityModelDefault": "mainAgent"  - native chat BYOK routing

Both are unmanaged by the generator, so the generator's merge path now
preserves them once they are back in the file.
"""
import json
import os

P = os.path.expandvars(r"%APPDATA%\Code\User\settings.json")

RESTORE = {
    "@azure.argTenant": "",
    "chat.byokUtilityModelDefault": "mainAgent",
}

with open(P, encoding="utf-8") as fh:
    data = json.load(fh)

added = []
for key, value in RESTORE.items():
    if key not in data:
        data[key] = value
        added.append(key)

if not added:
    print("nothing to restore; both keys already present")
else:
    with open(P, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)
        fh.write("\n")
    print("restored:", ", ".join(added))

with open(P, encoding="utf-8") as fh:
    check = json.load(fh)
print("total keys :", len(check))
print("theme      :", check.get("workbench.colorTheme"))
print("hermesAgent:", len([k for k in check if k.startswith("hermesAgent")]), "keys")
print("acp        :", list((check.get("acp.agents") or {}).keys()))
for key in RESTORE:
    print("  %-32s = %s" % (key, json.dumps(check.get(key))))
