"""The evolution stack's own tool helpers.

This directory is a REGULAR package on purpose. Without __init__.py it
is a namespace package, and a namespace package loses to any regular
package of the same name that appears elsewhere on sys.path - no matter
where the namespace directory sits. The Hermes agent ships its own
`tools/` package, so `import tools.history_secret_sweep` from a test
resolved to the AGENT's tools and failed with a ModuleNotFoundError
that named the submodule, which is the tell: `tools` imported fine,
it was simply the wrong `tools`.

A regular package found first on sys.path wins outright, so this file
is what makes the stack's helpers importable from its own tests.
"""
