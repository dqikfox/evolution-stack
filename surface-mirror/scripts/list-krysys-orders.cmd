@echo off
REM list-krysys-orders.cmd - Show KRYSYS orders, especially PayID ones needing manual confirmation.
REM Usage:
REM   list-krysys-orders.cmd           all orders
REM   list-krysys-orders.cmd payid     only PayID orders
REM   list-krysys-orders.cmd unpaid   only unpaid orders

setlocal
python "%LOCALAPPDATA%\hermes\scripts\list-orders.py" %*
endlocal