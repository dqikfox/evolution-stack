# Starlink gRPC API (Gen 3)

The Starlink Gen 3 router exposes a gRPC API on port 9000 for telemetry and control.

## Implementation Pattern

```python
import starlink_grpc

# Target MUST include the port :9000
target = "192.168.4.1:9000"
context = starlink_grpc.ChannelContext(target=target)
status = starlink_grpc.get_status(context=context)

# Access attributes directly
print(f"Signal Quality: {status.signal_quality}")
print(f"Pop Latency: {status.pop_ping_latency_ms}")
```

## Critical Pitfalls

### 1. Port Specification
The `ChannelContext` target must be explicitly `IP:PORT` (e.g., `192.168.4.1:9000`). 
**Why:** Omitting the port causes the gRPC client to fallback to port 443, resulting in a `StatusCode.UNAVAILABLE` (Connection Refused) error.

### 2. JSON Serialization
The return value of `get_status` is a `DishGetStatusResponse` (protobuf-style object).
**Why:** It is not a native Python dictionary and will raise a `TypeError` if passed to `json.dumps()`. Use `dir(status)` to find available telemetry fields.

### 3. Authentication
- **Reads:** Unauthenticated.
- **Writes:** Require an ECDSA key usually extracted from the Starlink mobile app.
