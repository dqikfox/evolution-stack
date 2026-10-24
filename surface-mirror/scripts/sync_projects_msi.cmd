@echo off
REM Bidirectional merge sync between \\MSI\project-MSI and C:\Users\KING\projects
REM /E = all subdirs, /XO = skip older (newer wins), no deletions on either side
set LOG=C:\Users\KING\AppData\Local\hermes\logs\projects_sync.log
if not exist C:\Users\KING\AppData\Local\hermes\logs mkdir C:\Users\KING\AppData\Local\hermes\logs

echo === %DATE% %TIME% SYNC START === >> "%LOG%"
set EXC=/XD node_modules "Library" .git __pycache__ venv .venv dist build .next .cache .turbo .bun "Library\PackageCache" "Library\Temp" "Library\Logs" obj bin Debug Release
robocopy "\\MSI\project-MSI" "C:\Users\KING\projects" /E /XO /XN /XX %EXC% /MAXAGE:3 /R:2 /W:5 /NP /NDL /XJ /LOG+:"%LOG%"
robocopy "C:\Users\KING\projects" "\\MSI\project-MSI" /E /XO /XN /XX %EXC% /MAXAGE:3 /R:2 /W:5 /NP /NDL /XJ /LOG+:"%LOG%"
echo === %DATE% %TIME% SYNC END === >> "%LOG%"
exit /b 0
