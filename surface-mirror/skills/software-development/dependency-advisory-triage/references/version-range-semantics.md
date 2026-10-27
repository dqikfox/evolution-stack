# Version range semantics for advisory triage

How to decide whether a candidate version is inside a GitHub advisory's
`vulnerable_version_range`, and how to find the installable floor.

## The range is a conjunction

A comma-separated range is an **AND** of clauses, not an OR:

```
>= 4.49.0, < 4.51.0     means  version >= 4.49.0 AND version < 4.51.0
```

Evaluating it as a disjunction ("is it >= the lower bound OR is it < the
upper bound?") reports every version above the lower bound as vulnerable.
That is wrong in the direction that hurts: a correct fix looks broken, and
the natural next move is to hunt for a problem that is not there.

Walk the clauses and require **all** of them to hold:

```python
def in_range(ver, rng):
    clauses = [c.strip() for c in rng.split(",") if c.strip()]
    if not clauses:
        return False
    for part in clauses:
        op, _, raw = part.partition(" ")      # ">= 4.49.0"
        op = op or "=="
        if not holds(ver, op, raw):
            return False
    return True
```

A version is vulnerable iff `in_range(version, rng)` is true.

## Comparison is version-aware, not string-aware

Use PEP 440 ordering (`packaging.version.Version`) when it is available:
`5.10.0` sorts after `5.9.0`, and `5.0.0rc3` sorts **before** `5.0.0`.
A plain string compare gets both wrong.

If `packaging` is unavailable, a tuple-of-ints fallback is adequate for
plain release versions but will mis-order pre-release suffixes:

```python
def key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])
```

## An advisory with no patched version

`first_patched_version` can be `null`. That is not "unfixable" — it means
the advisory's range has an upper bound and no release was cut against it.
Two cases:

- Range has an upper bound (`>= 4.49.0, <= 5.8.1`): the fix is to pin
  **above** that bound. No upstream release is required.
- Range has no upper bound (`< 5.3.0`): there must be a patched version
  somewhere; if `first_patched_version` is null too, the advisory is
  effectively "no fix exists yet" and the only lever is removing the
  dependency or gating the code path that reaches it.

Never treat a null `first_patched_version` as "skip this advisory".

## A yanked version is not an installable floor

The advisory's patched version can be **yanked**: published, then pulled by
the maintainers. It installs, but nobody should pin it, and the release
below it may still be inside a different advisory's range.

Check the yank flag directly on PyPI:

```
https://pypi.org/pypi/<package>/json
    .releases[<version>][i].yanked
```

A release is yanked when every file in it is marked yanked. Walk **up**
the sorted release list from the advisory's floor and take the first
version that is both outside every vulnerable range and not yanked.

This is why "the patched version" and "the version to pin" are usually
different numbers.

## Pin style

An advisory is cleared by the resolved version, not by the constraint
syntax. But a floor is only a floor if it is exact:

- `package==1.2.3` — exact. Establishes a floor.
- `package>=1.2.3` — not a floor. It permits the vulnerable version and
  every future one, and it does not clear the advisory.

When a package is under advisory, keep the exact pin. Use ranges only
for packages that are not, and only when a range is genuinely wanted.

## Verifying the whole set

Individual floors can still conflict, and a transitive dependency can
pull in a yanked release. After computing the floors, resolve the manifest
and read the resolution:

```
uv pip compile requirements.txt --python-version 3.11
```

A warning naming a yanked package in the resolution is part of the result.
The resolution is the thing that will actually be installed.
