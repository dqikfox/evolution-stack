import socket
import urllib.request
import sys
import time

def verify_service(host, port, path="/health", timeout=3):
    """
    Implements L15 & L09: A timeout is not a death. 
    Distinguishes between DOWN (socket failure) and DEGRADED (HTTP timeout or internal error).
    """
    # Stage 1: TCP Handshake Gatekeeper (L15 - Fast, low-latency)
    try:
        start_tcp = time.time()
        with socket.create_connection((host, port), timeout=timeout):
            tcp_elapsed = time.time() - start_tcp
    except Exception as e:
        print(f'CRITICAL: Service {host}:{port} unreachable at network layer: {e}')
        sys.exit(1)  # DOWN

    # Stage 2: HTTP Probe & Component Inspection (L09/L11)
    try:
        url = f"http://{host}:{port}{path}"
        req = urllib.request.Request(url, method='GET')
        start_http = time.time()
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed = time.time() - start_http
            body = response.read().decode('utf-8')
            
            # L09: Read the component block, not just the envelope
            if 'not_ready' in body or 'error' in body.lower():
                print(f'CRITICAL: Service {host}:{port} reports internal failure: {body[:100]}...')
                sys.exit(1)  # DOWN (Functionally dead)

            if elapsed > (timeout * 0.7):
                print(f'WARNING: Service {host}:{port} responded but was slow ({elapsed:.2f}s)')
                sys.exit(2)  # DEGRADED (Reachable but slow)
            
            print(f'OK: {host}:{port} is healthy ({elapsed:.3f}s)')
            sys.exit(0)  # HEALTHY

    except urllib.error.URLError as e:
        # If the error is a timeout, we know TCP worked, so it's just slow/hanging
        if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
            print(f'WARNING: Service {host}:{port} timed out during HTTP probe (TCP was OK)')
            sys.exit(2)  # DEGRADED
        else:
            print(f'CRITICAL: HTTP failure on {host}:{port}: {e}')
            sys.exit(1)  # DOWN
    except Exception as e:
        print(f'CRITICAL: Unexpected error probing {host}:{port}: {e}')
        sys.exit(1)

if __name__ == '__main__':
    # Usage: python service_gatekeeper.py <host> <port>
    target_host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    target_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    verify_service(target_host, target_port)