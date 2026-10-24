# Robocopy bidirectional merge template

Copy to `C:\Users\KING\AppData\Local\hermes\scripts\` and adjust paths. Log lives beside it in `logs/`.

```cmd
@echo off
REM Bidirectional merge sync A <-> B. /E all subdirs, /XO/XN newer-wins both ways, /XX never delete.
set LOG=C:\Users\KING\AppData\Local\hermes\logs\projects_sync.log
if not exist C:\Users\KING\AppData\Local\hermes\logs mkdir C:\Users\KING\AppData\Local\hermes\logs

echo === %DATE% %TIME% SYNC START === >> "%LOG%"
robocopy "\\HOST\share" "C:\local\dir" /E /XO /XN /XX /R:2 /W:5 /NP /NDL /XJ /LOG+:"%LOG%"
robocopy "C:\local\dir" "\\HOST\share" /E /XO /XN /XX /R:2 /W:5 /NP /NDL /XJ /LOG+:"%LOG%"
echo === %DATE% %TIME% SYNC END === >> "%LOG%"
exit /b 0
```

## Variants

- **Exclude dependency/build trees** (recommended initial run): append
  `/XD node_modules .git __pycache__ venv .venv dist build target`
  to both robocopy lines. Cuts first-pass time from hours to minutes on dev-project trees.
- **One-way mirror (HOST is source of truth)**: single leg with `/MIR` instead of the two `/E /XO /XN /XX` legs. Warn the user — /MIR deletes extras on the destination.
- **Instant propagation**: if hourly polling is too coarse, Syncthing over Tailscale beats robocopy on a schedule; robocopy is the zero-install baseline.

## Scheduling

```cmd
schtasks /create /tn "Host_Projects_Sync" /tr "C:\Users\KING\AppData\Local\hermes\scripts\sync_projects.cmd" /sc hourly /mo 1 /f
```

Robocopy exit code 0-7 = success; the wrapper `exit /b 0` prevents the scheduled task reporting failure on benign copies.
