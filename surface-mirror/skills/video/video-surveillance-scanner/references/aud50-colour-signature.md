## Australian $50 Note Colour Signature

**Physical description:** Salmon/orange/peach polymer note (current RBA design).

**RGB detection rule (AUD $50 tone):**

```python
if (r > 160 and
    g > 90 and g < 180 and
    b < 120 and
    r > g + 30 and
    r > b + 60):
    orange_count += 1
```

**Rationale:**
- High red component dominates the warm hue.
- Green must be present but not overpowering (avoids pure red/orange false positives).
- Blue must be low (avoids purple/magenta).
- Threshold of 6% frame coverage balances sensitivity against false positives from skin tones, wood, or warm lighting.

**Tested offsets:** 1.5 s and 2.0 s from clip start work for 5–10 s surveillance clips; adjust if objects consistently appear later in the frame sequence.
