# Local AI Stack — `~/AI`

What is installed, where things live, and how to start them.
**Rules for Claude Code sessions:** `CLAUDE.md`. **Full plan & reasoning:** `PLAN.md`.
**Getting photoreal people out of FLUX:** `PROMPTING.md`.

| | |
|---|---|
| Machine | Ryzen 5 5600 · RTX 5060 Ti 16G (sm_120) · 31 GiB RAM · CachyOS |
| Track A — LLMs | ✅ **DONE & VERIFIED** (2026-08-23) |
| Track B — ComfyUI | ✅ **DONE & VERIFIED** (2026-08-24) |
| Track C — Video | ⛔ deferred by decision (needs 64 GiB RAM) |
| Free disk | ~103 GiB |

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

## Quick start — ComfyUI

```fish
systemctl --user stop ollama          # free VRAM first: FLUX needs ~12.3 GiB
systemctl --user start comfyui        # then open http://127.0.0.1:8188
systemctl --user stop comfyui         # releases VRAM
```

> Same rule as Ollama: **not enabled at boot, down after every reboot/logout.** By design.

| Command | What it does |
|---|---|
| `systemctl --user start\|stop\|restart comfyui` | control the server |
| `journalctl --user -u comfyui -f` | live log |
| `curl -s localhost:8188/system_stats` | version + live VRAM |

**Ollama and ComfyUI cannot both hold a model.** 9.9 GiB (Qwen 14B) + 12.3 GiB (FLUX) far exceeds
15.5 GiB. Stop one before starting the other.

---

## Installed — Track B

### Environment
`~/AI/comfy-venv-cu130/` — uv-managed Python 3.12.13, **torch 2.13.0+cu130** / torchvision
0.28.0+cu130 / torchaudio 2.11.0+cu130, triton 3.7.1.
The old cu129 venv has been deleted; this is the only one.

`~/AI/ComfyUI/` — ComfyUI 0.33.0 (`b78cec8`), custom node `ComfyUI-GGUF` (city96, 6 nodes),
`comfy-kitchen 0.2.31` + `comfy-aimdo 0.4.13`.

### Models (14.2 GiB, in `~/AI/models/comfyui/`)

| File | Size | Where |
|---|---:|---|
| `diffusion_models/flux1-dev-nvfp4.safetensors` | 8.56 GiB | transformer only — 1464 tensors |
| `text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` | 4.80 GiB | 389 tensors, mixed F32/F16/F8_E4M3 |
| `text_encoders/clip_l.safetensors` | 0.23 GiB | 196 tensors, F16 |
| `vae/ae.safetensors` | 0.31 GiB | 244 tensors, F32 |

The NVFP4 file is **the transformer alone** — verified by parsing its header: zero VAE, T5 or CLIP
tensors. The other three are not optional.

### Launch profiles

| Profile | How | When |
|---|---|---|
| **SDPA (default)** | already in the unit: `--use-pytorch-cross-attention` | Always works. Stay here. |
| Low VRAM | add `--lowvram` | If a workflow OOMs |
| SageAttention | `--use-sage-attention` | **Only after a successful source build.** No prebuilt sm_120 wheel targets torch 2.13. `nvcc` is at `/opt/cuda/bin/nvcc`; you would also need `cmake` + `ninja` (~90 MiB, not installed). Never the default. |

**NVFP4 acceleration is independent of the attention backend** — it comes from the cu130 torch build
plus `comfy-kitchen`. `--use-pytorch-cross-attention` does not disable it.

**Never install xformers.** PyPI wheels stop at sm_89 and it silently downgrades torch.


### Z-Image Turbo (NVFP4) — added 2026-08-24

A 6B Lumina2/NextDiT model distilled for **8-step** sampling. Comfy-Org ships a native NVFP4 build,
so it uses the same FP4 tensor cores as FLUX.

| File | Size |
|---|---:|
| `diffusion_models/z_image_turbo_nvfp4.safetensors` | 4.20 GiB |
| `text_encoders/qwen_3_4b_fp4_mixed.safetensors` (Qwen3-4B) | 3.24 GiB |
| VAE | **reuses `vae/ae.safetensors`** — see below |

**Its VAE is byte-identical to FLUX's** (verified by sha256). Z-Image reuses the FLUX autoencoder,
so there is only one `ae.safetensors` on disk and both models point at it. Note the download ships
it under the same filename — if you ever re-download it, do **not** let it overwrite blindly; confirm
the checksum first.

**Loading it:** use `CLIPLoader` with type **`stable_diffusion`**, not a z-image entry — there isn't
one. ComfyUI detects `TEModel.QWEN3_4B` from the encoder weights and routes to `z_image.te` for any
clip_type that is not flux/flux2. Picking `flux2` would silently load it as a Klein encoder instead.

#### Measured, 832x1216, warm

| Config | Time | Note |
|---|---:|---|
| 8 steps, cfg 1.0, euler | **4.99 s** | the default to use |
| 12 steps, cfg 1.0, euler | 7.24 s | marginal quality gain |
| 8 steps, cfg 1.5, res_multistep | 9.35 s | **2x cost** — cfg > 1.0 needs cond *and* uncond passes |

Peak VRAM **8.0 GiB** (vs FLUX's 12.3).

#### Z-Image vs FLUX.1-dev on this machine

| | FLUX.1-dev NVFP4 | Z-Image Turbo NVFP4 |
|---|---|---|
| Transformer | 8.56 GiB | **4.20 GiB** |
| Text encoder | T5-XXL fp8, 4.80 GiB | Qwen3-4B fp4, **3.24 GiB** |
| Steps | 20-25 | **8** |
| 832x1216 warm | 24.0 s (25 steps) | **4.99 s** |
| Peak VRAM | 12.3 GiB | **8.0 GiB** |

**~4.8x faster at the same resolution, 4.3 GiB less VRAM.** On the flash-snapshot prompt from
`PROMPTING.md` it also produced *more* convincing results than FLUX — harder flash shadow, better
skin micro-texture. FLUX still has the larger LoRA/ControlNet ecosystem.

### Prompting
See **`PROMPTING.md`** — tested recipes for photorealistic people, the word
blacklist, guidance/step settings, and the known failure modes (hands, mirror geometry,
NVFP4's cost on fine detail).

### Measured on this machine — 2026-08-24

FLUX.1-dev NVFP4, 1024x1024, 20 steps, euler/simple, guidance 3.5:

| | |
|---|---|
| Cold (incl. model load) | **25.3 s** |
| Warm | **17.1 s** (~1.17 it/s) |
| Peak VRAM | **12.3 GiB** of 15.5 |

Raw kernel A/B, 4096^3 GEMM: **bf16 3.25 ms vs nvfp4 0.49 ms = 6.68x**. End-to-end sampling gains
are much smaller — attention, norms, VAE and text encoding are not FP4.

ComfyUI log confirms the path is live:
```
Found quantization metadata version 1
Detected mixed precision quantization
Native ops: convrot_w4a4, float8_e4m3fn, int8_tensorwise, mxfp8, float8_e5m2, asym_w4a8_int8, nvfp4
```

---

## Gotchas learned the hard way

**ComfyUI's `requirements.txt` will clobber your torch.** It lists bare `torch`, `torchvision`,
`torchaudio`, which resolve from PyPI and overwrite the cu130 build. Install from the filtered
`.comfy-reqs-notorch.txt` (keeps `torchsde`, which is a different package), and **verify
`torch.__version__` still ends in `+cu130` afterwards.**

**HF's Xet downloader can deadlock.** It wedged at 2.07/5.15 GiB — 0 bytes for 75 s, process in
`futex_wait` with 18 idle ESTABLISHED sockets. Fix: `HF_HUB_DISABLE_XET=1` and
`HF_HUB_DOWNLOAD_TIMEOUT=60`. The Xet and plain paths use different partial-file names and cannot
resume each other, so a switch costs the partial.

**`du` lies about the uv cache on Btrfs.** uv writes reflink copies, so cache and venv share
extents. `uv cache clean` reported removing 12.9 GiB but `df` gained only 5.4 GiB. Judge reclaim by
`df`, never `du`.

**Don't `pkill -f` a string that appears in your own command line** — it matches the killing shell.

### HF authentication
Token stored at `~/AI/models/hf/token` (perms 0600, inside the gitignored `models/` subvolume).
`hf auth whoami` → `NotSoPro`. Read-only scope + `canReadGatedRepos`, so gated repos such as
`black-forest-labs/FLUX.1-dev` are reachable directly.

---

## Verification record — 2026-08-23

- `library=CUDA compute=12.0 name=CUDA0 ... libdirs=ollama,cuda_v13 driver=13.3` → sm_120 on the CUDA 13 backend
- Streamed completion from `qwen2.5-coder:14b-instruct-q4_K_M`: 99 tokens, 44.0 tok/s, `done_reason: stop`
- `ollama ps` → `100% GPU`, context 16384; `nvidia-smi` → llama-server at 10062 MiB
- All 4 models generate/embed correctly; 0 pull failures
- Idle (server up, no model): ollama absent from `nvidia-smi` compute list, ~9 W

### Track B — 2026-08-24
- `torch 2.13.0+cu130`, `torch.version.cuda 13.0`, `sm_120` in arch list, `get_device_capability() == (12, 0)`
- live fp16 4096^2 matmul, bf16 matmul, fp8_e4m3fn cast — all executed on device
- `comfy_kitchen` **cuda** backend reports `quantize_nvfp4` / `scaled_mm_nvfp4`; both executed on device
- ComfyUI reached `To see the GUI go to: http://127.0.0.1:8188`
- **A real FLUX NVFP4 image rendered**: `ComfyUI/output/flux_nvfp4_verify_00001_.png`,
  1024x1024, std 47.7, 232,966 unique colours — inspected, coherent subject matter
- torch re-verified as `+cu130` after every dependency install

**Still not done:** Track C (video) remains deferred. SageAttention is not built.
