# Local AI Stack — Roadmap & Recommendations (August 2026)

**This file is a forward-looking roadmap, not the source of truth.** `CLAUDE.md` is the operating
rules and is accurate; `README.md` is current state. Where this file and `CLAUDE.md` disagree,
`CLAUDE.md` wins. Everything below has been reconciled against the machine as measured on
2026-08-29.

**Machine**: Ryzen 5 5600 · RTX 5060 Ti 16 GB (Blackwell, sm_120, cc 12.0) · 31 GiB RAM ·
CachyOS · Btrfs · Wayland/KDE
**Model store**: `~/AI/models/` (dedicated Btrfs subvolume, `chattr +C`)
**Free disk**: **112 GiB** (user freed ~60 GiB on 2026-08-29; was 52). Still finite — state the
size of any download before proposing it, per `CLAUDE.md` §3.5.

---

## 1. Non-negotiable constraints

- **VRAM**: 16,311 MiB total. Desktop consumes ~0.9–1.0 GiB → budget against **~14.5 GiB**.
- **Architecture**: Blackwell sm_120, native NVFP4. Prefer NVFP4/FP4 checkpoints when a verified
  one exists and runs through `comfy-kitchen` + torch cu130.
- **CUDA**: torch **2.13.0+cu130**. Never cu129, never xformers (wheels stop at sm_89).
- **RAM**: 31 GiB physical, **zram-only swap (~23 GiB really usable), no disk swap.** This — not
  VRAM — is the binding constraint on video block-swap / T5 offload.
- **PCIe**: 4.0 x8. Offload gains are limited; prefer staying in VRAM.
- **Services on-demand only.** Never leave both an LLM and a diffusion model resident.
  `OLLAMA_MAX_LOADED_MODELS=1` is mandatory.

### VRAM — measured on this machine, not estimated

| Workload | Peak VRAM | Notes |
|---|---|---|
| `gpt-oss-agent-32k` | 13,615 MiB | 91.7 tok/s |
| `gpt-oss-agent-64k` (**current default**) | 14,085 MiB | 87.6 tok/s, 100% GPU |
| `gpt-oss` @ 131072 ctx | 14,821 MiB | **spills 11% to CPU**, 80.1 tok/s — not adopted |
| Z-Image Turbo NVFP4 | ~8.0 GiB | ~5 s at 832×1216 |
| FLUX.2-dev NVFP4 | 15,397 MiB (94%) | ~80 s/image via `comfy-aimdo` offload |
| Concurrent LLM + diffusion | impossible | stop one first |

---

## 2. Current stack — what is *actually* installed

### Track A — LLMs & agentic
- Ollama (CUDA), user systemd unit, on demand. Store is **~30 GB actual / ~53 GB logical** —
  tags built from the same base share blobs, so the extra `-agent-*` tags cost nothing.
- `gpt-oss:20b` + `gpt-oss-agent-64k` (**default**) and `gpt-oss-agent-32k` — primary tool-calling.
- `qwen2.5-coder:14b-instruct-q4_K_M` + `-agent-32k` — coding; unreliable tool format at Q4.
- `gemma3:12b` (~7.6 GB blob) — general/vision, no native tools. **Reclaim candidate.**
- `qwen2.5-coder:1.5b-base` (941 MB) — FIM only. Reclaim candidate.
- `nomic-embed-text` — embeddings.
- **OpenCode** → Ollama, default `gpt-oss-agent-64k`, with `~/.config/opencode/AGENTS.md` path
  discipline and `OPENCODE_DISABLE_MODELS_FETCH=1` to keep it off `api.opencode.ai`.
- **Web access**: `scripts/ollama_web.py` — Marginalia + Wikipedia + DDG Instant Answer, keyless.

### Track B — Image & LoRA
- ComfyUI 0.33.0 on `~/AI/comfy-venv-cu130/` (cu130 + comfy-kitchen + comfy-aimdo), SDPA.
- **Installed:** Z-Image Turbo NVFP4, FLUX.2-dev NVFP4 (+ `flux2-vae`, `ae`, two text encoders).
- **Not installed:** FLUX.1-dev (removed, stubs cleaned), FLUX.2-klein-9B (removed 2026-08-29),
  klein-4B (never present). `checkpoints/` is empty — no SDXL-class model.
- **LoRA training**: ostris/ai-toolkit in its own venv, configs tuned for 16 GB. LoRA application
  to NVFP4 inference weights is verified working; **no training run has been done yet.**

### Track C — Video
**Integration is already done.** ComfyUI 0.33.0 ships native Wan 2.2 and LTX support
(`comfy/ldm/wan`, `comfy/ldm/lightricks`, `Wan22ImageToVideoLatent`, `WanImageToVideo`, the full
`LTXV*` set including audio). No custom nodes needed. Track C is a **pure download problem.**

---

## 3. Goals

1. Full local agentic capability — multi-tool, memory/RAG, browser use, MCP ecosystem.
2. Image generation + custom LoRA training on the NVFP4 path.
3. Practical local video (720p, or good 480p).
4. Private uncensored/NSFW creative use and *authorized* security-research discussion — fully
   local, never crossing into actionable unauthorized-intrusion methods.
5. Everything free: no paid APIs, no mandatory cloud, no license that blocks local use.

---

## 4. Recommendations

### 4.1 Agentic
- Keep **Ollama + OpenCode** as the core. Add **MCP servers** (filesystem, git, fetch) — `opencode
  mcp` is built in, so this is the biggest agentic gain for zero disk.
- Memory/RAG: Chroma or LanceDB + the installed `nomic-embed-text`.
- Browser: Playwright, local and sandboxed.
- **Declined:** LocalAI / LocalAGI (duplicates a working OpenAI-compatible endpoint at
  `127.0.0.1:11434/v1`), CrewAI / LangGraph (multi-agent multiplies a model measured at only
  2/4–3/3 single-agent reliability), voice stack, AnythingLLM.

### 4.2 Image
Keep the ComfyUI + comfy-kitchen + cu130 NVFP4 path. Z-Image Turbo is the daily driver;
FLUX.2-dev is the quality ceiling at ~80 s. SDXL/Pony/Illustrious is the cheapest way to add a
large free LoRA ecosystem (~7 GiB, zero integration work — SDXL is natively supported).
ai-toolkit stays the trainer; train against the base actually sampled with.

### 4.3 Video
- **Wan 2.2 TI2V 5B** — `9.31 (model) + 6.27 (umt5-fp8) + 1.31 (VAE)` = **~16.9 GiB**. The sane
  entry point; validates the pipeline before any larger commitment.
- **Wan 2.2 A14B fp8** — MoE, needs **both** experts: `13.31 × 2 + 6.27 + 1.31` = **~34.2 GiB**.
  Leaves almost nothing for LoRA training weights.
- **LTX-Video 13B distilled fp8** — 14.62 GiB, lighter, native audio support.
- ⚠️ **Measure RAM before downloading.** Community guidance wants ≥24 GiB system RAM for
  comfortable T5 offload; we sit at **~23 GiB usable, zram-only**. The fp8 encoder (6.27 vs
  10.59 GiB) is the mitigation. This is the real risk, not VRAM.
- Video LoRA training: out of scope, far too heavy.

### 4.4 Supporting tools
Ollama (LLM) · ComfyUI (image/video) · OpenCode (+ Aider/Continue.dev configs staged) ·
Chroma/LanceDB · Playwright · nvtop/gpustat. No Docker/Podman (neither is installed; prefer
native + uv/venv).

### 4.5 Uncensored / unrestricted models (free, measured sizes)

Verified against the Hugging Face API, August 2026:

| Model | Quant | Size | Role |
|---|---|---:|---|
| `gemma-4-12b-heretic-abliterated` | Q4_K_M | **6.87 GiB** | best all-rounder uncensored chat/roleplay |
| `Qwen3-VL-8B-Instruct-abliterated` | Q6_K | **6.26 GiB** | vision-capable uncensored |
| `Huihui-Qwen3.6-27B-abliterated` | Q3_K | 12.57 GiB | larger; real quality trade-off at Q3 |

**Cheapest path:** swap `gemma3:12b` (~7.6 GB) → `gemma-4-12b-heretic-abliterated` (6.87 GiB) —
roughly disk-neutral. Then create a 64k context tag exactly as the existing agent tags were made
(`FROM <base>` + `PARAMETER num_ctx 65536`, reuses layers) and register it in OpenCode.

Keep `gpt-oss-agent-64k` as the tool-calling driver; switch to an uncensored model only for pure
chat/roleplay where tool use is not needed. Never trust a model's self-reported "uncensored"
claim — test it.

For images, SDXL/Pony/Illustrious + community LoRAs remain the easiest free adult ecosystem when
FLUX LoRA coverage is thin. Training stays in the separate ai-toolkit venv, same 16 GB
quantize + offload settings.

**Guardrails — non-negotiable:**
- Adult (18+) content is fine. **Anything involving minors is strictly prohibited.**
- Security work only against systems owned or with explicit written authorization. No weaponized
  payloads, no step-by-step exploit code; prefer defensive and hardening discussion.
- Uncensored models get **no extra privileges** — existing path discipline, tool guards, and
  `external_directory` restrictions stay in force.

---

## 5. Operational rules

1. **VRAM discipline.** Stop the other service before starting a heavy job.
2. **Prefer NVFP4/FP4** where a verified checkpoint exists for this stack.
3. **Measure, don't assume**: `get_device_capability()` → `(12, 0)`, real VRAM via `nvidia-smi` or
   `/system_stats`, and a real generation time or tok/s.
4. Never install xformers. Never default to SageAttention.
5. Services stay on-demand, never enabled at boot.
6. All weights under `~/AI/models/` on the nodatacow subvolume.
7. Free software only.
8. Document decisions with measured VRAM, speed, and rationale.
9. Agent safety: restrictive `external_directory`, project-relative paths, sandboxed shell.
10. Use a 32k+ context tag for any tool-using workload; 4k breaks tool lists.
11. Uncensored models are allowed for creative/NSFW work. For anything involving probing,
    scanning, or attacking a system, confirm explicit authorization first.
12. Never download or recommend models whose purpose is illegal content. 18+ fine; minors never.

---

## 6. Execution order

1. **MCP servers for OpenCode** — ≈0 disk, built-in support, biggest agentic gain per byte.
2. **Uncensored LLM** — ≈0–7 GiB via the `gemma3` swap; add the 64k tag and register in OpenCode.
3. **SDXL/Pony + NSFW LoRAs** (~7 GiB) — largest free adult LoRA ecosystem, zero integration work.
4. **Video** — start with Wan 2.2 TI2V 5B (~16.9 GiB) to validate the pipeline and, more
   importantly, to measure real RAM pressure before committing to the 14B MoE path (~34.2 GiB).
5. **Run an actual LoRA training job** (~15–31 GiB of BF16 weights) — the one part of the existing
   setup never exercised end to end.
6. **Still declined on merit, not space:** LocalAI/LocalAGI (duplicates a working endpoint),
   CrewAI/LangGraph (multi-agent on a model measured at 2/4–3/3 single-agent reliability), voice
   stack, AnythingLLM.

### Disk is no longer the deciding constraint

At 52 GiB, video and LoRA-training weights could not coexist. At **112 GiB they can**: the full
set — 14B video (34.2) + LoRA BF16 (≈31) + uncensored LLM (6.9) + uncensored VL (6.3) + SDXL (≈7)
— is ≈86 GiB. Sequence is now driven by **value and risk, not capacity**.

**The remaining hard limits are RAM and VRAM, and freeing disk did not move either:**
- ~23 GiB usable RAM, zram-only — still below the ≥24 GiB commonly wanted for T5 offload.
  Measure before the 14B video download.
- ~14.5 GiB usable VRAM — still one heavy model at a time, always.

---

## 7. Quick reference

```fish
# LLM
systemctl --user start ollama
ollama run gpt-oss-agent-64k
systemctl --user stop ollama

# Image
systemctl --user stop ollama
systemctl --user start comfyui   # http://127.0.0.1:8188
systemctl --user stop comfyui

# LoRA training
systemctl --user stop comfyui
cd ~/AI/ai-toolkit
./venv/bin/python run.py ~/AI/configs/ai-toolkit/zimage_lora.yaml

# Agentic coding
systemctl --user start ollama
cd <project> && opencode          # TUI, gpt-oss-agent-64k by default
```
