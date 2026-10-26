"""
Tests for the NEXUS RAG relevance floor.

The bug this exists for: `build_context` injected EVERY retrieved note,
whether or not the note matched the query. The retrieval's score carries a
SOURCE PRIORITY boost, so a note from a high-priority source scored 0.04
with no textual relevance at all - and eight of those were injected into
every question.

The model then read the irrelevant context as the subject of the question
and answered by describing the notes instead of answering the message.
Measured on the live service before the fix: 3 correct answers in 5. After
the fix: 8 in 8.

These tests are offline. They do not contact a model, and they do not need
the corpus - they test the RELEVANCE RULE, which is the part that was
wrong.

    pytest tests/test_nexus_rag_relevance.py -q
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAG_PATH = "E:/ultron-memory/nexus-core/core/rag.py"
SEARCH_PATH = "E:/ultron-memory/nexus-core/core/search.py"
NEXUS_ROOT = "E:/ultron-memory/nexus-core"


def _load(name, path):
    """Import the module under test, with the heavy optional deps stubbed.

    `core.search` imports chromadb, which is not installed in this
    interpreter. The functions under test never touch it - they take the
    retrieval results as an argument - so a stub is enough, and the
    behavioural tests become real instead of skipped.

    The module uses RELATIVE imports (`from .config import ...`), so it has
    to be imported as part of the `core` package, not by file path.
    """
    if NEXUS_ROOT not in sys.path:
        sys.path.insert(0, NEXUS_ROOT)
    try:
        import chromadb  # noqa: F401
    except Exception:
        stub = type(sys)("chromadb")
        stub.PersistentClient = lambda *a, **k: None
        stub.__version__ = "stub"
        sys.modules["chromadb"] = stub
    try:
        import sentence_transformers  # noqa: F401
    except Exception:
        sys.modules["sentence_transformers"] = type(sys)("sentence_transformers")
    try:
        import numpy  # noqa: F401
    except Exception:
        pass
    # the real package import
    try:
        mod = importlib.import_module("core.rag")
        sys.modules[name] = mod
        return mod
    except Exception as e:
        print("   the core.rag import failed: %s" % str(e)[:120])
    # fall back to a by-path load for the source-level tests
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        pass
    return mod


# ------------------------------------------------------------------ the rule

def test_the_relevance_of_a_hit_excludes_the_source_boost():
    """A note from a high-priority source is not relevant to a query."""
    src = Path(RAG_PATH).read_text(encoding="utf-8", errors="replace")
    assert "_relevance" in src, "the relevance measure must exist"
    # the measure must be built from the per-hit signals, not from `score`
    body = src[src.index("def _relevance"):src.index("def build_context")]
    assert "kw_score" in body
    assert "vec_score" in body
    assert "source_boost" not in body, "the source boost is not relevance"


def test_a_hit_with_no_measured_signal_is_not_relevant():
    """The keyword fast path once returned hits with no per-hit signal.

    Such a hit is UNMEASURED, and unmeasured must not be treated as
    relevant - otherwise the fast path silently defeats the floor.
    """
    src = Path(RAG_PATH).read_text(encoding="utf-8", errors="replace")
    body = src[src.index("def _relevance"):src.index("def build_context")]
    assert "return 0.0" in body, "an unmeasured hit must score zero"


def test_the_hybrid_search_exposes_the_per_hit_signal():
    """The fast path must expose kw_score/vec_score, or the floor is a no-op."""
    src = Path(SEARCH_PATH).read_text(encoding="utf-8", errors="replace")
    fast = src[src.index("if len(kw) >= limit:"):src.index("vec = vector_search")]
    assert "kw_score" in fast, "the fast path must expose kw_score"
    assert "vec_score" in fast, "the fast path must expose vec_score"
    # and it must not hand back a score that is only a source boost
    assert "0.6 + source_boost" not in fast, \
        "a score made only of the source boost is not a relevance score"


def test_the_floor_is_configurable():
    src = Path(RAG_PATH).read_text(encoding="utf-8", errors="replace")
    assert "NEXUS_RAG_RELEVANCE_FLOOR" in src, \
        "the floor must be tunable without a code change"
    assert "RELEVANCE_FLOOR" in src


def test_the_floor_is_applied_before_a_note_is_injected():
    src = Path(RAG_PATH).read_text(encoding="utf-8", errors="replace")
    body = src[src.index("def build_context"):src.index("def _ollama_ping")]
    rel_check = body.index("_relevance")
    get_note = body.index("get_note")
    append = body.index("chunks.append")
    assert rel_check < get_note < append, \
        "the relevance check must come before the note is fetched and appended"


# ------------------------------------------------------------------ the behaviour

def test_no_context_is_injected_when_nothing_matches(monkeypatch):
    """The real rule: a query that matches nothing gets NO context."""
    mod = _load("nexus_rag_under_test", RAG_PATH)
    if not hasattr(mod, "build_context"):
        pytest.skip("the rag module could not be imported in this environment")

    monkeypatch.setattr(mod, "hybrid_search", lambda q, limit=20: [
        {"slug": "a", "title": "A", "id": 1, "source": "mem0-local",
         "kw_score": 0.0, "vec_score": 0.0, "score": 0.04},
        {"slug": "b", "title": "B", "id": 2, "source": "notion",
         "kw_score": 0.0, "vec_score": 0.0, "score": 0.04},
    ])
    monkeypatch.setattr(mod, "get_note", lambda slug: {
        "slug": slug, "title": "T", "body": "irrelevant body text", "source": "mem0-local"})

    ctx = mod.build_context("a question that matches nothing", top_k=8, floor=0.02)
    assert ctx == "", "irrelevant notes were injected: %r" % ctx[:200]


def test_a_genuinely_matching_note_is_still_injected(monkeypatch):
    """The floor must not break the RAG for a real question."""
    mod = _load("nexus_rag_under_test2", RAG_PATH)
    if not hasattr(mod, "build_context"):
        pytest.skip("the rag module could not be imported in this environment")

    monkeypatch.setattr(mod, "hybrid_search", lambda q, limit=20: [
        {"slug": "good", "title": "G", "id": 1, "source": "nexus",
         "kw_score": 0.2, "vec_score": 0.0, "score": 0.14},
        {"slug": "noise", "title": "N", "id": 2, "source": "mem0-local",
         "kw_score": 0.0, "vec_score": 0.0, "score": 0.04},
    ])
    monkeypatch.setattr(mod, "get_note", lambda slug: {
        "slug": slug, "title": "T", "body": "the real body", "source": "nexus"})

    ctx = mod.build_context("a question about the real body", top_k=8, floor=0.02)
    assert "the real body" in ctx
    assert ctx.count("--- source:") == 1, "the noise note was injected too"


def test_a_weak_but_real_match_survives_the_default_floor(monkeypatch):
    """The floor must not be so high that real matches are dropped."""
    mod = _load("nexus_rag_under_test3", RAG_PATH)
    if not hasattr(mod, "build_context"):
        pytest.skip("the rag module could not be imported in this environment")

    monkeypatch.setattr(mod, "hybrid_search", lambda q, limit=20: [
        {"slug": "weak", "title": "W", "id": 1, "source": "nexus",
         "kw_score": 0.05, "vec_score": 0.0, "score": 0.06},
    ])
    monkeypatch.setattr(mod, "get_note", lambda slug: {
        "slug": slug, "title": "T", "body": "the body", "source": "nexus"})

    ctx = mod.build_context("a question", top_k=8)
    assert "the body" in ctx, "a real match of 0.025 relevance was dropped"
