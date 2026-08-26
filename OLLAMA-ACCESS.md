# Accessing the Track A models (Ollama)

Companion to `README.md` (what's installed, service control table, VRAM budget) and
`COMFYUI-WEB.md` (the image-generation side). This file is about actually *talking* to the four
LLMs — the different ways in, and which one to reach for.

---

## Start it

```fish
systemctl --user start ollama
```

Ready in a couple of seconds. Verify:

```fish
curl -s http://127.0.0.1:11434/api/version
```

Same on-demand pattern as ComfyUI — **not** enabled at boot or on login, so an idle machine draws
no GPU power. `systemctl --user stop ollama` when done, which also frees VRAM immediately
(`OLLAMA_KEEP_ALIVE=5m` releases it automatically anyway after 5 minutes idle).

⚠️ **Ollama and ComfyUI cannot both hold a model in VRAM.** Largest LLM (9.0 GB) plus any image
model (8-15 GB) exceeds 16 GiB. Stop one before starting the other if switching between them.

---

## The four models

| Model | Role | Notes |
|---|---|---|
| `gpt-oss:20b` | tool-calling / agentic driver | 75.8 tok/s measured — see `WEB-ACCESS.md` |
| `qwen2.5-coder:14b-instruct-q4_K_M` | code chat / edit / agent | 44.0 tok/s measured |
| `gemma3:12b` | general purpose | 128k context, vision-capable, 47.8 tok/s |
| `qwen2.5-coder:1.5b-base` | tab-autocomplete **only** | base model, not instruct — continues code rather than chatting. Wrong choice for a conversation. |
| `nomic-embed-text` | embeddings | for `@codebase`-style indexing, not text generation |

`OLLAMA_MAX_LOADED_MODELS=1` is set — switching between the two big models evicts whichever was
resident. `ollama ps` shows what's currently loaded.

---

## Ways to talk to it

### Interactive terminal chat

```fish
ollama run qwen2.5-coder:14b-instruct-q4_K_M
```

Drops into a REPL. `/bye` exits the chat (does not stop the server — it's still running
underneath). `/set parameter num_ctx 32768` mid-session raises context length past the 16k default
if a long conversation needs it (costs more VRAM — see the KV-cache table in `README.md`).

### One-shot from the shell

```fish
ollama run qwen2.5-coder:14b-instruct-q4_K_M "write a fizzbuzz in rust"
```

No REPL, just the response to stdout. Useful for scripting or a quick single question.

### HTTP API directly

Ollama's native endpoint:

```fish
curl -s http://127.0.0.1:11434/api/generate -d '{
  "model": "qwen2.5-coder:14b-instruct-q4_K_M",
  "prompt": "explain what chattr +C does on btrfs",
  "stream": false
}'
```

`stream: false` returns one JSON object with the full response; omit it (or set `true`) for
newline-delimited streaming chunks, which is the default. This is the path every verification
render/completion in this project's history actually used — same idea as scripting ComfyUI's
`/prompt` endpoint instead of clicking Queue.

### OpenAI-compatible endpoint

```
http://127.0.0.1:11434/v1
```

Point any OpenAI-SDK-shaped tool at this — Continue.dev, Zed, Aider, a custom script using the
`openai` Python package with `base_url` overridden, etc. Config snippets for the first three are
in `configs/` (`continue-config.yaml`, `zed-settings-snippet.json`, `aider.conf.yml`), though as of
writing none of those editors are actually installed — the configs are staged for whenever they
are.

Example with `curl` directly against the OpenAI-shaped path:

```fish
curl -s http://127.0.0.1:11434/v1/chat/completions -d '{
  "model": "gemma3:12b",
  "messages": [{"role": "user", "content": "hello"}]
}'
```

### Embeddings

```fish
curl -s http://127.0.0.1:11434/api/embed -d '{
  "model": "nomic-embed-text",
  "input": ["text to embed", "a second string"]
}'
```

Returns 768-dimensional vectors, one per input string.

---

## Picking the right access method

| Situation | Use |
|---|---|
| Quick question from the terminal | `ollama run <model> "..."` one-shot |
| Back-and-forth conversation | `ollama run <model>` interactive |
| Scripting, batch queries, or need the raw JSON | `/api/generate` or `/api/chat` |
| Wiring up an editor or an existing OpenAI-SDK tool | `/v1` endpoint |
| Building a search/RAG index | `/api/embed` with `nomic-embed-text` |

---

## Troubleshooting

See `README.md`'s troubleshooting table for service-level issues (not starting, wrong processor,
port conflicts). The one specific to *using* the models rather than running the service:

**Response feels slow to start** — first request after `ollama start` (or after switching which
model is loaded) pays a one-time load cost: ~3.9s measured for the 14B from a DRAM-less QLC drive.
Subsequent requests to the same loaded model are warm.
