# Agentic stack — what's installed and how to run it

Built 2026-08-29, covering `BACKLOG.md` sections **A** (agentic/orchestration) and **E**
(uncensored models). Every item below was verified by actually running it, not just installed —
where something only partly works, that is stated.

**Read the "MCP reality check" section before relying on MCP tools.** They install and connect
cleanly, but the local 20B cannot reliably drive them.

---

## Ports — nothing here starts at boot

| Service | Port | Start |
|---|---|---|
| Ollama | 11434 | `systemctl --user start ollama` |
| ComfyUI | 8188 | `systemctl --user start comfyui` |
| LocalAI | 8080 | `cd ~/AI/localai && ./local-ai run --models-path ~/AI/localai/models --backends-path ~/AI/localai/backends --address 127.0.0.1:8080` |
| OpenWebUI | 8081 | `cd ~/AI && DATA_DIR=~/AI/models/openwebui OLLAMA_BASE_URL=http://127.0.0.1:11434 ./openwebui-venv/bin/open-webui serve --port 8081` |
| LocalAGI | 3000 | `cd ~/AI/localagi && LOCALAGI_LLM_API_URL=http://127.0.0.1:11434/v1 LOCALAGI_MODEL=gpt-oss-agent-64k LOCALAGI_STATE_DIR=~/AI/models/localagi-state ./localagi serve` |
| AnythingLLM | desktop | `~/AI/anythingllm/AnythingLLMDesktop.AppImage` |

⚠️ **Only one heavy GPU consumer at a time.** LocalAI and Ollama both load models to VRAM — stop
one before starting the other. `CLAUDE.md` §1 still governs.

⚠️ **LocalAGI binds `0.0.0.0`, not localhost**, and exposes no bind-address setting. On an
untrusted network, firewall port 3000 or don't run it.

---

## A1 — MCP servers ✅ configured, 6/6 connect

In `~/.config/opencode/opencode.json`. `opencode mcp list` reports all six connected.

| Server | Transport | Purpose |
|---|---|---|
| `filesystem` | `npx @modelcontextprotocol/server-filesystem` | file access (redundant with opencode built-ins) |
| `git` | `uvx mcp-server-git` | repo status/diff/log |
| `fetch` | `uvx mcp-server-fetch` | URL retrieval |
| `memory` | `npx @modelcontextprotocol/server-memory` | persistent knowledge graph → `~/AI/models/mcp-memory/` |
| `sequential-thinking` | `npx @modelcontextprotocol/server-sequential-thinking` | structured reasoning aid |
| `playwright` | `npx @playwright/mcp --headless --isolated` | browser control (also satisfies A7) |

### MCP reality check — measured, not assumed

| Test | Result |
|---|---|
| `opencode mcp list` | **6/6 connected** |
| Context cost of 6 servers | **+5,376 tokens** (12,157 vs 6,781 baseline) |
| Plain chat with MCP enabled | ✅ works |
| **Built-in** tools (glob/read/edit) with MCP enabled | ✅ works, 18 s |
| **MCP** tool explicitly requested (`git status`) | ❌ **did not complete in 10 minutes** |

The servers are fine; the **20B at Q4 cannot reliably select and invoke MCP tools** on top of
opencode's own toolset — the same reliability ceiling documented in `OPENCODE.md`. One run also
emitted an `invalid` tool call.

First run after a config change is slow — `npx`/`uvx` fetch and cache the server packages. Early
timeouts here were that, not a real fault; once cached, startup is ~1 s per server.

**If opencode feels slow or stalls on a task, disable MCP:** set `"enabled": false` on the servers
in `opencode.json`. Built-in tools are unaffected. Re-enable when driving opencode with a stronger
model.

---

## A2 — LocalAI ✅ verified

`~/AI/localai/local-ai` (v4.9.0, 151 MB binary — no Docker, no root).

- Backend: `cuda12-llama-cpp`, installed via `./local-ai backends install localai@llama-cpp`.
- **Shares Ollama's GGUF via symlink** rather than re-downloading 8.4 GB:
  `localai/models/qwen2.5-coder-14b.gguf → ~/AI/models/ollama/blobs/sha256-ac9bc7…`
- Verified: real completion via `/v1/chat/completions` in **11 s**, 12.8 GiB VRAM.

## A3 — LocalAGI ✅ built and running

No release binaries exist and it is Docker-first, so it was **built from source**: userspace Go
toolchain at `~/AI/go` (no root), then `webui/react-ui` frontend (`npm run build`) before
`make build` — the Makefile target is `build: webui/react-ui/dist`, and the backend will not start
without that dist directory.

Serves on **:3000**, pointed at Ollama. See the bind-address warning above.

## A4 — LangGraph + CrewAI ✅ both verified

In `~/AI/agent-venv/` (806 MB).

- **LangGraph**: ReAct agent called two custom tools correctly (`vram_budget` → 6.5 GiB,
  `multiply` → 19,481). Note `create_react_agent` is deprecated → `langchain.agents.create_agent`.
- **CrewAI**: single-agent crew answered correctly against `ollama/gpt-oss-agent-64k`, and
  auto-disabled telemetry (stays fully local).

## A5 — Vector store / RAG ✅ verified end to end

`chromadb` + `lancedb` in `agent-venv`, embeddings from the already-installed `nomic-embed-text`
(768-dim). Round trip verified: three documents embedded and stored at
`~/AI/models/chroma`, then a semantic query returned the correct document first by a wide
margin (181.96 vs 396.11 distance).

## A6 — AnythingLLM ✅ installed

`~/AI/anythingllm/AnythingLLMDesktop.AppImage` (902 MB, x86_64). AppImage executes — `fusermount3`
is present, so no extraction workaround needed. It is a GUI desktop app; configure its model
provider to the Ollama endpoint on first launch.

## A7 — Playwright ✅ verified

Chromium + headless shell + ffmpeg in `~/.cache/ms-playwright` (656 MB). `--with-deps` needs root
and was skipped; the KDE desktop already supplies the system libraries. Verified by taking a real
screenshot of `example.com`. Also exposed to agents through the `playwright` MCP server.

## A8 / A9 — Speech ✅ verified as a round trip

`~/AI/speech-venv/` (438 MB): `faster-whisper` (STT) + `piper-tts` (TTS).

Piper synthesised *"The RTX 5060 Ti has sixteen gigabytes of video memory"* to WAV; faster-whisper
transcribed it back as *"The RTX 5060 Ti has 16GB of video memory"* in **0.4 s**.

Whisper runs **CPU / int8 deliberately** — the GPU is reserved for the LLM and diffusion
workloads. Voice: `~/AI/models/piper-voices/en_US-lessac-medium.onnx`.

```fish
echo "text" | ~/AI/speech-venv/bin/piper -m ~/AI/models/piper-voices/en_US-lessac-medium.onnx -f out.wav
```

## A10 — Monitoring ✅ partly

`gpustat` in `agent-venv` — works (`~/AI/agent-venv/bin/gpustat`).
**`nvtop` still needs one root command** (no passwordless sudo here):

```fish
sudo pacman -S nvtop
```

## A11 — OpenWebUI ✅ running

`~/AI/openwebui-venv/`, serving on **:8081**, `DATA_DIR=~/AI/models/openwebui`. Health endpoint
returns `{"status":true}`. First launch downloads its own `all-MiniLM-L6-v2` embedder and needs
browser first-run setup (account creation), which is why its API reports 0 models until then.

---

## E — Uncensored models

| Tag | Base | Size | Context | Status |
|---|---|---:|---:|---|
| `gemma4-heretic-64k` | gemma-4-12b-heretic-abliterated Q4_K_M | 7.4 GB | 65536 | ✅ verified |
| `qwen3vl-abliterated-64k` | Qwen3-VL-8B-Instruct-abliterated Q6_K + mmproj-f16 | 7.9 GB | 65536 | ✅ verified, vision works |
| `qwen36-abliterated-32k` | Huihui-Qwen3.6-27B-abliterated Q3_K | ~12.6 GB | 32768 | ⏳ download in progress |

Both are registered in `opencode.json` and selectable there.

### E6 — the label is not evidence, so it was tested

Identical prompt, identical settings — *"villain monologue justifying burning a village, no
disclaimers"*:

| Model | Refused? |
|---|---|
| `gpt-oss-agent-64k` | ✅ yes — *"I'm sorry, but I can't help with that."* |
| `gemma4-heretic-64k` | ❌ no — produced the in-character prose |

The abliteration is real. Keep `gpt-oss-agent-*` as the tool-calling driver (the abliterated
models were not validated for agentic tool loops); switch to `gemma4-heretic-64k` for pure
chat/roleplay where tool use is not needed.

### E2 vision needed an extra file

The Q6_K GGUF alone returns `image input is not supported - hint: … provide the mmproj`. Vision
requires the **separate `mmproj` projector**, added as a second `FROM` line in the Modelfile:

```
FROM <model>.Q6_K.gguf
FROM <model>.mmproj-f16.gguf
PARAMETER num_ctx 65536
```

After that, `ollama show` lists `vision`, and it correctly read text out of a screenshot.

### Downloading these

`ollama pull hf.co/<repo>:<quant>` works but **HuggingFace rate-limited it** at ~7.4 GB with
repeated `stream error … CANCEL; received from peer`, stalling at 99.7%. `hf download` + a
Modelfile is the reliable path, and is what `CLAUDE.md` §6 already prescribes for multi-GB weights.

`ollama create` **copies** the GGUF into its blob store, so the staging directory
(`~/AI/models/gguf-staging`) is redundant afterwards — deleting it reclaimed 14 GB. Verified the
tags still work after deletion.

---

## Performance tuning — measured

Three concurrent requests against `gpt-oss`, aggregate throughput:

| Config | Aggregate | VRAM | Placement |
|---|---:|---:|---|
| `NUM_PARALLEL=1` @ 64k (**in use**) | 92.2 tok/s | 14,219 MiB | 100% GPU |
| `NUM_PARALLEL=2` @ 64k | 114.3 tok/s | 14,909 MiB | ⚠️ 11% CPU spill |
| `NUM_PARALLEL=2` @ 32k | **121.9 tok/s** | 14,201 MiB | 100% GPU |

`NUM_PARALLEL=2` @ 32k is the throughput winner (**+32%**), but it was **not** adopted as the
default: the gain only materialises under genuinely concurrent load, while halving the context
window costs every request — and the 6 MCP servers already consume ~5.4k tokens of it. For one
person driving one opencode session, context headroom wins.

**Switch to it when running several services at once:** set `OLLAMA_NUM_PARALLEL=2` in
`configs/ollama.service` and use the `gpt-oss-agent-32k` tag. Do not pair `NUM_PARALLEL=2` with
the 64k tag — 2 × 64k of KV cache spills to CPU.

`OLLAMA_KEEP_ALIVE` was raised **5m → 30m**: with opencode, OpenWebUI, LocalAGI and CrewAI all
hitting Ollama, reloading 14 GiB across idle gaps dominated real latency.

---

## Disk

Everything new lives under `~/AI/` and is gitignored (`/agent-venv/`, `/speech-venv/`,
`/openwebui-venv/`, `/localai/`, `/localagi/`, `/anythingllm/`, `/go/`).

| Component | Size |
|---|---:|
| agent-venv (LangGraph, CrewAI, Chroma, LanceDB) | 806 MB |
| speech-venv | 438 MB |
| openwebui-venv | ~1.5 GB |
| LocalAI binary + CUDA backend | ~2.5 GB |
| LocalAGI + Go toolchain | ~1.5 GB |
| AnythingLLM AppImage | 902 MB |
| Playwright browsers | 656 MB |
| E models (in ollama blobs) | ~15 GB (+12.6 GB pending) |
