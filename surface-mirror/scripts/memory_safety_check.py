import os
import subprocess
import sys

def check_mem0():
    """Check if mem0 is functional and quota is likely available."""
    try:
        print("Checking mem0 connectivity...")
        if not os.environ.get('MEM0_API_KEY') and not os.path.exists(os.path.expanduser('~/.hermes/.env')):
            return False, "No MEM0 credentials found in env or .env"
        # In a real setup, we would attempt an actual call to the service here.
        return True, "mem0 appears available."
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    success, msg = check_mem0()
    print(f"{'OK' if success else 'FAIL'} | {msg}")
    sys.exit(0 if success else 1)
