# Giving the Ollama models web access

Companion to `OLLAMA-ACCESS.md` (how to talk to the models) and `README.md` (what's installed).
This covers `scripts/ollama_web.py` — a script that lets a tool-calling-capable model search the
web and fetch pages before answering.

**Update 2026-08-27 — the search backend was replaced.** DuckDuckGo put its HTML endpoint behind
an anti-bot challenge, and the script broke completely: every query returned `no results found`.
Search now runs on three keyless JSON APIs instead. See "Search backends" below. The default model
also changed to `gpt-oss-agent-32k` (32k context) — search results plus a fetched page overflow
the stock 4096-token context.

**Update 2026-08-26:** the default model changed from `qwen2.5-coder:14b-instruct-q4_K_M` to
gpt-oss, which is verified categorically more reliable at tool-calling — see "Which model"
below. The Known limitations section further down was written against qwen2.5-coder's behavior;
it still applies if you pass `--model qwen2.5-coder-agent-32k`, but gpt-oss did not
reproduce any of those failures in the same tests.

**Read this before trusting an answer from it.** The mechanism works and is verified below with
real transcripts, but a model's judgement about *when* to use it can be unreliable — documented
honestly, with numbers, in the Known limitations section. Don't skip that part.

---

## Why a script, not a feature you turn on

Ollama does not ship a web-search tool. Getting a model to search the web requires three things
working together: the model deciding it needs to search, emitting a structured request to do so,
and *something* on the client side actually performing that search and feeding the result back.
Ollama only provides the middle piece (the tool-calling protocol) — the actual search execution
has to be supplied by the caller. `scripts/ollama_web.py` is that caller.

## Which model

```fish
curl -s http://127.0.0.1:11434/api/show -d '{"model":"gpt-oss:20b"}' | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['capabilities'])"
```

Two models on this machine have `tools` in their capability list: `gpt-oss:20b` and
`qwen2.5-coder:14b-instruct-q4_K_M`. `gemma3:12b` does not — verified by sending it a `tools` field
directly: it responds normally and never touches `tool_calls`, it just silently ignores the field.
There is no way to give gemma3 web access through Ollama's native mechanism; it would need a
different approach entirely (e.g. manually injecting search results into the prompt yourself, with
no model-driven decision about when to search).

**Default: `gpt-oss:20b`.** Head-to-head against qwen2.5-coder on the identical failure cases that
motivated the fallback-parsing and duplicate-call-guard code below:

| | qwen2.5-coder:14b-instruct-q4_K_M | gpt-oss:20b |
|---|---|---|
| Structured `tool_calls` populated | inconsistent — 3 different malformed text forms observed | clean every time tested |
| Date query (search → fetch → answer) | needed the duplicate-call guard to escape a 5x identical-fetch loop | one search, correct answer, no loop |
| "12 * 7, no need to search" | 1 success in 3 identical attempts, other 2 exhausted 8 rounds searching math sites | 3 for 3, answered directly, zero tool calls |
| Measured throughput | not benchmarked here | **75.8 tok/s**, 100% GPU, 14.2 GiB VRAM |

The likely reason: gpt-oss uses OpenAI's Harmony response format, which Ollama parses internally
(token injection, role/channel handling) rather than relying on the model reproducing an exact
`<tool_call>` tag sequence in its own output. qwen2.5-coder's tool format depends on the model
getting that tag-wrapping right every time at Q4 quantization, and it doesn't always.

`qwen2.5-coder:14b-instruct-q4_K_M` remains available via `--model` — still the better pick if you
specifically need its code-domain knowledge for a query, but tested less reliable as a *tool-use*
loop.

## Search backends — no API key, no extra service

**What broke.** Until 2026-08-27 search scraped `html.duckduckgo.com/html/`. DDG now answers that
endpoint with **HTTP 202 and an anti-bot challenge page** (`anomaly` ×67, `challenge` ×13, zero
result markers), so every query returned nothing. Checked at the same time and also closed to
plain scraping: `lite.duckduckgo.com` (same challenge), `searx.be` (captcha), Startpage (Anubis
proof-of-work), Mojeek (requires JavaScript).

Keyless *general* web search by scraping is effectively over. `web_search` now merges three JSON
APIs that do still work:

| Backend | Role | Notes |
|---|---|---|
| **Marginalia** | the general web index — main engine | independent crawler, no key. Rate limited, so calls are spaced 1.5 s apart and retried once |
| **Wikipedia** | encyclopedic backstop | always answers, never rate limited |
| **DuckDuckGo Instant Answer** | one-line abstract | official API. Good on entities (`btrfs`), returns empty for open-ended questions |

Results are merged, deduplicated by URL, and tagged with their source (`[web]`, `[wikipedia]`) so
you can see where each came from.

**Alternatives considered and rejected.** Self-hosting SearXNG would give real meta-search, but
neither podman nor docker is installed and there is no `searxng` package in the repos — it would
have meant a container runtime plus a new service for a script that is meant to be thin. A keyed
API (Brave, Tavily) works but requires an account. The current setup needs neither, which matches
how everything else here is built.

If Marginalia ever goes the way of DDG, adding a keyed backend is a small change — `_marginalia()`
is one self-contained function with the same signature as `_wikipedia()`.

---

## Usage

```fish
systemctl --user start ollama                    # required first

./scripts/ollama_web.py "what is a btrfs subvolume?"
./scripts/ollama_web.py -q "..."                 # answer only, no tool-call trace
./scripts/ollama_web.py --model qwen2.5-coder-agent-32k "..."

# check the search backends alone, no model, no ollama needed - use this first
# if answers look wrong, to tell a search problem from a model problem
./scripts/ollama_web.py --search-only "btrfs subvolume snapshot"
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

- **`web_search(query)`** — queries Marginalia, Wikipedia and DDG's Instant Answer API, merges the
  hits, drops duplicate URLs and returns up to 6 tagged title/URL/snippet triples, with a
  `Summary:` line first when an abstract exists.
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

### A third guard, added when DDG broke: escaping dead searches

When DuckDuckGo started returning nothing, the failure mode was not an error — it was the model
burning all 8 rounds on searches that each returned `no results found`, then giving up with no
answer at all. The script now counts empty searches: after the second one it appends an
instruction telling the model to stop searching and answer from what it knows, stating plainly
what it could not verify. A degraded answer beats eight wasted rounds and silence.

---

## Verified working, real transcripts

### 2026-08-27, after the backend swap

```
$ ./scripts/ollama_web.py "Find the ComfyUI GitHub repository and tell me what its README says it is."
  [tool call] web_search({'query': 'ComfyUI GitHub repository README says it is'})
  [tool call] web_search({'query': 'ComfyUI'})
  [tool call] web_search({'query': 'ComfyUI GitHub'})
  [tool call] fetch_url({'url': 'https://github.com/comfyanonymous/ComfyUI'})
  [tool call] fetch_url({'url': 'https://raw.githubusercontent.com/.../README.md'})
**GitHub repository** `https://github.com/comfyanonymous/ComfyUI`
(refined its query three times, found the repo, then fetched the raw README rather than
 trusting the rendered page - the whole loop worked as designed)
```

`--search-only` on three queries, no model involved — Marginalia returned relevant hits for all
three, including the niche one:

```
$ ./scripts/ollama_web.py --search-only "what is NVFP4 quantization"
1. [web] LLM Inference on RTX PRO 6000 Blackwell · eordano's garden
2. [web] In search of wasted bits: how much information do LLM weights carry? | Doubleword
3. [web] NVFP4 GEMV – simons blog
```

### gpt-oss:20b (earlier transcripts, DDG-era backend)

```
$ ./scripts/ollama_web.py "What is today's exact date? Search the web to confirm it."
  [tool call] web_search({'query': 'current date 2026-08-26'})
The exact date today is Wednesday, August 26, 2026.
(one search, no loop, no duplicate-call guard needed)

$ ./scripts/ollama_web.py "Search and tell me: what does the acronym NVFP4 stand for?"
  [tool call] web_search({'query': 'NVFP4 acronym'})
  [tool call] fetch_url({'url': 'https://developer.nvidia.com/blog/introducing-nvfp4...'})
NVFP4 stands for NVIDIA Floating-Point 4 - the 4-bit floating-point data type NVIDIA
introduced with its Blackwell GPU architecture...

$ for i in 1 2 3; do ./scripts/ollama_web.py -q "What is 12 * 7? No need to search."; done
12 × 7 = 84.
12 × 7 = **84**
12 × 7 = 84.
(3 for 3, zero tool calls - see the head-to-head table above for qwen's score on the same prompt)
```

### qwen2.5-coder:14b-instruct-q4_K_M (via `--model`)

```
$ ./scripts/ollama_web.py --model qwen2.5-coder:14b-instruct-q4_K_M -q "Search the web: what year did the RTX 5060 Ti release?"
The RTX 5060 Ti was released on April 16, 2025.

$ ./scripts/ollama_web.py --model qwen2.5-coder:14b-instruct-q4_K_M "What is today's exact date? Search the web to confirm it."
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

## Known limitations of qwen2.5-coder as the tool-calling model — read before using `--model qwen2.5-coder:14b-instruct-q4_K_M`

None of the following were reproduced with the current default, `gpt-oss:20b`, in the same tests
(see the head-to-head table above). They apply specifically when overriding `--model` to
qwen2.5-coder.

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
