# Local AI Stack — Audit & Build Plan

**Machine:** CachyOS / Ryzen 5 5600 / RTX 5060 Ti 16G (sm_120) / 31 GiB RAM
**Audited:** 2026-08-23 · **Status:** Track A COMPLETE & VERIFIED. Track B not started. Track C deferred.
**Read `CLAUDE.md` first** for the operating rules. This file is the reasoning and the checklist.

---

# PHASE 1 — AUDIT RESULTS

## Headline corrections to my starting assumptions

| I assumed | Reality |
|---|---|
| ~230 GB free | **102 GiB free.** Total partition is 244 GiB, 141 GiB used. |
| PyTorch install was interrupted / incomplete | **Complete and fully working on sm_120.** Nothing to redo. |
| Qwen download is a usable code model | It is the **BASE** model (not Instruct), in **BF16 safetensors**, unusable by Ollama. |
| FLUX NVFP4 is ready to run | Transformer only. **No VAE, no T5, no CLIP.** Needs 5.34 GiB more. |
| — | **4.68 GiB of orphaned `.incomplete` blobs** are sitting in the HF cache doing nothing. |
| — | Swap is **zram only**. No disk swap. This kills the video-gen offload story. |

## Audit table

| # | Check | Finding | Verdict |
|---|---|---|---|
| 1 | GPU + driver | RTX 5060 Ti, driver `610.57.04`, CUDA UMD **13.3**, compute cap **12.0**, 15.52 GiB usable VRAM, PCIe Gen4 x8 (idles at Gen2 — normal power saving). ~710 MiB already used by KDE + Firefox. | ✅ |
| 2 | Driver package | `linux-cachyos-nvidia-open 7.2.0-1` matches running kernel `7.2.0-1-cachyos`. `linux-cachyos-lts-nvidia-open 6.18.42-1` also present for the LTS kernel. Module licence `Dual MIT/GPL` = genuinely the open module. | ✅ |
| 3 | Python toolchain | System Python **3.14.7** (too new for ML wheels — do not use). `uv 0.12.5` at `/usr/bin/uv`, on PATH. `mise 2026.8.6` (node v24.19.0). `shelly 3.0.6`. No system `pip`/`pipx`. | ✅ |
| 4 | `~/AI/comfy-venv` | Exists. Python **3.12.13** (uv-managed CPython). **`torch 2.13.0+cu129` fully installed and functional.** `get_arch_list()` includes `sm_120`; `get_device_capability()` → **`(12, 0)`**; live 2048² fp16 matmul on device succeeded; `float8_e4m3fn` cast OK; bf16 supported. Plus `torchvision 0.28.0+cu129`, `torchaudio 2.11.0+cu129`, `triton 3.7.1`, `numpy 2.4.4`, `pillow 12.2.0`, full `nvidia-*-cu12` set. **No `pip`** (uv venv). Size **6.9 GiB**. | ✅ works — but see §cu130 |
| 5 | `~/AI/FLUX.1-dev-NVFP4` | **8.56 GiB**, 4 files. `flux1-dev-nvfp4.safetensors` is **structurally complete** — parsed the header, declared data end == file size **exactly**. 1464 tensors: 152×U8 (packed NVFP4), 266×F8_E4M3, 514×BF16, 532×F32 scales. **But contains only the transformer** (`double_blocks`, `single_blocks`, `final_layer`, `img_in`/`txt_in`/`time_in`/`vector_in`/`guidance_in`). Zero VAE / T5 / CLIP tensors. No `.incomplete` files. | ⚠️ complete but **not runnable alone** |
| 6 | Qwen2.5-Coder-14B cache | **33 GiB total.** Format: **full BF16 safetensors**, 6 shards, 29.54 GB — all snapshot symlinks resolve, shard sizes match `model.safetensors.index.json` exactly → **the download is complete**. **However:** repo is `Qwen/Qwen2.5-Coder-14B` — the **BASE** model, *not* `-Instruct`. Plus **4.68 GiB of orphaned `.incomplete` blobs** from the first failed attempt, duplicating data that later succeeded. | ❌ wrong format **and** wrong variant |
| 7 | Docker / podman | Neither installed. No `nvidia-container-toolkit`, no `nvidia-ctk`. Nothing configured. | ⬜ absent (fine — not needed) |
| 8 | Disk | `/dev/nvme0n1p5` btrfs, **244G total / 141G used / 102G available**. Mount: `noatime,compress=zstd:1,ssd,discard=async`. `~/AI` on `@home`. RAM 31 GiB, **swap = zram 31.3 GiB only, no disk swap**. `du`: FLUX 8.6G · comfy-venv 6.9G · HF cache 33G · uv cache 7.3G · pacman cache 6.3G · `~/Videos` **52G**. | ⚠️ far tighter than assumed |
| 9 | Existing AI runtimes | ComfyUI, Ollama, llama.cpp, LM Studio, vLLM, koboldcpp — **none present.** No binaries, no packages, no data dirs (`~/.ollama` etc. all absent), no systemd user units at all (`~/.config/systemd/user/` doesn't exist). | ⬜ clean slate |

## Additional findings not on the checklist

- **`snapper` + `snap-pac` + `limine-snapper-sync` are installed and active.** `snap-pac` takes a
  snapshot on *every* pacman transaction. Whether `@home` has its own snapper config needs one sudo
  command to confirm — it materially affects both space reclamation and whether `chattr +C` sticks.
- **Network is healthy right now**: pypi.org 15 ms, pypi.nvidia.com 296 ms, huggingface.co 264 ms,
  ollama.com 1.2 s, github.com 1.6 s. All 200. The historical timeouts were transient.
- **PyTorch index today offers** cu121, cu124, cu126, cu128, **cu129, cu130, cu132**. torch `2.13.0`
  is published for cu129, cu130 *and* cu132 on cp312, each with matching torchvision 0.28.0 /
  torchaudio 2.11.0. **A cu129 → cu130 move is a pure CUDA-build swap at identical library versions.**
- **`ollama-cuda` depends on the full `cuda` package** (2.20 GiB download / 4.71 GiB installed).
- **`cmake` and `ninja` are not installed** (needed only for a SageAttention source build).
- `git 2.55.0`; global identity `Suyash728 <suyashkerkar642005@gmail.com>`; `~/AI` was not a repo.

---

# PHASE 2 — THE PLAN

## The cu129 vs cu130 decision → **cu130. Install `torch 2.13.0+cu130`.**

### Why cu130
1. **NVFP4 acceleration in ComfyUI requires a cu130 PyTorch build plus the `comfy-kitchen[cublas]`
   kernel library.** This is stated by ComfyUI's own engineering blog and by the `comfy-kitchen`
   package itself. Without cu130, an NVFP4 checkpoint still *loads*, but falls back to emulation and
   sampling can be **up to 2× slower than fp8**.
2. **That makes cu129 the actively wrong choice for you specifically.** You have already spent
   8.56 GiB on the NVFP4 checkpoint. On cu129 that file is not merely un-accelerated — it is *worse
   than an fp8 checkpoint you don't have*. The only reason to hold NVFP4 weights is the FP4 hardware
   path, and cu130 is the gate on it.
3. **The swap is low-risk.** You are on torch 2.13.0 today and the target is torch 2.13.0 — same
   version, different CUDA build, with matching torchvision/torchaudio published. No Python API
   changes, so **no pure-Python custom node can notice the difference.**
4. **The driver is not a constraint.** UMD is CUDA 13.3, newer than cu130.

### Why not cu132 (it exists)
`comfy-kitchen` and every community SageAttention wheel target **cu130**. cu132 is ahead of the
ecosystem and buys you nothing. Skip it.

### On SageAttention — and why the two-venv fallback is the wrong fix
You asked me to propose two venvs if cu130 endangers SageAttention. **It doesn't, and two venvs
wouldn't help.** Here's the honest state:

- SageAttention is a compiled CUDA extension linked against an exact PyTorch C++ ABI. Community
  sm_120 wheels are pinned to exact torch builds. The ones I found target **torch 2.11**
  (cu128 and cu130 variants). One source claims 2.2.0.post6 works on cu130 + torch 2.13 —
  **I could not verify that**, so treat it as unconfirmed.
- **You are on torch 2.13.0.** No prebuilt sm_120 SageAttention wheel I found targets it.
  So SageAttention is a build-from-source job on **cu129 and cu130 alike**. cu130 doesn't degrade
  the situation, and a second cu129 venv would *also* have no matching wheel — it would cost ~7 GiB
  and solve nothing.
- **Therefore: one venv, cu130.** Default launch profile is SDPA
  (`--use-pytorch-cross-attention`) — fast, always works, zero build risk. SageAttention becomes an
  optional experiment later; `nvcc` arrives free with the `cuda` package from Track A, and you'd add
  `cmake`+`ninja` (~90 MiB) at that point.

*(I will revisit this the moment a prebuilt sm_120 wheel for torch 2.13 + cu130 turns up.)*

### Safety measure
Build **`comfy-venv-cu130` fresh alongside** the working `comfy-venv`, verify `(12, 0)` in it, and
only then delete the old one. Given your history of network timeouts, never destroy a working
PyTorch install before its replacement is proven. Transient cost: ~7 GiB. You have room.

---

## Disk budget — **the plan is net-negative on disk**

### Reclaim first (before installing anything)

| What | Size | Risk |
|---|---:|---|
| Orphaned `.incomplete` blobs in HF cache | **4.68 GiB** | **Zero.** Pure garbage — the retries already succeeded. |
| Qwen2.5-Coder-14B BF16 safetensors | **27.52 GiB** | Low — see "the honest Qwen answer" below. |
| pacman package cache (`paccache -rk1`) | ~4 GiB | Zero — keeps 1 version of each package. |
| uv cache (`uv cache prune`, **after** the cu130 build) | ~7.3 GiB | Zero — it's a cache. |
| **Total reclaimed** | **≈ 43.5 GiB** | |

### Then spend

| Track | Item | Method | Size | Verified? |
|---|---|---|---:|---|
| A | `ollama` | `pacman -S` | 0.07 GiB | ✅ `pacman -Si` |
| A | `ollama-cuda` | `pacman -S` | 0.99 GiB | ✅ `pacman -Si` |
| A | `cuda` (hard dep of ollama-cuda) | pulled in | 4.71 GiB | ✅ `pacman -Si` |
| A | `qwen2.5-coder:14b-instruct-q4_K_M` | `ollama pull` | 8.37 GiB | ✅ registry manifest |
| A | `qwen2.5-coder:1.5b-base` (tab autocomplete) | `ollama pull` | 0.92 GiB | ✅ registry manifest |
| A | `gemma3:12b` (general purpose) | `ollama pull` | 7.59 GiB | ✅ registry manifest |
| A | `nomic-embed-text` *(optional, for RAG)* | `ollama pull` | 0.26 GiB | ✅ registry manifest |
| B | torch 2.13.0+cu130 stack (net over existing cu129) | `uv pip` | ~0.5 GiB | ⚠️ est. (6.1 GiB replaces 6.1 GiB) |
| B | ComfyUI repo | `git clone` | ~0.15 GiB | ⚠️ estimate |
| B | ComfyUI Python deps (non-torch) | `uv pip` | ~1.5 GiB | ⚠️ estimate |
| B | `comfy-kitchen[cublas]` (NVFP4 kernels) | `uv pip` | 0.06 GiB | ✅ PyPI (cp312-abi3, 55.8 MiB) |
| B | `ComfyUI-GGUF` custom node + `gguf` | `git clone` + `uv pip` | <0.01 GiB | ⚠️ estimate |
| B | `t5xxl_fp8_e4m3fn_scaled.safetensors` | `hf download` | 4.80 GiB | ✅ HF API |
| B | `clip_l.safetensors` | `hf download` | 0.23 GiB | ✅ HF API |
| B | `ae.safetensors` (FLUX VAE) | `hf download` | 0.31 GiB | ✅ HF API |
| | **Total new spend** | | **≈ 30.5 GiB** | |

### Net result

```
  102 GiB free now
+  43.5 GiB reclaimed
-  30.5 GiB spent
= ~115 GiB free after the full build
```

**The plan ends with ~13 GiB more free space than you have today, and never exceeds the 100 GiB
threshold you asked me to flag.** Peak transient dip is during the cu130 build (two venvs + unpruned
uv cache): worst case ≈ 96 GiB free. Comfortable.

If you'd rather keep the Qwen BF16 weights, the plan still only costs ~+3 GiB net (≈ 87 GiB free).
It is not a forced deletion.

---

## Track A — Text & code LLMs

### The honest answer on your existing Qwen download

**You cannot use it, and I'd delete it. Two independent reasons, either one fatal:**

1. **Wrong format.** Ollama consumes GGUF. You have BF16 `safetensors`. There is no way around this
   short of converting.
2. **Wrong variant — and this is the one that actually settles it.** The cached repo is
   `Qwen/Qwen2.5-Coder-14B`, the **base** model. Not `-Instruct`. Base models do raw text
   continuation; they do not follow chat instructions. Continue.dev chat, Zed's assistant and Aider
   all need the **Instruct** model. Converting the base weights would cost you hours and ~36 GiB of
   peak disk to arrive at a model that still can't do the job you want.

**Could you convert instead of re-downloading?** Yes, technically: clone llama.cpp, run
`convert_hf_to_gguf.py` (~29 GiB F16 intermediate), then quantize to Q4_K_M (~8.4 GiB). That saves
an 8.37 GiB download but costs **~36 GiB of peak disk and ~36 GiB of writes to a DRAM-less QLC
drive** — precisely the write-thrashing your constraints say to avoid — and still lands you on the
base model. **Not worth it.** Delete the 33 GiB, pull 8.37 GiB, come out 24 GiB ahead.

*(Base models are genuinely good at fill-in-the-middle autocomplete — but a 14B is far too slow for
tab-completion latency anyway. The 0.92 GiB `1.5b-base` below is the right tool for that.)*

### What to install

| Item | Why |
|---|---|
| `ollama` + `ollama-cuda` (pacman) | Primary runtime. GGUF, OpenAI-compatible endpoint at `localhost:11434/v1`. |
| `qwen2.5-coder:14b-instruct-q4_K_M` | Code chat / edit / agent work. |
| `qwen2.5-coder:1.5b-base` | Tab-autocomplete in Continue.dev. Base variant is correct here (FIM), and small = low latency. |
| `gemma3:12b` | General-purpose 12B-class. Chosen over `mistral-nemo:12b` (6.96 GiB): newer, stronger, 128k context, and vision-capable. |

**On the `cuda` dependency** (constraint #5 says justify it): it is a **hard dependency** of
`ollama-cuda` — not optional. It's justified because (a) there's no alternative short of the
unmanaged upstream install script dumping duplicate CUDA libs into `/usr/local`, (b) pacman keeps it
in lockstep with your driver on a rolling distro, and (c) it provides the `nvcc` you'd need for a
SageAttention build in Track B. 4.71 GiB against ~115 GiB free is a good trade.

### VRAM math (against ~14.8 GiB usable, desktop running)

Qwen2.5-Coder-14B: 48 layers, 8 KV heads, head_dim 128 → **192 KiB of KV cache per token**.

| Config | Weights | KV cache | Total | Verdict |
|---|---:|---:|---:|---|
| 32k ctx, fp16 KV | 8.37 | 6.00 | **14.37** | ✗ no headroom |
| 16k ctx, fp16 KV | 8.37 | 3.00 | **11.37** | ✓ fine |
| **16k ctx, q8_0 KV** | 8.37 | 1.50 | **9.87** | ✓✓ **recommended** |
| 32k ctx, q8_0 KV | 8.37 | 3.00 | 11.37 | ✓ if you need long context |

So set `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0`, and `num_ctx 16384`.
`gemma3:12b` (7.59 GiB) has similar headroom. The two 8-ish GiB models **cannot both stay resident**
(16 GiB > 14.8) — Ollama will evict one; set `OLLAMA_MAX_LOADED_MODELS=1` to make that deterministic.

### Editor wiring (all point at the same endpoint)

- **Continue.dev** — `~/.continue/config.yaml`, provider `ollama`, `apiBase http://localhost:11434`.
  14B-instruct for chat/edit, 1.5b-base for `tabAutocompleteModel`.
- **Zed** — `settings.json` → `language_models.ollama.api_url = "http://localhost:11434"`.
- **Aider** — `aider --model ollama_chat/qwen2.5-coder:14b-instruct-q4_K_M`
  with `OLLAMA_API_BASE=http://127.0.0.1:11434`.

---

## Track B — Image generation (ComfyUI)

### Steps
1. `uv venv ~/AI/comfy-venv-cu130 --python 3.12` (fresh, alongside the working one).
2. `env UV_HTTP_TIMEOUT=300 uv pip install --index-url https://download.pytorch.org/whl/cu130 torch==2.13.0 torchvision==0.28.0 torchaudio==2.11.0`
3. **GATE:** verify `get_device_capability() == (12, 0)`, `sm_120` in `get_arch_list()`, and a live
   fp16 matmul. Only past this gate does anything else get installed.
4. `git clone https://github.com/comfyanonymous/ComfyUI ~/AI/ComfyUI`, then
   `uv pip install -r requirements.txt` **without** letting it touch torch (pin/`--no-deps` the torch line).
5. `uv pip install 'comfy-kitchen[cublas]'` — the NVFP4 kernel library.
6. `git clone https://github.com/city96/ComfyUI-GGUF` into `custom_nodes/`, `uv pip install gguf`.
7. Move `flux1-dev-nvfp4.safetensors` into `~/AI/models/comfyui/diffusion_models/`.
8. Download the three missing pieces (see below).
9. Write `extra_model_paths.yaml` pointing at `~/AI/models/comfyui/`.
10. **Do not install xformers.** SDPA is the default and correct path here.

### The missing FLUX pieces — your NVFP4 file is a transformer, nothing else

I parsed the safetensors header: 1464 tensors, all of them transformer blocks. **Zero** VAE, T5 or
CLIP tensors. FLUX needs all four components. You must add:

| File | From | Size |
|---|---|---:|
| `t5xxl_fp8_e4m3fn_scaled.safetensors` | `comfyanonymous/flux_text_encoders` | 4.80 GiB |
| `clip_l.safetensors` | `comfyanonymous/flux_text_encoders` | 0.23 GiB |
| `ae.safetensors` | `black-forest-labs/FLUX.1-schnell` (ungated; identical VAE to dev) | 0.31 GiB |

**Take fp8 T5, not fp16** (9.12 GiB). It saves 4.3 GiB, and with an FP4 transformer on a 16 GiB card
an fp16 text encoder is the wrong place to spend VRAM. The `_scaled` variant is the better-quality
fp8 build.

### Launch profiles (both go in `~/AI/README.md` during BUILD)

| Profile | Flags | When |
|---|---|---|
| **Default / fallback** | `--use-pytorch-cross-attention` | Always works. Start here, stay here. |
| NVFP4 | default attention + `comfy-kitchen` present | After verifying cu130. Expect ~2× over fp8. |
| Low VRAM | `--lowvram` | If a workflow OOMs. |
| SageAttention | `--use-sage-attention` | **Only** if a source build succeeds. Never the default. |

⚠️ ComfyUI's async offload/pinned-memory gains scale with PCIe bandwidth, and ComfyUI's own blog
reports **PCIe 4.0 x8 — exactly your link — shows "less impressive results"** than 4.0 x16. Keep
models resident in VRAM where you can; offloading is comparatively expensive on this board.

---

## Track C — Video generation → **DEFER. Don't set it up.**

You were right, and the audit gives a sharper reason than "you need 64 GB":

1. **Your swap is zram, not disk.** 31.3 GiB of *compressed RAM*, no disk swap at all. Model weights
   are near-incompressible, so zram gives roughly 1:1 and burns CPU doing it. Your real offload pool
   is the **~23 GiB of available RAM**, not 62 GiB. Block-swap workflows that assume a large host
   memory pool will hit the OOM killer, not a slow path.
2. **PCIe 4.0 x8.** Block-swap streams weights across the bus every step. This is the exact
   configuration ComfyUI singles out as benefiting least from offload.
3. **The models don't fit.** Wan 2.2 14B wants 24 GiB+ VRAM for decent 480p/720p; LTX-2 (22B) is
   quoted at a 32 GiB VRAM baseline. You have 14.8 GiB usable.
4. **Disk.** A Wan 2.2 14B GGUF + encoders + VAE is ~20–30 GiB — a quarter of your free space for
   something that will be painful.

*(Points 3–4 are from current community/vendor reporting, not measured on your machine.)*

**What would change the answer**, cheapest first:
- **64 GiB DDR4** (2×32 GB, replacing the kit — B550M AORUS ELITE AX has 4 slots but mixing kits on
  Zen 3 at 3200 is unreliable; buy a matched 2×32). This is the real unlock for block-swap.
- **A second NVMe** purely for weights — removes the storage constraint and stops competing with Windows.
- VRAM is the hard ceiling. 16 GiB caps you at ~5B video models regardless of RAM.

**If you want to dip a toe anyway:** Wan 2.2 **5B** is the only sane entry point (fits ~8 GiB VRAM),
~6–8 GiB download. Optional, not in the budget above.

---

## Track D — Shared infrastructure

### One model store, on its own subvolume

```
~/AI/models/          ← btrfs subvolume, chattr +C, isolated from @home snapshots
├── hf/               ← HF_HOME
├── ollama/           ← OLLAMA_MODELS
└── comfyui/{diffusion_models,text_encoders,vae,loras,clip_vision}
```

**Why a subvolume rather than just `chattr +C`:** you have `snap-pac` taking a snapshot on every
pacman transaction. Btrfs re-enables CoW for the first write to a `+C` file after a snapshot, so `+C`
alone is **not durable** on a snapshotted subvolume. A nested subvolume is excluded from its parent's
snapshots (btrfs snapshots are not recursive) — which isolates the model store *and* makes `+C` stick.

Order matters: **create subvolume → `chattr +C` → only then populate.** `+C` never applies
retroactively. Moving `FLUX.1-dev-NVFP4` across the subvolume boundary is a real 8.56 GiB copy rather
than a rename — that copy is precisely what applies `+C` to the file, so it's worth doing once.

**RESOLVED 2026-08-23:** `snapper list-configs` lists only `root -> /`, but `@home` **is** being
snapshotted by another mechanism (btrfs-assistant / manual). So the nested subvolume is
**load-bearing, not optional** — without it the weights would sit in a snapshotted subvolume where
`+C` silently stops applying after each snapshot. Verified: every ollama blob carries the `C` flag.

### Environment (fish — persistent universal variables)

```fish
set -Ux HF_HOME        /home/suyash/AI/models/hf
set -Ux OLLAMA_MODELS  /home/suyash/AI/models/ollama
set -Ux OLLAMA_FLASH_ATTENTION 1
set -Ux OLLAMA_KV_CACHE_TYPE   q8_0
set -Ux OLLAMA_MAX_LOADED_MODELS 1
```

### systemd **user** services — on demand, never at boot

`~/.config/systemd/user/ollama.service`:
```ini
[Unit]
Description=Ollama (user)
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/ollama serve
Environment=OLLAMA_MODELS=/home/suyash/AI/models/ollama
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KV_CACHE_TYPE=q8_0
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_HOST=127.0.0.1:11434
Restart=on-failure

[Install]
WantedBy=default.target
```

`~/.config/systemd/user/comfyui.service`:
```ini
[Unit]
Description=ComfyUI (user)
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/home/suyash/AI/ComfyUI
ExecStart=/home/suyash/AI/comfy-venv-cu130/bin/python main.py --listen 127.0.0.1 --port 8188 --use-pytorch-cross-attention
Environment=HF_HOME=/home/suyash/AI/models/hf
Restart=on-failure

[Install]
WantedBy=default.target
```

**`systemctl --user start …` only. Never `enable`.** Confirmed `Linger=no`, so nothing survives
logout — which is what you want for idle GPU draw. Also `sudo systemctl mask ollama.service` to make
sure the *system* unit shipped by the pacman package can never start alongside the user one.

⚠️ systemd does not read fish variables — that's why every var is repeated as `Environment=`.
If you change a value, change it in **both** places.

---

# PHASE 3 — BUILD CHECKLIST (awaiting your go-ahead)

Track A first (fastest win), then B. Stop and report on any failure.

**0 — Reclaim & prepare**
- [x] `sudo snapper list-configs` — check whether `@home` is snapshotted
- [x] `find ~/.cache/huggingface/hub -name '*.incomplete' -delete` → +4.68 GiB
- [x] Confirm deletion of Qwen BF16 cache → +27.52 GiB
- [~] `sudo paccache -rk1` → ~+4 GiB  *(skipped: not needed, ended at 115 GiB free)*
- [x] Create `~/AI/models` subvolume, `chattr +C`, create subdirs
- [x] Set fish universal variables

**A — Ollama**
- [x] `sudo pacman -S ollama ollama-cuda`
- [x] write + start the user unit  *(mask skipped: system unit already `disabled`+`inactive`)*
- [x] `ollama pull` × 3 (+ optional embed model)
- [x] ✅ **PROOF:** a real streamed completion from `qwen2.5-coder:14b`, `nvidia-smi` showing it resident
- [x] Write Continue.dev / Zed / Aider config snippets

**B — ComfyUI**
- [ ] `uv venv ~/AI/comfy-venv-cu130 --python 3.12`
- [ ] Install torch 2.13.0+cu130 stack
- [ ] ✅ **GATE:** `get_device_capability() == (12, 0)` + `sm_120` in arch list + live matmul
- [ ] Clone ComfyUI, install deps without disturbing torch
- [ ] `comfy-kitchen[cublas]`, `ComfyUI-GGUF`, `gguf`
- [ ] Move FLUX NVFP4 into the model store; download t5 fp8 + clip_l + ae
- [ ] Write `extra_model_paths.yaml`; write + start the user unit
- [ ] ✅ **PROOF:** server starts, a FLUX NVFP4 image actually renders
- [ ] Delete old `comfy-venv` (+6.9 GiB), `uv cache prune` (+~7 GiB)

**C — Video:** deferred by decision. Revisit at 64 GiB RAM.

**D — Docs**
- [x] Write `~/AI/README.md`: what's installed, where models live, how to start each service,
      fallback launch profiles
- [ ] Commit
