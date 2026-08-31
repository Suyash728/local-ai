#!/usr/bin/env python3
"""
Shared building blocks for local research tooling.

`ollama_web.py` stays as-is (fast one-shot Q&A with tool-calling). This module
holds the pieces `deep_research.py` needs that ollama_web.py either does not
expose or does badly:

  * search_hits()      - the same backends, but returning STRUCTURED hits so
                         results can be deduped and ranked across rounds.
                         ollama_web.web_search() returns a formatted string,
                         which is fine for a model but useless for a pipeline.
  * fetch_clean()      - real content extraction. ollama_web.fetch_url() strips
                         every tag with a regex, so nav/menu/footer boilerplate
                         competes with the article for the character budget.
  * chat_json()        - schema-constrained model calls. Measured 2026-08-29 on
                         gpt-oss-agent-64k: 3/3 valid JSON with `format`=schema
                         vs 2/3 without (the failure came back wrapped in a
                         ```json fence).

Stdlib only, matching the rest of scripts/.
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# Reuse the search backends and rate-limiting already proven in ollama_web.py
# rather than duplicating them - they would drift.
import ollama_web as _ow

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
UA = _ow.UA
DEFAULT_MODEL = "gpt-oss-agent-64k"


# ---------------------------------------------------------------- search ----

def shorten_query(q: str, keep: int = 6) -> str:
    """Marginalia is a small independent index and does badly with long
    natural-language queries - which is exactly what an LLM planner emits.
    Drop stopwords and keep the distinctive terms."""
    stop = {"what", "which", "how", "much", "many", "does", "do", "is", "are",
            "the", "a", "an", "of", "for", "on", "in", "to", "with", "and",
            "or", "can", "run", "using", "need", "needs", "required", "require",
            "requirements", "practical", "best", "when", "why", "should"}
    words = [w for w in re.findall(r"[\w.+-]+", q) if w.lower() not in stop]
    return " ".join(words[:keep]) or q


def search_hits(query: str, max_results: int = 6, retry_short: bool = True) -> list[dict]:
    """Structured version of ollama_web.web_search().

    Returns [{title, url, snippet, source}], deduped by normalised URL.

    Resilient by design: Marginalia is rate-limited and intermittently times
    out (measured: one query took 45.8s and returned nothing while the same
    query succeeded in 1.1s moments later). A failure of one backend must not
    zero the round, so backends are independent and a query that returns
    nothing is retried once in shortened keyword form.
    """
    hits, seen = [], set()

    def add(src, rows):
        for r in rows or ():
            u = _norm_url(r.get("url", ""))
            if not u or u in seen:
                continue
            seen.add(u)
            hits.append({"title": r.get("title", ""), "url": r["url"],
                         "snippet": r.get("snippet", ""), "source": src})

    try:
        add("web", _ow._marginalia(query))
    except Exception:
        pass
    try:
        add("wikipedia", _ow._wikipedia(query))
    except Exception:
        pass

    if not hits and retry_short:
        short = shorten_query(query)
        if short.lower() != query.lower():
            try:
                add("web", _ow._marginalia(short))
            except Exception:
                pass
            try:
                add("wikipedia", _ow._wikipedia(short))
            except Exception:
                pass
    return hits[:max_results]


def _norm_url(u: str) -> str:
    """Dedup key. ollama_web only strips a trailing slash, so http/https and
    ?utm_source= variants of one page survive as separate hits."""
    if not u:
        return ""
    try:
        p = urllib.parse.urlsplit(u)
        host = p.netloc.lower().removeprefix("www.")
        qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
              if not k.lower().startswith(("utm_", "fbclid", "gclid", "ref"))]
        return urllib.parse.urlunsplit(
            ("", host, p.path.rstrip("/"), urllib.parse.urlencode(qs), ""))
    except Exception:
        return u.rstrip("/")


# --------------------------------------------------------------- extract ----

_SKIP = {"script", "style", "nav", "header", "footer", "aside", "form",
         "noscript", "svg", "button", "select", "iframe", "figure"}
_BLOCK = {"p", "div", "section", "article", "li", "td", "blockquote", "pre",
          "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}


class _Extractor(HTMLParser):
    """Collect visible text per block, skipping chrome.

    Deliberately simple and dependency-free: agent-venv has no beautifulsoup4
    or trafilatura, and adding one for this would be the only non-stdlib dep in
    scripts/. Density filtering below recovers most of what readability buys.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.title = ""
        self._buf: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()[:200]
        if self._skip == 0 and data.strip():
            self._buf.append(data)

    def _flush(self):
        if self._buf:
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if t:
                self.blocks.append(t)
            self._buf = []

    def close(self):
        super().close()
        self._flush()


def extract_main_text(raw_html: str, max_chars: int = 12000) -> tuple[str, str]:
    """(title, text). Keeps blocks that look like prose, drops nav/link chrome.

    A block is kept if it is long enough to be a sentence, or is a short line
    inside an otherwise substantial run. Menus and link lists are typically a
    long tail of 1-4 word blocks, which this filters out.
    """
    p = _Extractor()
    try:
        p.feed(raw_html)
        p.close()
    except Exception:
        pass
    kept = [b for b in p.blocks if len(b) >= 40 or b.endswith((".", "?", "!", ":"))]
    if not kept:                       # pathological page - fall back to all text
        kept = p.blocks
    text = "\n\n".join(kept).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[truncated at {max_chars} chars]"
    return p.title, text


def fetch_clean(url: str, max_chars: int = 12000, timeout: int = 20) -> dict:
    """{url, title, text, ok, error}. Never raises - a dead link costs one
    fetch, not the whole run."""
    out = {"url": url, "title": "", "text": "", "ok": False, "error": ""}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            body = r.read(4_000_000)
        if "html" not in ctype and "text" not in ctype:
            out["error"] = f"unsupported content-type: {ctype[:40]}"
            return out
        raw = body.decode("utf-8", "replace")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out
    out["title"], out["text"] = extract_main_text(raw, max_chars)
    out["ok"] = bool(out["text"].strip())
    if not out["ok"]:
        out["error"] = "no extractable text"
    return out


# ------------------------------------------------------------------ model ----

def chat_json(system: str, user: str, schema: dict, model: str = DEFAULT_MODEL,
              timeout: int = 600, retries: int = 2) -> dict | None:
    """Schema-constrained call. Returns the parsed object, or None.

    Ollama's `format` accepts a JSON schema and constrains decoding, which
    measured materially more reliable than prompting for JSON (3/3 vs 2/3).
    The retry still strips ``` fences because a constrained decode can still
    fail on a truncated generation.
    """
    for attempt in range(retries + 1):
        body = {"model": model, "stream": False, "format": schema,
                "options": {"temperature": 0.2 if attempt == 0 else 0.0},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                content = json.load(r)["message"]["content"]
        except Exception:
            continue
        obj = _parse_loose(content)
        if obj is not None:
            return obj
    return None


def chat_text(system: str, user: str, model: str = DEFAULT_MODEL,
              timeout: int = 900) -> str:
    """Unconstrained call, for prose (the final report)."""
    body = {"model": model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["message"]["content"]
    except Exception as e:
        return f"[model call failed: {type(e).__name__}: {e}]"


_FENCE = re.compile(r"^\s*(?:```(?:json)?\s*)?(\{.*\}|\[.*\])\s*(?:```)?\s*$", re.S)


def _parse_loose(content: str):
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = _FENCE.match(content.strip())
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
    return None


def embed(text: str, model: str = "nomic-embed-text") -> list[float] | None:
    """768-dim via nomic-embed-text-v1.5. Its context is 2048 tokens, so
    callers must chunk - see memory.CHUNK_CHARS."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/embeddings",
            data=json.dumps({"model": model, "prompt": text}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)["embedding"]
    except Exception:
        return None
