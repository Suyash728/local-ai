#!/usr/bin/env python3
"""
Give a tool-calling-capable Ollama model live web access.

Default model is gpt-oss-agent-32k (gpt-oss:20b at num_ctx 32768). The stock
gpt-oss:20b tag runs at Ollama's default 4096 context, which search results plus
a fetched page will overflow. gpt-oss is categorically more reliable at
tool-calling here than qwen2.5-coder:14b (see WEB-ACCESS.md for the measured
comparison). gemma3:12b has no tool-calling capability at all.

SEARCH BACKENDS (2026-08-27). DuckDuckGo's HTML endpoint - what this script
used until now - was put behind an anti-bot challenge and returns HTTP 202 with
zero results for every query. lite.duckduckgo.com, searx.be, Startpage and
Mojeek are all closed to plain scraping too. web_search now queries three
keyless JSON APIs and merges them:

  * Marginalia  - an independent general web index. The main engine.
                  Rate limited, so calls are spaced and retried once.
  * Wikipedia   - encyclopedic backstop, always answers.
  * DuckDuckGo Instant Answer - one-line abstract for entity queries
                  (good on "btrfs", empty on open-ended questions).

Stdlib only - no new dependencies, no API keys, no extra services.

Usage:
    ./ollama_web.py "what is a btrfs subvolume?"
    ./ollama_web.py --model qwen2.5-coder-agent-32k "..."
    ./ollama_web.py --search-only "btrfs subvolume"   # test search, no model
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
UA = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0"
MAX_ROUNDS = 8          # tool-call round trips before giving up
MAX_FETCH_CHARS = 6000  # truncate fetched pages so they don't blow the context

MARGINALIA_MIN_INTERVAL = 1.5   # seconds between Marginalia calls (it rate limits)
_last_marginalia = 0.0


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _clean(s, limit=180):
    s = html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:limit]


def _marginalia(query, n=5):
    """General web index. Public API, no key, but rate limited - space the calls
    and retry once, otherwise a burst returns read timeouts."""
    global _last_marginalia
    gap = time.time() - _last_marginalia
    if gap < MARGINALIA_MIN_INTERVAL:
        time.sleep(MARGINALIA_MIN_INTERVAL - gap)
    url = "https://api.marginalia.nu/public/search/" + urllib.parse.quote(query)
    for attempt in (1, 2):
        try:
            _last_marginalia = time.time()
            d = _get_json(url, timeout=20)
            out = []
            for r in (d.get("results") or [])[:n]:
                out.append({"title": _clean(r.get("title"), 100),
                            "url": r.get("url", ""),
                            "snippet": _clean(r.get("description"))})
            return out
        except Exception:
            if attempt == 2:
                return []
            time.sleep(4)
    return []


def _wikipedia(query, n=3):
    try:
        d = _get_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": query,
             "format": "json", "srlimit": n}))
        return [{"title": h["title"],
                 "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(h["title"].replace(" ", "_")),
                 "snippet": _clean(h.get("snippet"))}
                for h in d["query"]["search"][:n]]
    except Exception:
        return []


def _ddg_abstract(query):
    try:
        d = _get_json("https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": 1}))
        txt = (d.get("AbstractText") or "").strip()
        return f"{txt} [{d.get('AbstractURL','')}]" if txt else ""
    except Exception:
        return ""


def web_search(query: str, max_results: int = 6) -> str:
    abstract = _ddg_abstract(query)
    hits, seen_urls = [], set()
    for src, rows in (("web", _marginalia(query)), ("wikipedia", _wikipedia(query))):
        for r in rows:
            u = r["url"].rstrip("/")
            if not u or u in seen_urls:
                continue
            seen_urls.add(u)
            r["source"] = src
            hits.append(r)
    hits = hits[:max_results]
    if not hits and not abstract:
        return ("no results found - all search backends returned nothing. "
                "Try a shorter, more general query, or fetch_url a known page.")
    lines = []
    if abstract:
        lines.append(f"Summary: {abstract}\n")
    for i, r in enumerate(hits, 1):
        lines.append(f"{i}. [{r['source']}] {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    except Exception as e:
        return f"fetch failed: {e}"
    text = _TAG_RE.sub(" ", body)
    text = _ANY_TAG_RE.sub("\n", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text).strip()
    if len(text) > MAX_FETCH_CHARS:
        text = text[:MAX_FETCH_CHARS] + f"\n\n[truncated at {MAX_FETCH_CHARS} chars]"
    return text


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web and return titles, URLs and snippets for the top results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "the search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch a specific URL and return its visible text content.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "the URL to fetch"}},
                "required": ["url"],
            },
        },
    },
]

DISPATCH = {"web_search": lambda a: web_search(a["query"]), "fetch_url": lambda a: fetch_url(a["url"])}


def chat(model, messages, verbose):
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps({"model": model, "messages": messages, "tools": TOOLS, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


_BARE_CALL_RE = re.compile(
    r"^\s*(?:<tool_call>)?\s*(?:```(?:json)?\s*)?(\{.*\})\s*(?:```)?\s*(?:</tool_call>)?\s*$",
    re.S,
)


def _fallback_parse_tool_call(content):
    """Ollama's structured `tool_calls` field depends on the model wrapping its
    call in the exact <tool_call>...</tool_call> tags its own template defines.
    At Q4 quantization qwen2.5-coder is inconsistent about this: observed
    emitting the bare JSON with no wrapper, and separately wrapping it in a
    markdown ```json code fence instead. Neither is what Ollama's parser
    looks for, so tool_calls stays empty and the call shows up as plain
    content. Recover both variants here rather than treating either as a
    final answer."""
    if not content:
        return None
    m = _BARE_CALL_RE.match(content.strip())
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if "name" in obj and "arguments" in obj:
        return [{"function": {"name": obj["name"], "arguments": obj["arguments"]}}]
    return None


SYSTEM_PROMPT = (
    "You have web_search and fetch_url tools. Use them only for facts you cannot "
    "already answer correctly - current events, prices, versions, specs, or anything "
    "that might have changed since training. For arithmetic, general knowledge, or "
    "anything you already know confidently, answer directly without calling a tool. "
    "If a search returns nothing useful twice, stop searching and answer with what "
    "you have, saying plainly what you could not confirm."
)


def run(model, prompt, verbose=True):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    seen = set()  # (name, sorted-args-json) already executed this conversation
    empty_searches = 0
    for _ in range(MAX_ROUNDS):
        resp = chat(model, messages, verbose)
        msg = resp["message"]
        tool_calls = msg.get("tool_calls") or _fallback_parse_tool_call(msg.get("content", ""))
        if not tool_calls:
            return msg.get("content", "")
        messages.append(msg)
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            key = (name, json.dumps(args, sort_keys=True))
            if verbose:
                print(f"  [tool call] {name}({args})", file=sys.stderr)
            if key in seen:
                # Observed with qwen2.5-coder:14b-instruct-q4_K_M: it can call the
                # same tool with identical arguments repeatedly even when the prior
                # result already answered the question, instead of stopping to
                # respond. Refuse the repeat and push it toward answering.
                result = ("You already called this tool with these exact arguments "
                          "and received the result above. Do not call it again with "
                          "the same arguments - answer the user's question now using "
                          "the information you already have.")
                if verbose:
                    print("  [tool call] duplicate, refused", file=sys.stderr)
            else:
                seen.add(key)
                fn = DISPATCH.get(name)
                result = fn(args) if fn else f"unknown tool: {name}"
                # Stop a model burning every round on searches that return nothing
                # (seen when DDG broke: 5 consecutive empty searches, then gave up).
                if name == "web_search" and result.startswith("no results found"):
                    empty_searches += 1
                    if empty_searches >= 2:
                        result += ("\n\nSearch is not returning results for this. Answer "
                                   "now from what you already know and state clearly "
                                   "what you could not verify.")
                if verbose:
                    preview = result[:200].replace("\n", " ")
                    print(f"  [tool result] {preview}...", file=sys.stderr)
            messages.append({"role": "tool", "content": result})
    return "(gave up after too many tool-call rounds)"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt")
    ap.add_argument("--model", default="gpt-oss-agent-32k")
    ap.add_argument("-q", "--quiet", action="store_true", help="suppress tool-call trace on stderr")
    ap.add_argument("--search-only", action="store_true",
                    help="run the search backends directly and print results; no model involved")
    args = ap.parse_args()
    if args.search_only:
        print(web_search(args.prompt))
    else:
        print(run(args.model, args.prompt, verbose=not args.quiet))
