# Unity Circuit Component Extension Pattern (from QHYSICS session)

Condensed pattern for adding a new passive component (e.g. Resistor) to a hybrid legacy+modern Unity VR physics lab.

## Context
- Legacy: CircuitLab.cs (SpiceSharp DC sim), CircuitComponent base, PegMgr for breadboard snapping, Dispenser enum + tag system for reset/animation.
- Modern: QhysicsGadgets.cs (hotbar spawn + Load* for induction), QhysicsInventory (desktop 1-9 hotbar + UI), XR gadgets, procedural fallbacks for missing prefabs.
- Goal: new component must snap to pegs, participate in sim, appear in hotbar, support desktop + VR.

## Core Steps
1. **Interface compliance**: Create `Assets/Scripts/CircuitLab/NewComp.cs` inheriting `CircuitComponent`, implementing `IResistor` (or IBattery etc.). Implement `Resistance`, `SetActive`, `SetCurrent`, optional labels with TMP, visuals.
2. **Enum + mapping**:
   - Add to `Dispenser.ComponentTag` enum.
   - Add case in `TryMapTag(key, out tag)` in QhysicsGadgets.
3. **Spawning**:
   - In `SpawnPrimitiveProxy` (fallback path): special case for name, use appropriate PrimitiveType (Cylinder for resistor), scale, attach script, set `.resistance`, `tag = "NewComp"`, call helper to add BoxCollider + SphereCollider (PegMgr disables these on place).
   - Name spawned as `"ComponentNewComp_Desktop"`.
   - Call `EnsureGrabPhysics` / `EnableColliders`.
4. **Inventory integration** (for desktop hotbar):
   - Add to `SlotId` enum (e.g. after Bulb).
   - Insert into `SlotLabels` array.
   - Extend `ReadDigitPressed` and hotkey check from `<=8` to `<=9` (or dynamic).
   - Make `_slotImages` / `_slotLabels` arrays sized to `SlotLabels.Length`.
   - Update `for (int i = 0; i < 8` loops and startX calc to use `SlotLabels.Length`.
   - Update hint text.
5. **Visuals & labels**: In component, build procedural (cylinder + leads) if no `resistorBody` assigned. Handle billboard in LateUpdate. Respect `Lab.showLabels`.
6. **Sim hookup**: Handled automatically if IResistor (adds VoltageSource + Resistor in AddSpiceSharpEntity). Ensure `IsClosed`, peg positions correct.
7. **Verification**:
   - Static: Python script (use tempfile + `hermes-verify-` prefix in AppData\Local\Temp) checking class inheritance, enum, map cases, special spawn logic, inventory slots.
   - Runtime: In Unity Editor (Ctrl+P), use hotbar key, spawn, drop on pegs, complete circuit with battery/wire/bulb/switch, activate labels lever, observe current/resistance values and visuals.
   - No unit tests in project → ad-hoc only.

## Pitfalls Observed
- Primitive cube vs needed shape: override in special case.
- Colliders: must have Box + Sphere; PegMgr hardcodes GetComponent on them.
- Hotbar length: hardcoded 8 everywhere (arrays, loops, digit checks) — must update all.
- Name/tag: legacy reset/search uses tag and "Component" + tag prefix.
- No prefab: always implement procedural fallback + script attach in gadget spawner.
- Orientation/scale: peg system expects short vs long components; test drop behavior.
- Labels: TMP requires using TMPro; optional in component.

## Files Typically Touched
- Assets/Scripts/CircuitLab/NewComp.cs (new)
- Assets/Scripts/CircuitLab/Dispenser.cs (enum)
- Assets/Universe/Player/QhysicsGadgets.cs (map + spawn special case + helpers)
- Assets/Universe/Player/QhysicsInventory.cs (slots, UI build, hotkeys)
- (Optional) QHYSICS_PLAY.md or README for docs
- Scene may need manual dispenser addition later (use editor menus)

## Example Trigger Phrases
"add resistor support", "make the hotbar resistor actually work on the breadboard", "extend the circuit components".

This pattern generalizes to other I* interfaces (new conductors, batteries, dynamics).

See main continuous-feature-development for the overall SCAN → BUILD → VERIFY cadence (adapted here to Unity Editor test instead of pytest/Playwright).