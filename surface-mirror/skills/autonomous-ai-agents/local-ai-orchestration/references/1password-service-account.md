# 1Password Service Account — Full Session Reproduction

## Problem Summary

1Password CLI v2.30+ (installed at `C:\Users\KING\bin\op.exe`) cannot be automated via traditional methods because every `--reveal` operation triggers a **fresh Windows Hello biometric prompt** that expires in shell timeouts (15-60s) before the user can respond.

Attempted and failed approaches:
- `op signin --raw` → waits for desktop app auth, times out
- `op read` with desktop integration → same biometric wall
- `op item get --reveal` via PowerShell → same
- GUI automation via `computer_use` → blocked by CUA driver permissions
- Background processes with long timeouts → Windows Hello popup dismissed automatically

## Working Solution: Service Account Token

### Creation Steps

1. Open browser → `https://my.1password.com/developer`
2. Sign in with the 1Password account (same as desktop app)
3. Navigate to **Service Accounts** → **New Service Account**
4. Name: `Megatron-Automation`
5. Grant access to vault(s) containing needed credentials
6. Copy the token (format: `ops_eyJzaWduSW5BZGRyZXNzIjoibXkuMXBhc3N3b3JkLmNvbSIs...`)
7. Store securely on local machine:
   ```powershell
   $token = "ops_..."  # Paste token here
   $token | Out-File -FilePath "$env:USERPROFILE\.ultron\.op_service_account" -Encoding utf8
   icacls "$env:USERPROFILE\.ultron\.op_service_account" /inheritance:r /grant:r "$env:USERNAME:(R)"
   ```

### Usage Pattern

```powershell
$env:OP_SERVICE_ACCOUNT_TOKEN = Get-Content "$env:USERPROFILE\.ultron\.op_service_account"

# Now all op commands work headlessly:
& "C:\Users\KING\bin\op.exe" item get "ITEM_UUID" --vault "vault-name" --reveal
& "C:\Users\KING\bin\op.exe" read "op://vault/item/field"
```

### Security Notes
- Service Account tokens are **revocable** from the 1Password web UI
- Token has **vault-scoped** access only (least privilege)
- File is stored with restricted ACLs (`icacls`)
- Token never appears in command history when read from file

## Pitfalls

1. **Never mix `--reveal` with interactive signin in scripts** — the biometric prompt will hang
2. **Don't store the token in env vars permanently** — read from file per-command
3. **Token expiry** — Service Account tokens expire after 1 year by default; set calendar reminder
4. **Vault access changes** — If you add new items to the vault, the Service Account needs to be re-granted access

## Hermes Integration

For Hermes agent automation, add this to the agent's context or as a pre-step:
```powershell
$env:OP_SERVICE_ACCOUNT_TOKEN = Get-Content "$env:USERPROFILE\.ultron\.op_service_account"
```

Then use `op` normally in subsequent commands.
