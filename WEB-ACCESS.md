# Giving the Ollama models web access

Companion to `OLLAMA-ACCESS.md` (how to talk to the models) and `README.md` (what's installed).
This covers `scripts/ollama_web.py` — a script that lets a tool-calling-capable model search the
web and fetch pages before answering.

**Read this before trusting an answer from it.** The mechanism works and is verified below with
real transcripts, but the model's judgement about *when* to use it is unreliable — documented
honestly, with numbers, in the Known limitations section. Don't skip that part.

---

## Why a script, not a feature you turn on

Ollama does not ship a web-search tool. Getting a model to search the web requires three things
working together: the model deciding it needs to search, emitting a structured request to do so,
and *something* on the client side actually performing that search and feeding the result back.
Ollama only provides the middle piece (the tool-calling protocol) — the actual search execution
has to be supplied by the caller. `scripts/ollama_web.py` is that caller.

## Which model — and why only one

```fish
ollama show --json qwen2.5-coder:14b-instruct-q4_K_M | grep -o '"capabilities":\[[^]]*\]'
```

Only `qwen2.5-coder:14b-instruct-q4_K_M` has `tools` in its capability list.
`gemma3:12b` does not — verified by sending it a `tools` field directly: it responds normally and
never touches `tool_calls`, it just silently ignores the field. There is no way to give gemma3 web
access through Ollama's native mechanism; it would need a different approach entirely
(e.g. manually injecting search results into the prompt yourself, with no model-driven decision
about when to search).

## No API key needed

Search runs through `html.duckduckgo.com/html/` — DuckDuckGo's server-rendered results page, no
account or key required. This is intentionally the free option, at the cost of being somewhat more
fragile than a paid search API (see Known limitations).

---

## Usage

```fish
./scripts/ollama_web.py "what's the latest CachyOS kernel version?"
./scripts/ollama_web.py --model qwen2.5-coder:14b-instruct-q4_K_M "..."
./scripts/ollama_web.py -q "..."          # suppress the tool-call trace, print only the answer
```

Requires `ollama` running (`systemctl --user start ollama`). Stdlib only — no packages to install,
no new venv, matches this project's existing "thin script against the API" pattern (see how every
batch comparison in `MODEL-COMPARISON.md` was generated the same way against ComfyUI).

The verbose trace (default on, `-q` to silence) prints each tool call and a preview of its result
to stderr, so you can see what it searched and what it found — useful for judging whether to trust
the final answer.

---

## What it actually does

Two tools are exposed to the model:

- **`web_search(query)`** — parses DuckDuckGo's HTML results page with Python's stdlib
  `html.parser` (not regex, so it survives markup changes better) into title/URL/snippet triples,
  unwrapping DDG's redirect-wrapped URLs back to the real target.
- **`fetch_url(url)`** — fetches a page, strips scripts/styles/tags, unescapes entities, collapses
  whitespace, and truncates at 6000 characters so a single page can't blow the model's context.

The loop: send the conversation with both tool definitions → if the model's response contains a
tool call, run it and append the result as a `role: tool` message → repeat, up to 8 rounds → return
whichever response has no further tool call as the final answer.

### A real defect found and fixed during testing: tool calls arriving as plain text

Ollama populates `message.tool_calls` only when the model wraps its call in the exact
`<tool_call>...</tool_call>` tags its own chat template defines. At Q4 quantization,
qwen2.5-coder was observed doing this three different ways across repeated identical queries:
tagged correctly, as bare JSON with no wrapper, and wrapped in a markdown ` ```json ` code fence.
Only the first form gets picked up by Ollama's own parser — the other two silently land in
`message.content` as if the model had just answered in text, which would have made the tool
invisible to this script entirely.

Fixed with a fallback regex that recognizes all three forms and reconstructs a synthetic
`tool_calls` entry so none of them get missed. Verified by triggering all three variants directly
against the raw API and confirming each is now caught.

### A real defect found and fixed: identical repeated tool calls

In testing, the model called `fetch_url` on the same URL five times in a row — after the *first*
fetch already contained the answer in plain text (`Today's Date is Wednesday August 26, 2026`).
It wasn't missing the answer; it just didn't recognize it had one and kept calling instead of
responding.

Fixed with duplicate-call detection: if a tool is called with arguments identical to a previous
call in the same conversation, the script refuses to run it again and instead returns a message
telling the model it already has this result and should answer now. This reliably broke the loop
in testing — the model responded correctly on the next turn every time this was observed.

---

## Verified working, real transcripts

```
$ ./scripts/ollama_web.py -q "Search the web: what year did the RTX 5060 Ti release?"
The RTX 5060 Ti was released on April 16, 2025.

$ ./scripts/ollama_web.py -q "Search: is CachyOS based on Arch Linux?"
CachyOS is based on Arch Linux.

$ ./scripts/ollama_web.py "What is today's exact date? Search the web to confirm it."
  [tool call] web_search({'query': "today's date"})
  [tool call] fetch_url({'url': 'https://www.calendardate.com/todays.htm'})
  [tool call] fetch_url({'url': 'https://www.calendardate.com/todays.htm'})
  [tool call] duplicate, refused
  ...
Today's exact date is Wednesday, August 26, 2026.
```

All three checked against ground truth: the date matched the system clock, and the GPU release
date and CachyOS's base distro are independently verifiable facts, both correct.

---

## Known limitations — read before trusting an answer

**The model over-uses the tool, sometimes badly.** Asked `"What is 12 * 7? No need to search"` —
an explicit instruction not to search, for something the model can trivially compute — it searched
Google, then a math site, then a second math site, then a third, burning through most of the round
budget before either answering or giving up. A system prompt was added telling it to only use
tools for things it can't already answer confidently. **Measured effect: 1 success in 3 repeated
identical attempts**, the other two exhausted all 8 rounds and gave up with no answer. This is
inherent, sampling-driven model behavior at Q4 quantization on a 14B model doing agentic tool use —
not something further prompt engineering reliably fixes. Simple factual/computational questions may
be faster and more reliable asked with `ollama run` directly (no tools attached at all) than through
this script.

**DuckDuckGo's HTML endpoint is not an official API.** It can change format or start blocking
without notice — this is the trade-off for not needing an API key. If `web_search` starts
returning "no results found" for queries that clearly have results, this is the first thing to
suspect.

**`fetch_url` will hit bot walls, 403s, 404s, and 429s regularly** — real websites block scrapers.
Observed all four during testing on ordinary tech/spec sites. The model usually tries a different
result when this happens, but it costs a round each time.

**Content extraction is naive.** `fetch_url` strips all HTML tags indiscriminately rather than
identifying the actual article content — a heavily-templated page (nav menus, cookie banners, etc.)
can bury the useful text in boilerplate, or push it past the 6000-character truncation on a long
page. This was directly responsible for one confusing debugging session — always check the tool
trace (drop `-q`) to see what the model actually saw before trusting an answer built on `fetch_url`
output.

**No result caching, no rate limiting, no robots.txt respect.** Fine for occasional personal use;
would need hardening before any higher-volume or shared use.
