#!/usr/bin/env python3
"""
Local deep-research agent: plan -> search -> triage -> fetch -> extract ->
gap-check -> synthesize, with persistent memory of past sessions.

WHY A PIPELINE AND NOT AN AGENT
-------------------------------
The obvious design is one agent holding web_search/fetch/memory tools, free to
choose. That was rejected on measured evidence: gpt-oss:20b at Q4 cannot
reliably orchestrate many tools. With 6 MCP servers attached to opencode, an
explicitly-requested tool call did not complete in 10 minutes, and even the
built-in toolset produced an `invalid` tool call (see AGENTIC-STACK.md).

So Python owns the control flow and the model gets ONE narrow job per call,
with no tool-selection burden. Every structured stage is schema-constrained via
Ollama's `format` - measured 3/3 valid JSON vs 2/3 when merely asked for JSON.

Each stage is independently testable, and a failure in any stage degrades the
run rather than losing it: whatever findings exist are always synthesised and
saved.

Usage:
    ./deep_research.py "your question"
    ./deep_research.py "..." --rounds 3 --max-fetch 6
    ./deep_research.py "..." --no-memory        # skip recall + save
    ./deep_research.py "..." --model qwen36-abliterated-16k
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_lib as R
import memory as M

REPORT_DIR = M.ROOT


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------- 1. PLAN -----

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"},
                    "minItems": 2, "maxItems": 5},
        "what_would_answer_this": {"type": "string"},
    },
    "required": ["queries", "what_would_answer_this"],
}
PLAN_SYS = (
    "You plan web research. Given a question, output 2-5 diverse search-engine "
    "queries that together would answer it. Use the wording a source document "
    "would use, not conversational phrasing. Vary the angle: definitions, "
    "specifications/numbers, comparisons, first-hand reports. Do not answer the "
    "question yourself."
)


def plan(question, prior, model):
    u = f"Question: {question}"
    if prior:
        u += ("\n\nYou have researched related topics before. Do not repeat these "
              "queries; go deeper or cover what they missed:\n"
              + "\n".join(f"- {p['question']}" for p in prior))
    got = R.chat_json(PLAN_SYS, u, PLAN_SCHEMA, model=model)
    if not got or not got.get("queries"):
        return [question], "(planner failed; falling back to the raw question)"
    return got["queries"][:5], got.get("what_would_answer_this", "")


# ----------------------------------------------------------- 3. TRIAGE -----

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "pick": {"type": "array", "items": {"type": "integer"}},
        "why": {"type": "string"},
    },
    "required": ["pick", "why"],
}
TRIAGE_SYS = (
    "You choose which search results are worth reading in full. Given a question "
    "and a numbered list of results, return the indices worth fetching, best "
    "first. Prefer primary sources, documentation, specifications and first-hand "
    "measurements over listicles, SEO blogspam and aggregators. Skip results "
    "whose title or snippet shows they are off-topic."
)


def triage(question, hits, budget, model):
    if not hits:
        return []
    listing = "\n".join(
        f"{i}. [{h['source']}] {h['title']}\n   {h['url']}\n   {h['snippet'][:150]}"
        for i, h in enumerate(hits))
    got = R.chat_json(TRIAGE_SYS,
                      f"Question: {question}\n\nResults:\n{listing}\n\n"
                      f"Return at most {budget} indices.",
                      TRIAGE_SCHEMA, model=model)
    if not got:
        return list(range(min(budget, len(hits))))   # fall back to top-N
    idx = [i for i in got.get("pick", []) if isinstance(i, int) and 0 <= i < len(hits)]
    return idx[:budget] or list(range(min(budget, len(hits))))


# ---------------------------------------------------------- 5. EXTRACT -----

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"},
                               "quote": {"type": "string"}},
                "required": ["claim", "quote"],
            },
        },
    },
    "required": ["relevant", "summary", "findings"],
}
EXTRACT_SYS = (
    "You extract evidence from one web page for a research question. Return a "
    "short summary of what this page contributes, and a list of findings. Every "
    "finding needs a claim and a VERBATIM quote from the page supporting it - "
    "never invent or paraphrase a quote. If the page does not address the "
    "question, set relevant=false and return no findings. Prefer concrete "
    "numbers, versions, dates and specifications."
)


def extract(question, page, model):
    body = page["text"][:14000]
    got = R.chat_json(EXTRACT_SYS,
                      f"Question: {question}\n\nPage title: {page['title']}\n"
                      f"URL: {page['url']}\n\nPage text:\n{body}",
                      EXTRACT_SCHEMA, model=model)
    if not got or not got.get("relevant"):
        return None
    out = []
    for f in got.get("findings", [])[:6]:
        q = (f.get("quote") or "").strip()
        # Guard against fabricated quotes: keep only what really is on the page.
        verified = _quote_on_page(q, page["text"])
        out.append({"claim": (f.get("claim") or "").strip(), "quote": q,
                    "url": page["url"], "verified": verified})
    return {"url": page["url"], "title": page["title"],
            "summary": (got.get("summary") or "").strip(), "findings": out}


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _quote_on_page(quote, text):
    """Cheap verbatim check. Short quotes are matched whole; long ones by a
    distinctive middle slice, since models often trim leading/trailing words."""
    q, t = _norm(quote), _norm(text)
    if not q or len(q) < 12:
        return False
    if q in t:
        return True
    mid = q[len(q) // 4: len(q) // 4 + 60]
    return len(mid) >= 30 and mid in t


# --------------------------------------------------------- 6. GAP CHECK ----

GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "sufficient": {"type": "boolean"},
        "missing": {"type": "string"},
        "next_queries": {"type": "array", "items": {"type": "string"},
                         "maxItems": 3},
    },
    "required": ["sufficient", "missing", "next_queries"],
}
GAP_SYS = (
    "You judge whether gathered evidence answers a research question. If it does, "
    "set sufficient=true. If not, say what is missing and give up to 3 new "
    "search queries targeting exactly that gap. Be strict: partial answers, "
    "missing numbers, or a single unconfirmed source mean it is not sufficient."
)


def gap_check(question, pages, model):
    ev = "\n\n".join(f"- {p['title']} ({p['url']})\n  {p['summary']}" for p in pages)
    got = R.chat_json(GAP_SYS, f"Question: {question}\n\nEvidence so far:\n{ev}",
                      GAP_SCHEMA, model=model)
    if not got:
        return True, "", []
    return bool(got.get("sufficient")), got.get("missing", ""), \
        [q for q in got.get("next_queries", []) if q][:3]


# -------------------------------------------------------- 7. SYNTHESIZE ----

WRITE_SYS = (
    "You write a research report from gathered evidence. Structure: a direct "
    "answer in the first 2-3 sentences, then the detail, then explicit "
    "limitations. Cite with bracketed numbers [1], [2] matching the numbered "
    "sources given. Every non-obvious claim needs a citation. Use only the "
    "evidence provided - if it does not answer part of the question, say so "
    "plainly rather than filling the gap from memory. Prefer concrete numbers. "
    "Markdown, no title header."
)


def synthesize(question, pages, model):
    if not pages:
        return "No usable sources were gathered for this question."
    src = {p["url"]: i + 1 for i, p in enumerate(pages)}
    blocks = []
    for p in pages:
        n = src[p["url"]]
        fl = "\n".join(f'  - {f["claim"]}  (quote: "{f["quote"][:200]}")'
                       for f in p["findings"] if f["verified"])
        blocks.append(f"[{n}] {p['title']} - {p['url']}\n  {p['summary']}\n{fl}")
    body = "\n\n".join(blocks)
    report = R.chat_text(
        WRITE_SYS, f"Question: {question}\n\nEvidence:\n{body}", model=model)
    lines = ["", "## Sources", ""]
    for p in pages:
        lines.append(f"{src[p['url']]}. [{p['title'] or p['url']}]({p['url']})")
    return report.strip() + "\n" + "\n".join(lines)


# ---------------------------------------------------------------- driver ---

def run(question, rounds=2, max_fetch=5, per_query=6, model=R.DEFAULT_MODEL,
        use_memory=True):
    t0 = time.time()
    prior = M.recall(question, k=3) if use_memory else []
    if prior:
        log(f"  [memory] {len(prior)} related past session(s):")
        for p in prior:
            log(f"      [{p['distance']}] {p['question'][:70]}")

    pages, seen_urls, all_sources = [], set(), []
    queries, rationale = plan(question, prior, model)
    log(f"  [plan] {rationale[:100]}")

    for rnd in range(1, rounds + 1):
        log(f"  [round {rnd}] queries: {queries}")
        hits = []
        for q in queries:                      # sequential: Marginalia is rate-limited
            for h in R.search_hits(q, per_query):
                if R._norm_url(h["url"]) not in seen_urls:
                    hits.append(h)
        if not hits:
            log("  [search] nothing new returned")
            break
        all_sources.extend(hits)

        pick = triage(question, hits, max_fetch, model)
        log(f"  [triage] fetching {len(pick)} of {len(hits)}")
        for i in pick:
            h = hits[i]
            key = R._norm_url(h["url"])
            if key in seen_urls:
                continue
            seen_urls.add(key)
            page = R.fetch_clean(h["url"])
            if not page["ok"]:
                log(f"      skip {h['url'][:60]} ({page['error'][:40]})")
                continue
            got = extract(question, page, model)
            if got:
                v = sum(1 for f in got["findings"] if f["verified"])
                log(f"      + {len(got['findings'])} findings ({v} quote-verified)"
                    f" from {page['title'][:50]}")
                pages.append(got)
            else:
                log(f"      - not relevant: {page['title'][:50]}")

        if rnd == rounds or not pages:
            break
        ok, missing, nxt = gap_check(question, pages, model)
        if ok:
            log("  [gap] evidence judged sufficient")
            break
        log(f"  [gap] missing: {missing[:100]}")
        if not nxt:
            break
        queries = nxt

    log(f"  [synthesize] from {len(pages)} page(s)")
    report = synthesize(question, pages, model)
    elapsed = time.time() - t0

    path = None
    if use_memory:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower())[:50].strip("-")
        path = REPORT_DIR / f"{time.strftime('%Y-%m-%d')}-{slug}.md"
        path.write_text(f"# {question}\n\n_{time.strftime('%Y-%m-%d %H:%M')} · "
                        f"{model} · {elapsed:.0f}s · {len(pages)} sources_\n\n{report}\n")
        findings = [f for p in pages for f in p["findings"]]
        for s in all_sources:
            s["fetched"] = int(R._norm_url(s["url"]) in seen_urls)
        sid = M.save_session(question, report, all_sources, findings, model,
                             rounds, elapsed, report_path=path)
        M.index_session(sid, question, report)
        log(f"  [saved] session {sid} -> {path}")

    return report, elapsed, len(pages)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--max-fetch", type=int, default=5)
    ap.add_argument("--per-query", type=int, default=6)
    ap.add_argument("--model", default=R.DEFAULT_MODEL)
    ap.add_argument("--no-memory", action="store_true")
    a = ap.parse_args()
    report, elapsed, n = run(a.question, a.rounds, a.max_fetch, a.per_query,
                             a.model, not a.no_memory)
    print(report)
    log(f"\n  done in {elapsed:.0f}s from {n} sources")


if __name__ == "__main__":
    main()
