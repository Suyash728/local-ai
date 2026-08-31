# Local deep research + persistent memory

A multi-round research agent that plans, searches, reads pages, checks its own coverage and writes
a cited report — then remembers it. Fully local: Ollama + the existing keyless search backends.

```fish
systemctl --user start ollama
cd ~/AI/scripts
./deep_research.py "What is a Btrfs subvolume and how do snapshots work?"
./memory.py recall "copy on write filesystem"      # what have I researched before?
./memory.py recent 10
```

Reports land in `~/AI/research/YYYY-MM-DD-slug.md` and are indexed for semantic recall.

---

## Why a pipeline and not an agent

The obvious design is one agent holding `web_search` / `fetch` / `memory` tools, free to choose.
**That was rejected on measured evidence, not taste.** `gpt-oss:20b` at Q4 cannot reliably
orchestrate a large tool namespace: with 6 MCP servers attached to opencode, an explicitly
requested tool call did not complete in 10 minutes, and even the built-in toolset produced an
`invalid` tool call (`AGENTIC-STACK.md`).

So Python owns the control flow and the model gets **one narrow job per call, with no tools
attached at all**:

```
 PLAN       model    question -> 2-5 search queries              (JSON schema)
 SEARCH     python   run each query through the backends
 TRIAGE     model    pick which results are worth reading        (JSON schema)
 FETCH      python   download + extract main text
 EXTRACT    model    one page -> summary + quoted findings       (JSON schema)   [map]
 GAP CHECK  model    is this enough? what is missing?            (JSON schema)
   -> loop back to SEARCH with new queries, or stop
 SYNTHESIZE model    findings -> cited report                    (prose)         [reduce]
```

The model never selects a tool; it answers a question about text. Every stage is independently
testable, and a failure in one degrades the run instead of ending it.

## Structured output — measured, not assumed

Every structured stage uses Ollama's `format` with a JSON schema. This was measured on
`gpt-oss-agent-64k` before the pipeline was built:

| Mode | Valid JSON |
|---|---|
| `format` + JSON schema | **3/3** |
| plain "return JSON" prompt | 2/3 — the failure came back wrapped in a ` ```json ` fence |

`chat_json()` also passes `temperature: 0.2`, then `0.0` on retry — the tag itself ships
`temperature: 1`, which is the worst possible setting for schema-constrained decoding.

---

## Files

| Path | Role |
|---|---|
| `scripts/research_lib.py` | shared: structured search, content extraction, schema-constrained model calls, embeddings |
| `scripts/deep_research.py` | the pipeline + CLI |
| `scripts/memory.py` | SQLite (authoritative) + Chroma (semantic recall) |
| `scripts/ollama_web.py` | **unchanged** — still the fast one-shot Q&A tool (`WEB-ACCESS.md`) |
| `~/AI/research/research.db` | sessions, sources, findings |
| `~/AI/research/*.md` | the reports themselves |

`ollama_web.py` was deliberately left alone. It is documented, verified and serves a different
purpose; `research_lib.py` imports its search backends rather than duplicating them, so the
rate-limiting logic has exactly one home.

## Content extraction — the fix that mattered most

`ollama_web.fetch_url()` strips every tag with a regex, so navigation chrome competes with the
article for the character budget. Measured on the same page:

```
old: 'Btrfs - Wikipedia\n\nJump to content\n\nMain menu\n\nmove to sidebar\n\nhide\n\nNavigation...'
new: 'SUSE, Meta, Western Digital, Oracle Corporation, Fujitsu, Fusion-io, Intel...'
```

`research_lib.extract_main_text()` uses stdlib `html.parser`: it skips `script/style/nav/header/
footer/aside/form` subtrees entirely, treats only block elements as line breaks (so inline `<b>`
and `<a>` no longer shatter sentences — which matters because citations depend on contiguous
verbatim quotes), and keeps blocks that look like prose rather than menu entries.

**No new dependency.** `agent-venv` has no beautifulsoup4 or trafilatura, and neither actually
solves this — bs4 gives a better parser but no readability heuristic. If extraction quality proves
insufficient on real pages, `extract_main_text()` is a single seam to swap.

## Citations are verified, not trusted

The extract stage must return a **verbatim quote** for every finding. Python then checks that the
quote is really a span of the fetched page (`_quote_on_page`), and only quote-verified findings are
passed to synthesis. A fabricated quote is dropped rather than cited.

Measured on the Btrfs run: **16 of 18 findings quote-verified** across 3 pages (6/6, 5/6, 5/6).

---

## Verified end to end — 2026-08-31

Question: *"What is a Btrfs subvolume and how do snapshots and copy-on-write work?"*

```
[memory]  1 related past session found
[round 1] 5 queries -> 15 hits -> 4 fetched -> 0 relevant
[gap]     missing: "only basic definitions, no mechanism detail"
[round 2] 3 new queries -> 15 hits -> 4 fetched -> 18 findings (16 verified)
[synth]   from 4 pages
done in 471s
```

**The multi-round loop earned its place on this run.** Round 1 produced nothing usable; the gap
check diagnosed why and rewrote the queries; round 2 succeeded. A single-shot search would have
returned nothing.

The report opened with a direct 3-sentence answer, then a detail table, then explicit limitations,
citing `[1]`-`[4]` against official `btrfs.readthedocs.io` documentation — triage chose primary
sources over blogs unprompted. One `403 Forbidden` was skipped without affecting the run.

Memory recall across sessions, with wording that appears nowhere in the stored text:

```
$ ./memory.py recall "copy on write filesystem snapshots"
  [227.24] session 3: What is a Btrfs subvolume and how do snapshots and copy-on-write work?
  [490.09] session 1: What are the VRAM requirements for Wan 2.2 video generation?
```

## Known limitation: search coverage, not the pipeline

The first end-to-end attempt — *"What VRAM does Wan 2.2 need on a 16GB GPU?"* — **returned zero
sources**, and that failure is worth recording rather than hiding.

The pipeline behaved correctly. Marginalia's index is small and has little on recent niche tech, so
triage was choosing between a forum thread, an unrelated idle-power post and a CUDA OOM thread. The
extract stage read them and correctly judged all four irrelevant rather than inventing an answer.

**The ceiling here is the free keyless search backends, not the agent.** Marginalia is an
independent crawler that favours the non-commercial web; Wikipedia covers established topics well.
Recent product specifics are the weak spot. If that matters, adding one keyed backend (Brave,
Tavily) is a single function with the same signature as `_marginalia` — but it would break the
"no API keys" property the rest of this stack holds to.

Also measured: **the planner writes long natural-language queries, which a small index handles
badly.** `research_lib.shorten_query()` retries any query that returns nothing in stopworded
keyword form. Before that fix a round could return 0 hits; after it, 5 consecutive queries returned
23 hits with no stalls.

---

## Memory design

Two stores, deliberately:

- **SQLite** (`~/AI/research/research.db`) — authoritative. Sessions, sources, findings. Exact,
  greppable, survives anything.
- **Chroma** (`~/AI/models/chroma`, collection `research`) — semantic recall only. Rebuildable
  from SQLite with `./memory.py reindex`, so it is a cache, not a source of truth.

`nomic-embed-text` is **v1.5, 768-dim, with a 2048-token context**. That context is why
`CHUNK_CHARS = 6000` (~1500 tokens): a longer chunk is silently truncated by the embedder, which
degrades recall without erroring. Chunks are prefixed with the session question so a chunk from
deep in a report still carries a topical anchor.

⚠️ The Chroma collection is created with `embedding_function=None`. Without it,
`get_or_create_collection` installs Chroma's default 384-dim ONNX MiniLM on a collection that only
ever receives 768-dim vectors — dormant while embeddings are passed explicitly, then fatal the
moment anything queries by text.

### VRAM: embeddings evict the LLM

`OLLAMA_MAX_LOADED_MODELS=1`, and gpt-oss-agent-64k is ~14 GiB resident. **Every embedding call
evicts it.** The pipeline is therefore structured so embeddings happen in exactly two phases,
both outside the model loop:

```
recall     -> nomic loads          (start of run)
PLAN..WRITE-> gpt-oss loads        (all model calls, zero swaps)
index      -> nomic loads          (end of run)
```

Interleaving an embed into the loop would cost a ~14 GiB reload each time. Keep it out.

---

## Options

```fish
./deep_research.py "question" --rounds 3        # more gap-check iterations (default 2)
./deep_research.py "question" --max-fetch 6     # pages read per round (default 5)
./deep_research.py "question" --no-memory       # skip recall and persistence
./deep_research.py "question" --model qwen36-abliterated-16k
```

**Timing:** ~8 minutes for 2 rounds and 4 sources. Fetching and prefill dominate, not generation.
Stop ComfyUI first — `CLAUDE.md` §1 still governs, one GPU workload at a time.
