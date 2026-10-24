print("boot")
import runpy, sys
try:
    runpy.run_path(r"C:\Users\KING\AppData\Local\hermes\scripts\watchdog.py", run_name="__main__")
except SystemExit as e:
    print("SystemExit", e.code)
    sys.exit(e.code if isinstance(e.code, int) else 1)
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(2)
print("done")
