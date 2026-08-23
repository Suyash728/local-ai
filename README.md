# Local AI Stack — `~/AI`

What is installed, where things live, and how to start them.
**Rules for Claude Code sessions:** `CLAUDE.md`. **Full plan & reasoning:** `PLAN.md`.

| | |
|---|---|
| Machine | Ryzen 5 5600 · RTX 5060 Ti 16G (sm_120) · 31 GiB RAM · CachyOS |
| Track A — LLMs | ✅ **DONE & VERIFIED** (2026-08-23) |
| Track B — ComfyUI | ⬜ not started |
| Track C — Video | ⛔ deferred by decision (needs 64 GiB RAM) |
| Free disk | ~115 GiB |

---

## Quick start

```fish
systemctl --user start ollama      # start the server (on demand)
ollama run qwen2.5-coder:14b-instruct-q4_K_M
systemctl --user stop ollama       # frees VRAM immediately
```

> **After every reboot the service is DOWN. That is intentional** — the unit is not
> enabled at boot, so an idle machine draws no GPU power. `systemctl --user start ollama`.
> It also stops at logout (`Linger=no`).

| Command | What it does |
|---|---|
| `systemctl --user start\|stop\|restart ollama` | control the server |
| `systemctl --user status ollama` | is it running? |
| `journalctl --user -u ollama -f` | live server log |
| `ollama ps` | which model is loaded, VRAM use, context, TTL |
| `ollama list` | installed models |
| `curl -s localhost:11434/api/version` | health check |

---

## Installed — Track A

### System packages (pacman, 5.93 GiB)
`ollama 0.32.15-1.1` · `ollama-cuda 0.32.15-1.1` · `cuda 13.3.1` · `gcc15` · `gcc15-libs` · `cccl`

`cuda` is a **hard dependency** of `ollama-cuda`, not an optional extra. It also provides
**`nvcc` at `/opt/cuda/bin/nvcc`** (v13.3.73, `NVCC_CCBIN=/usr/bin/g++-15`) — needed if
SageAttention ever gets built from source in Track B.

### Models (18 GiB, in `~/AI/models/ollama`)

| Model | Size | Role | Measured |
|---|---:|---|---|
| `qwen2.5-coder:14b-instruct-q4_K_M` | 9.0 GB | code chat / edit / agent | **44.0 tok/s** |
| `gemma3:12b` | 8.1 GB | general purpose, 128k ctx, vision | **47.8 tok/s** |
| `qwen2.5-coder:1.5b-base` | 986 MB | tab autocomplete (FIM) | **265.1 tok/s** |
| `nomic-embed-text` | 274 MB | `@codebase` indexing | 768-dim |

**Why `1.5b-base` and not instruct:** autocomplete is fill-in-the-middle, not chat, and it is
latency-bound. A 14B would feel awful for tab-completion. Verified: given
`def binary_search(arr, target):` it continues the body rather than explaining it.

---

## Where models live

```
~/AI/models/              ← dedicated Btrfs subvolume, chattr +C (nodatacow)
├── hf/                   ← HF_HOME
├── ollama/               ← OLLAMA_MODELS  (blobs/ + manifests/)
└── comfyui/{diffusion_models,text_encoders,vae,loras,clip_vision}   ← Track B
```

`~/AI/models` is a **real Btrfs subvolume**, not a plain directory. `@home` *is* snapshotted on
this machine, and Btrfs re-enables CoW for the first write to a `+C` file after each snapshot —
so `chattr +C` alone would not have stuck. A nested subvolume is excluded from its parent's
snapshots (Btrfs snapshots are not recursive), which isolates the weights and makes `+C` durable.
Verified: every downloaded blob carries the `C` flag.

`FLUX.1-dev-NVFP4/` is still at `~/AI/` and moves into `models/comfyui/diffusion_models/` during
Track B — that move is a real copy across the subvolume boundary, which is what applies `+C` to it.

---

## Configuration

### fish universal variables (persist across sessions)
```fish
set -Ux HF_HOME                  /home/suyash/AI/models/hf
set -Ux OLLAMA_MODELS            /home/suyash/AI/models/ollama
set -Ux OLLAMA_HOST              127.0.0.1:11434
set -Ux OLLAMA_FLASH_ATTENTION   1
set -Ux OLLAMA_KV_CACHE_TYPE     q8_0
set -Ux OLLAMA_MAX_LOADED_MODELS 1
```

### systemd user unit
Live at `~/.config/systemd/user/ollama.service`; tracked copy in `configs/ollama.service`.

⚠️ **systemd does not inherit fish variables.** Every var is repeated as an `Environment=` line
inside the unit. **If you change one, change it in both places.** The unit also sets
`OLLAMA_KEEP_ALIVE=5m` so an idle session releases VRAM.

After editing: `systemctl --user daemon-reload; systemctl --user restart ollama`

---

## VRAM budget (16311 MiB total; desktop uses ~0.9–1.0 GiB)

Qwen2.5-Coder-14B: 48 layers, 8 KV heads, head_dim 128 → **192 KiB of KV cache per token**.

| Config | Weights | KV | Total | |
|---|---:|---:|---:|---|
| 32k ctx, fp16 KV | 8.37 | 6.00 | 14.37 | ✗ no headroom |
| **16k ctx, q8_0 KV** | 8.37 | **1.59** | **~10.0** | ✓ **in use** |
| 32k ctx, q8_0 KV | 8.37 | 3.19 | 11.6 | ✓ if you need long context |

**Measured at 16k / q8_0:** `100% GPU`, `llama_kv_cache: K (q8_0) 816 MiB, V (q8_0) 816 MiB`,
llama-server resident at 10062 MiB, total GPU 11070 / 16311 MiB.

The 14B and gemma3 **cannot both stay resident** (9.0 + 8.1 GB > 14.4 GiB usable).
`OLLAMA_MAX_LOADED_MODELS=1` makes the eviction deterministic instead of a surprise OOM.

To raise context: `/set parameter num_ctx 32768` in `ollama run`, or `"num_ctx"` in the API call.
The server's own default is 4096 (derived from VRAM) — **always set it explicitly**.

---

## Editor integration

Configs are staged in `configs/`. None of these editors are installed yet.

| Editor | Install |
|---|---|
| Continue.dev | VS Code ext `Continue.continue`, then `cp configs/continue-config.yaml ~/.continue/config.yaml` |
| Zed | not installed; merge `configs/zed-settings-snippet.json` into `~/.config/zed/settings.json` |
| Aider | `uv tool install aider-chat`, `cp configs/aider.conf.yml ~/.aider.conf.yml`, `set -Ux OLLAMA_API_BASE http://127.0.0.1:11434` |

Endpoint for anything OpenAI-compatible: **`http://127.0.0.1:11434/v1`**

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `could not connect to ollama server` | Not running — it never auto-starts. `systemctl --user start ollama` |
| Server gone after reboot/logout | By design. Same fix. |
| Model on CPU instead of GPU | `ollama ps` → PROCESSOR column. Check `journalctl --user -u ollama` for `library=CUDA compute=12.0` |
| Slow first response | Cold load of 9 GB from a DRAM-less QLC drive (~3.9 s measured). Subsequent calls are warm. |
| Port 11434 in use | The system unit may have started. `systemctl is-active ollama.service` — it should be `inactive`. Optionally `sudo systemctl mask ollama.service`. |
| VRAM not released | `OLLAMA_KEEP_ALIVE=5m`. Force now: `systemctl --user stop ollama` |

### Optional hardening (not done)
```fish
sudo systemctl mask ollama.service    # system unit is already disabled+inactive
```

---

## Verification record — 2026-08-23

- `library=CUDA compute=12.0 name=CUDA0 ... libdirs=ollama,cuda_v13 driver=13.3` → sm_120 on the CUDA 13 backend
- Streamed completion from `qwen2.5-coder:14b-instruct-q4_K_M`: 99 tokens, 44.0 tok/s, `done_reason: stop`
- `ollama ps` → `100% GPU`, context 16384; `nvidia-smi` → llama-server at 10062 MiB
- All 4 models generate/embed correctly; 0 pull failures
- Idle (server up, no model): ollama absent from `nvidia-smi` compute list, ~9 W

**Not verified:** any Track B claim. ComfyUI, cu130 torch and NVFP4 are untouched.
