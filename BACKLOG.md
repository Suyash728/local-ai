# Backlog — every proposed addition, triaged

Full inventory of everything the `ROADMAP.md` source material proposed, **listed regardless of
disk cost** so it can be triaged on merit. Sizes are measured or pulled from the Hugging Face API
on 2026-08-29, not estimated.

`ROADMAP.md` holds the recommended *order*. This file is the complete *menu*, with stable IDs
(A1, D2, …) so items can be picked off by name. Update the Status column as things land.

Status key: ⬜ not started · 🟡 in progress · ✅ done · ❌ declined

---

## A. Agentic / orchestration

| # | Item | Cost | Status | Assessment |
|---|---|---|:--:|---|
| A1 | **MCP servers** (filesystem, git, browser, code-exec) for OpenCode | ~0 GiB | ✅ | Configured, then **disabled** — 20B cannot invoke them and they cost 5,043 tok/request. See `OPENCODE.md` |
| A2 | **LocalAI** — OpenAI/Anthropic-compatible API, agents, MCP, web UI | ~2–5 GiB + a service | ✅ | Built at user request. Shares Ollama's GGUF by symlink; verified 11 s completion |
| A3 | **LocalAGI** — agent platform, Responses-API compatible | similar | ✅ | Built at user request — from source (no binaries, Docker-first). Serves :3000. Binds 0.0.0.0 |
| A4 | **CrewAI / LangGraph** multi-agent | ~1 GiB Python deps | ✅ | Both verified against local Ollama. Reliability caveat stands for real multi-agent work |
| A5 | **Vector store** — Chroma / LanceDB / Qdrant + `nomic-embed-text` | <1 GiB | ✅ | Real capability; the embedder is already installed |
| A6 | **AnythingLLM** — all-in-one UI + knowledge base | ~1–2 GiB | ✅ | Built at user request. AppImage runs; overlap with A5/A11 is now real, pick per task |
| A7 | **Playwright** browser automation | ~0.5 GiB | ✅ | Delivers the "browser use" goal; Node 24 already present |
| A8 | **faster-whisper / whisper.cpp** (STT) | ~1–3 GiB | ✅ | Works fine, but not aligned to the stated priorities |
| A9 | **Piper / Coqui-XTTS** (TTS) | ~1–2 GiB | ✅ | Same as A8 |
| A10 | **nvtop / gpustat** monitoring | ~10 MiB | 🟡 | gpustat done; **nvtop needs `sudo pacman -S nvtop`** (no passwordless sudo) |
| A11 | **OpenWebUI** chat UI | ~1–2 GiB | ✅ | There is currently no chat UI at all on this machine |

## B. Image generation

| # | Item | Cost | Status | Assessment |
|---|---|---|:--:|---|
| B1 | Keep Z-Image Turbo NVFP4 as the daily driver | — | ✅ | Already installed and verified |
| B2 | **Re-add FLUX.1-dev NVFP4** as a quality reference | ~12 GiB | ❌ | Deliberately removed; FLUX.2-dev supersedes it |
| B3 | **FLUX.2-klein-4B** (Apache-licensed) | ~15 GiB | ⬜ | Never installed. The 4B is the *trainable* one — pairs with C3 |
| B4 | **SDXL / Pony / Illustrious** + LoRA ecosystem | ~7 GiB | ⬜ | Largest free LoRA ecosystem, zero integration (SDXL is native, `checkpoints/` is empty) |
| B5 | SimpleTuner / Kohya SS as alternate trainers | ~5 GiB each | ⬜ | Only worthwhile if going SDXL-centric; ai-toolkit covers current models |

## C. LoRA training

| # | Item | Cost | Status | Assessment |
|---|---|---|:--:|---|
| C1 | **Run an actual training job** (Z-Image) | ~19 GiB BF16 | ⬜ | The one part of the existing stack **never exercised end to end** |
| C2 | Train against the base actually sampled with (Turbo vs base) | — | ✅ | Already documented in `LORA-TRAINING.md` |
| C3 | Train FLUX.2-klein-4B | ~15 GiB | ⬜ | Requires B3 first |

## D. Video

| # | Item | Cost | Status | Assessment |
|---|---|---|:--:|---|
| D1 | **Wan 2.2 TI2V 5B** (`9.31` + `6.27` umt5-fp8 + `1.31` VAE) | **16.9 GiB** | ⬜ | Sane entry point — validates the pipeline *and* measures real RAM pressure |
| D2 | **Wan 2.2 A14B fp8** — MoE, needs **both** experts (`13.31 × 2` + encoder + VAE) | **34.2 GiB** | ⬜ | The source called this "Wan 2.2 14B" as if one model; it is 2× that |
| D3 | **LTX-Video 13B distilled fp8** | 14.6 GiB | ⬜ | Lighter alternative, native audio support |
| D4 | Wan 1.3B / quantized LTX for fast iteration | ~3–8 GiB | ⬜ | Draft tier |
| D5 | VideoHelperSuite custom nodes | ~0 | ❌ | **Not needed** — ComfyUI 0.33.0 ships native Wan/LTX nodes |
| D6 | Dedicated systemd unit / launch profile for video | ~0 | ⬜ | Reasonable once video actually exists |
| D7 | Video LoRA training | very heavy | ❌ | The source itself flags this as experimental |

## E. Uncensored / unrestricted

| # | Item | Cost | Status | Assessment |
|---|---|---|:--:|---|
| E1 | **`gemma-4-12b-heretic-abliterated`** Q4_K_M | **6.87 GiB** | ✅ | Best all-rounder. ≈disk-neutral if swapping out `gemma3:12b` (7.6 GB) |
| E2 | **`Qwen3-VL-8B-Instruct-abliterated`** Q6_K | **6.26 GiB** | ✅ | Vision-capable uncensored |
| E3 | `Huihui-Qwen3.6-27B-abliterated` Q3_K | 12.57 GiB | ✅ | Done at **16k** ctx — 32k spills to CPU (19.0 tok/s); 16k is 100% GPU at 25.7 tok/s |
| E4 | Create a **64k context tag** for the chosen model, register in OpenCode | ~0 | ✅ | Same Modelfile trick as the existing agent tags (reuses layers) |
| E5 | NSFW LoRAs on SDXL/Pony | ~1–3 GiB | ⬜ | Requires B4 |
| E6 | Test refusal behaviour rather than trusting the "uncensored" label | ~0 | ✅ | A/B done: gpt-oss refused, gemma4-heretic complied. Abliteration is real |

## F. Rules & documentation

| # | Item | Status | Where |
|---|---|:--:|---|
| F1 | Goals bullet: uncensored creative use + *authorized* security work | ✅ | `ROADMAP.md` §3 |
| F2 | Rule: authorization required before any probing/scanning/attacking | ✅ | `ROADMAP.md` §5.11 |
| F3 | Rule: 18+ fine, anything involving minors strictly prohibited | ✅ | `ROADMAP.md` §5.12 |
| F4 | Rules 1–10 (VRAM discipline, NVFP4-first, measure-don't-assume, no xformers…) | ✅ | Already in `CLAUDE.md` |

---

## What actually constrains this now

**Disk no longer decides.** At 112 GiB free, the full realistic set — D2 + C1 + E1 + E2 + B4 ≈
**86 GiB** — fits with ~26 GiB to spare. Sequencing is a question of value and risk, not capacity.

Two ceilings that freeing disk did **not** move:

- **RAM: ~23 GiB usable, zram-only, no disk swap.** Still under the ≥24 GiB commonly wanted for
  comfortable T5 offload. This gates **D2** specifically — do **D1** first and measure.
- **VRAM: ~14.5 GiB usable.** Still one heavy model resident at a time, always.

**Suggested first pass if no other preference:** A1 + A10 + E1/E4 (near-zero disk, immediate
payoff), then D1 to measure RAM before committing to D2.
