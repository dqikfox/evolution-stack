---
name: cross-host-smb-sync
description: Use when syncing files between Windows hosts over SMB.
---

# Cross-Host SMB Sync (Windows <-> Windows)

Use when wiring or repairing a sync between two Windows machines over an SMB share (e.g. THRONE <-> MSI).

## Procedure

1. **Probe both sides first**: ls //HOST/share from bash, plus the local dir. Confirm read access in both directions before designing anything.
2. **Write the sync script** as a .cmd using robocopy bidirectional merge (see references/robocopy-merge.md for the template):
   - /E /XO /XN /XX = all subdirs, newer timestamp wins per side, no deletions anywhere (merge, not mirror). Run A->B then B->A.
   - /XJ skips junctions (prevents recursion loops); /R:2 /W:5 retries locked files.
   - Append both legs to one log with /LOG+:.
   - Warn the user: last-writer-wins means same-file edits on both sides lose the older edit. Offer /XD node_modules .git __pycache__ exclusion if dep trees dominate copy time.
3. **Schedule it**: schtasks /create /tn <Name> /tr "<script>" /sc hourly /f.
4. **Test write access explicitly** before claiming done: touch //HOST/share/.w_test && rm. Read success proves nothing about write.
5. **If write fails with Access Denied / ERROR 5**: diagnose on the server side (see below), not the client.

## Diagnosing a read-only share

- cmdkey /list | grep -i -B1 HOST -- find the stored credential in use for that host.
- net use \\HOST\share /delete /y then reconnect with /user:... to force auth. If net use *succeeds* but touch still fails, auth is fine and the **share ACL itself is read-only** -- nothing client-side will fix it.
- **System error 1219** ('multiple connections ... same user'): Windows binds one credential session per server name. Work around by connecting via the host's *other* DNS name instead (e.g. Tailscale FQDN host.tail886dbb.ts.net vs HOST) -- each name gets its own session. To fully reset: net use * /delete /y (note: this also drops mapped drives like U: -- reconnect them after).

## Fixing share perms remotely via SSH (Windows OpenSSH host)

When you have SSH creds for the target host, fix server-side ACLs without console access:

- **Drive SSH with paramiko from terminal, not execute_code** -- the sandbox kernel lacks paramiko; install with python -m pip install paramiko into the system python and run a script via terminal(). No sshpass exists in git-bash.
- **Windows usernames ending in $ must be passed complete** (CHANN0$, not CHANN0) -- a dropped $ returns AuthenticationException even with the right password.
- Then on the target:
  - powershell -NoProfile -Command "Get-SmbShare -Name '<share>' | Select Name,Path" -- get the backing path.
  - Get-SmbShareAccess -Name '<share>' -- if it shows only 'Everyone Allow Read', that is the root cause.
  - Grant-SmbShareAccess -Name '<share>' -AccountName '<user>' -AccessRight Full -Force -- fix the share ACL.
  - icacls "<path>" /grant "<user>:(OI)(CI)M" /T /Q -- fix NTFS. For large trees (hundreds of thousands of files) this exceeds any SSH exec timeout -- launch it detached instead:
    Start-Process icacls -ArgumentList '<path>','/grant','<user>:(OI)(CI)M','/T','/Q' -WindowStyle Hidden
- Verify from the client immediately: touch //HOST/share/.w_test on BOTH the short name and any FQDN alias.

## Pitfalls

- cmd //c through git-bash drops into an interactive shell without running the script -- invoke .cmd files by their bash-style path directly (C:/path/script.cmd).
- Two overlapping sync runs collide on the log file ('being used by another process') -- harmless but confusing; check grep -c "SYNC END" on the log for the true count.
- node_modules over SMB is the slowest possible copy (thousands of tiny files at ~1-2 MB/s effective) -- exclude it unless the user explicitly wants deps mirrored.
- Don't guess credentials across a session: check cmdkey /list, 1Password (op item list, and pass --vault credentials for service-account op item get calls), and the NEXUS/ultron-memory notes under E:\ultron-memory before asking the user.
