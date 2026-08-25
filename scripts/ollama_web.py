#!/usr/bin/env python3
"""
Give a tool-calling-capable Ollama model live web access.

Only qwen2.5-coder:14b-instruct-q4_K_M supports Ollama's native tool-calling
on this machine (verified: `ollama show --json` capabilities include "tools").
gemma3:12b does not - it silently ignores a `tools` field instead of using it.

Two tools are exposed: web_search (DuckDuckGo HTML, no API key) and fetch_url
(reads a page and returns its text). Stdlib only - no new dependencies.

Usage:
    ./ollama_web.py "what's the latest CachyOS kernel version?"
    ./ollama_web.py --model qwen2.5-coder:14b-instruct-q4_K_M "..."
"""
import argparse
import html.parser
import json
import re
import sys
import urllib.parse
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
UA = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0"
MAX_ROUNDS = 8          # tool-call round trips before giving up
MAX_FETCH_CHARS = 6000  # truncate fetched pages so they don't blow the context


class _DDGResultParser(html.parser.HTMLParser):
    """Extracts (title, url, snippet) triples from DuckDuckGo's HTML results page."""
    def __init__(self):
        super().__init__()
        self.results = []
        self._in_title_a = False
        self._in_snippet = False
        self._cur_url = None
        self._cur_title = []
        self._cur_snippet = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = d.get("class", "")
        if tag == "a" and "result__a" in cls.split():
            self._in_title_a = True
            self._cur_url = self._unwrap(d.get("href", ""))
            self._cur_title = []
        elif "result__snippet" in cls.split():
            self._in_snippet = True
            self._cur_snippet = []

    def handle_data(self, data):
        if self._in_title_a:
            self._cur_title.append(data)
        elif self._in_snippet:
            self._cur_snippet.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title_a:
            self._in_title_a = False
        if tag in ("a", "span") and self._in_snippet:
            # snippet elements are usually a single <a> or <span>; end on either
            if self._cur_snippet or not self._in_title_a:
                self._in_snippet = False
                if self._cur_url and self._cur_title:
                    self.results.append({
                        "title": "".join(self._cur_title).strip(),
                        "url": self._cur_url,
                        "snippet": "".join(self._cur_snippet).strip(),
                    })
                    self._cur_url = None
                    self._cur_title = []

    @staticmethod
    def _unwrap(href):
        # DDG wraps results as //duckduckgo.com/l/?uddg=<urlencoded-target>&rut=...
        if "uddg=" in href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in q:
                return q["uddg"][0]
        return href


def web_search(query: str, max_results: int = 5) -> str:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except Exception as e:
        return f"search failed: {e}"
    parser = _DDGResultParser()
    parser.feed(body)
    results = parser.results[:max_results]
    if not results:
        return "no results found"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
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
                "properties": {
                    "query": {"type": "string", "description": "the search query"},
                },
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
                "properties": {
                    "url": {"type": "string", "description": "the URL to fetch"},
                },
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
    with urllib.request.urlopen(req, timeout=120) as r:
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
    "anything you already know confidently, answer directly without calling a tool."
)


def run(model, prompt, verbose=True):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    seen = set()  # (name, sorted-args-json) already executed this conversation
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
                if verbose:
                    preview = result[:200].replace("\n", " ")
                    print(f"  [tool result] {preview}...", file=sys.stderr)
            messages.append({"role": "tool", "content": result})
    return "(gave up after too many tool-call rounds)"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt")
    ap.add_argument("--model", default="qwen2.5-coder:14b-instruct-q4_K_M")
    ap.add_argument("-q", "--quiet", action="store_true", help="suppress tool-call trace on stderr")
    args = ap.parse_args()
    print(run(args.model, args.prompt, verbose=not args.quiet))
