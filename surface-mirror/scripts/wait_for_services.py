import socket
import time
import sys

REQUIRED_PORTS = [8666, 8500, 8080]
TIMEOUT = 60
POLL_INTERVAL = 2

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    print(f"Starting dependency check for ports: {REQUIRED_PORTS}")
    start_time = time.time()
    
    for port in REQUIRED_PORTS:
        while not check_port(port):
            if time.time() - start_time > TIMEOUT:
                print(f"Error: Timeout reached waiting for port {port} to become available.")
                sys.exit(1)
            print(f"Waiting for service on port {port}... (elapsed: {int(time.time() - start_time)}s)")
            time.sleep(POLL_INTERVAL)
        print(f"Port {port} is UP.")

    print("All services verified. Proceeding with benchmark.")
    sys.exit(0)

if __name__ == "__main__":
    main()