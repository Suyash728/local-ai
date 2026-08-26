# Build Plan — Decisions & Rationale (archival)

**Status: build complete.** This file is a historical record of *why* things were built the way
they were. For current state, use `README.md`. For full audit detail and phase-by-phase checklists,
see git history (`git log --oneline` from the first commit) — every decision below traces to a
verified commit.

---

## Starting assumptions that were wrong (worth remembering)

The original brief assumed ~230 GB free disk and an interrupted PyTorch install. Neither was true:
disk was 102 GiB free (not 230), and the existing `torch 2.13.0+cu129` venv was complete and
working on sm_120. The cached "Qwen2.5-Coder-14B" download was the **base** model in BF16
safetensors — wrong format for Ollama (needs GGUF) and wrong variant (base ≠ instruct) regardless.
Deleted rather than converted (conversion would have cost ~36 GiB of writes to a DRAM-less QLC
drive for a still-wrong model). The FLUX NVFP4 checkpoint on hand was transformer-only — no VAE,
T5, or CLIP tensors, verified by parsing the safetensors header directly rather than assuming.

**Lesson carried forward through the whole build: verify every claim about this machine's state
before acting on it. Nothing was taken on faith, including things that looked obviously true.**

---

## Key decisions

**cu130 over cu129.** NVFP4 acceleration in ComfyUI needs a cu130 torch build plus
`comfy-kitchen[cublas]`; without it an NVFP4 checkpoint loads but runs up to 2x slower than fp8 —
which would have made the already-downloaded 8.56 GiB FLUX NVFP4 file actively harmful to keep.
Same torch version (2.13.0), different CUDA build, so the swap carried no Python-API risk. Built
`comfy-venv-cu130` fresh alongside the working cu129 venv and only deleted the old one after
verifying `(12, 0)` in the new one.

**One venv, not two, for SageAttention.** No prebuilt sm_120 SageAttention wheel targets torch
2.13 on cu129 *or* cu130 — a second venv would have cost ~7 GiB and fixed nothing. SDPA
(`--use-pytorch-cross-attention`) is the default launch profile; SageAttention stays a possible
future source-build, not a blocker.

**Model store as a nested Btrfs subvolume, not just `chattr +C`.** `@home` turned out to be
snapshotted (confirmed after initial uncertainty), and Btrfs re-enables copy-on-write for the first
write to a `+C` file after every snapshot — so `+C` alone would not have stuck. A nested subvolume
is excluded from its parent's snapshots, which makes `+C` durable. Verified every downloaded blob
carries the `C` flag.

**Track C (video generation) deferred.** Swap on this machine is zram-only (compressed RAM, no
disk swap), so the real offload pool for block-swap workflows is ~23 GiB of available RAM, not the
31 GiB total — and video models commonly want 50-95 GiB for offloading at decent resolutions. PCIe
4.0 x8 is also the configuration ComfyUI's own documentation flags as gaining least from GPU
offload. Revisit if RAM goes to 64 GiB; VRAM (16 GiB) remains the harder ceiling regardless,
capping any local video model at roughly the 5B class.

**Ollama's `cuda` package dependency was accepted, not avoided.** It's a hard dependency of
`ollama-cuda`, not optional — and it also provided the `nvcc` used later to confirm SageAttention
would need a source build.

---

## Net effect on disk

Reclaimed ~43.5 GiB (orphaned HF `.incomplete` blobs, the wrong-format Qwen download, pacman/uv
caches) against ~30.5 GiB of new installs for Track A + B, ending with **more free space than the
audit started with** despite installing a full LLM + image-gen stack. Later additions (Z-Image,
klein-9B, FLUX.2-dev, gpt-oss, opencode) are accounted for in `README.md`'s current disk figure,
not here — this section reflects the original two-track build only.

---

## What's built (see README.md for detail, verification proof, and how to use each)

- **Track A** — Ollama + `gpt-oss:20b`, `qwen2.5-coder:14b-instruct`, `gemma3:12b`,
  `qwen2.5-coder:1.5b-base`, `nomic-embed-text`
- **Track B** — ComfyUI on cu130 + comfy-kitchen (NVFP4), with FLUX.1-dev, Z-Image Turbo,
  FLUX.2-klein-9B and FLUX.2-dev all installed and verified
- **Track C** — deferred by decision, not built
- **Track D** — shared model store (subvolume + `chattr +C`), systemd user services (on-demand
  only, never enabled at boot), fish environment variables mirrored into each service's
  `Environment=` lines
- **Beyond the original plan** — web search/fetch tool-calling for Ollama (`WEB-ACCESS.md`),
  agentic coding via opencode (`OPENCODE.md`), a Z-Image/klein-9B/FLUX.2-dev strengths-and-weaknesses
  comparison (`MODEL-COMPARISON.md`), photoreal-prompting notes (`PROMPTING.md`)
