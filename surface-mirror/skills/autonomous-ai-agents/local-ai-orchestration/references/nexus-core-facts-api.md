# NEXUS CORE Megatron Semantic Facts API

## Endpoint

```
POST http://127.0.0.1:8650/api/memory/fact
```

## CRITICAL: Form-encoded, NOT JSON

The endpoint expects `application/x-www-form-urlencoded`, not JSON. Sending JSON gets `"Field required"` errors for both `key` and `value` fields:

**Wrong (JSON):**
```bash
curl -X POST http://127.0.0.1:8650/api/memory/fact \
  -H 'Content-Type: application/json' \
  -d '{"key":"system.nexus-core","value":"v3.3.0","category":"system","confidence":1.0}'
# → {"detail":[{"type":"missing","loc":["body","key"],...},{"type":"missing","loc":["body","value"],...}]}
```

**Correct (form-encoded):**
```bash
curl -X POST http://127.0.0.1:8650/api/memory/fact \
  -d 'key=system.nexus-core' \
  -d 'value=v3.3.0' \
  -d 'category=system' \
  -d 'confidence=1.0'
# → {"status":"stored","key":"system.nexus-core","category":"system"}
```

## Querying facts

```bash
GET http://127.0.0.1:8650/api/memory/facts
# → {"facts": {"user.preferred-voice-id": {"value":"0iuMR9ISp6Q7mg6H70yo", ...}, ...}}
```

## Available categories

- `user` — user preferences, identity
- `system` — infrastructure facts, versions, config state
- `pytest` — test framework artifacts (cruft from development)

## Cleanup

Pytest artifacts can be removed by checking the facts list and deleting any `pytest.*` keys via the UI or a targeted DELETE request.
