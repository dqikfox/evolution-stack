#!/usr/bin/env python3
"""Run the Lummings brand review across the provider rotation.

The point of this script is not elegance. The point is that ONE provider
ran out of quota (ChatGPT Plus hit its usage limit mid-review), and the
work still gets done - because the rotation exists.

It pins each provider in turn, sends the same task, and writes each review
to its own file. A provider that cannot serve the request is recorded as
such, with the reason, and the run continues.

    python run_brand_review.py
"""
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

ROUTER = "C:/Users/KING/AppData/Local/hermes/scripts/provider_router.py"
W = Path("C:/Users/KING/AppData/Local/hermes/cache/scratch/lummings-review")

CANON = ["SOURCE_OF_TRUTH.md", "BRAND_RULES_ONEPAGER.md", "BRAND_GUIDELINES.md",
         "VISUAL_LOCK.md", "NAME_CANON.md", "HEARTLIGHTS.md", "CHARACTER_BIBLE.md"]

INSTRUCTION = """You are doing a BRAND AND STYLE REVIEW for Lummings, a children's
companion app. The canon files are given below, then the public-facing copy.

public_copy.txt has already been stripped of CSS, JavaScript and HTML
attributes, so everything in it is text a READER SEES. A retired name in a CSS
class or a filename is allowed and is NOT a violation - only a retired name
in visible text is.

CHECK FOR EXACTLY THESE, and nothing else:

1. RETIRED NAMES IN VISIBLE TEXT. "Lila" and "Pip" are retired. The public
   names are Lumo, Luna, Sprout, Nori, Moki. Flag every visible occurrence.

2. HEARTLIGHT MISUSE. A Heartlight is the ESSENCE or soul of a Lumming, not
   a pet, a creature, a friend to collect, or a thing to own. Flag any
   passage that treats it as a creature or a possession.

3. THE MARKETING BAN LIST. No "why why" or horror-parent framing, no dark
   FOMO, no punishing a missed day, no paywalling the bond, no pressure to
   streak or collect.

4. TONE. It must be warm, hopeful, patient, honest and quiet, and safe first,
   with soft hooks. Flag anything harsh, guilt-tripping, loud, manipulative,
   or childish in a way that talks down to a parent.

5. SEX, VIOLENCE, FEAR AND DISTRESS. This is a product for young children.
   Flag content that could frighten, distress, or sexualise a child, and
   anything that describes a child in danger without a calm resolution.

6. INCONSISTENCY WITH THE CANON. Facts that contradict SOURCE_OF_TRUTH.md -
   a wrong colour, a wrong tagline, a wrong Heartlight name, a wrong role.

OUTPUT FORMAT - follow this exactly:

# Lummings brand review

## Summary
<one paragraph: how many findings, of which kinds, and the single most
important thing to fix>

## Findings
One block per finding, in this exact form:

### F<N> - <the kind> - <severity: critical | major | minor>
- **Where:** <the "## <file>" page heading, and the quoted text>
- **Quote:** <the exact visible text, verbatim>
- **Rule:** <the canon rule it breaks, quoted or closely paraphrased>
- **Fix:** <the specific replacement text or the specific change>

Number findings F1, F2, ... in order of severity. If a category has no
findings, say "None found" for it. Do not invent findings: if the copy is
clean in a category, say so. Do not rewrite the whole site - report the
problems with precise, minimal fixes. Your entire answer must be the review
document, with no preamble and no closing remarks."""


def build_prompt(copy: str) -> str:
    parts = []
    for name in CANON:
        p = W / name
        if p.is_file():
            parts.append("===== CANON: %s =====\n%s" % (name, p.read_text(encoding="utf-8",
                                                                              errors="replace")))
    parts.append("===== PUBLIC COPY =====\n%s" % copy)
    parts.append("===== THE TASK =====\n%s" % INSTRUCTION)
    return "\n\n".join(parts)


def main():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    spec = importlib.util.spec_from_file_location("_router", ROUTER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_router"] = mod
    spec.loader.exec_module(mod)

    copy = (W / "public_copy.txt").read_text(encoding="utf-8", errors="replace")
    prompt = build_prompt(copy)
    print("   the prompt: %d chars" % len(prompt), flush=True)

    # the rotation, in the order the router prefers them
    order = ["anthropic", "xai", "nexus", "ollama-cloud", "ollama-local", "chatgpt"]
    results = {}
    for name in order:
        p = next((x for x in mod.REGISTRY if x.name == name), None)
        if p is None or not p.enabled:
            print("   %-14s not in the rotation" % name, flush=True)
            continue
        t0 = time.time()
        try:
            text, meta = mod.call(p, prompt, max_tokens=6000, timeout=600)
        except Exception as e:
            msg = str(e)[:200]
            print("   %-14s FAILED after %5.1fs: %s" % (name, time.time() - t0, msg), flush=True)
            results[name] = {"status": "failed", "error": msg}
            continue
        el = time.time() - t0
        findings = len(re.findall(r"^###\s*F\d+", text, re.M))
        out = W / ("REVIEW-%s.md" % name)
        out.write_text(text, encoding="utf-8")
        print("   %-14s OK in %5.1fs: %d findings -> %s"
              % (name, el, findings, out.name), flush=True)
        results[name] = {"status": "ok", "elapsed": round(el, 1), "findings": findings,
                         "tokens_out": meta.get("tokens_out"), "file": out.name}

    print("\n=== the review, across the rotation ===")
    for name, r in results.items():
        print("   %-14s %s" % (name, r))
    (W / "review_results.json").write_text(
        __import__("json").dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
