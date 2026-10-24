import socket
import sys

def verify(host, port):
    # Stage 1: TCP Liveness (Immune to L11 recursive dependency loops)
    try:
        sock = socket.create_connection((host, port), timeout=2)
        print(f"LIVENESS: {host}:{port} accepted TCP connection.")
        sock.close()
    except Exception as e:
        print(f"FAILURE: Port {port} not reachable via TCP: {e}")
        sys.exit(1)

    # Stage 2: HTTP Readiness (Subject to L09/L11 logic-based hangs)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)  # Short timeout prevents benchmark-wide execution hangs
        s.connect((host, port))
        s.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        resp = s.recv(1024)
        if b"200 OK" in resp:
            print("READINESS: Service reported 200 OK.")
            sys.exit(0)
        else:
            # Addresses L09: Port is open but component failed (e.g., ChromaDB not ready)
            print(f"DEGRADED: Service responded with error or invalid status: {resp[:50]!r}")
            sys.exit(1)
    except socket.timeout:
        # Specifically catches the failure described in the prompt logs
        print("TIMEOUT: /health endpoint hung (likely dependency-check recursion - see L11).")
        sys.exit(1)
    except Exception as e:
        print(f"FAILURE: HTTP probe encountered an error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    target_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    verify("127.0.0.1", target_port)