# LoRA training — ai-toolkit on this machine

Installed 2026-08-27. Trainer is **[ostris/ai-toolkit](https://github.com/ostris/ai-toolkit)**,
which is the de-facto standard for Z-Image and FLUX.2 and the only one supporting both.

**Status: installed and verified to load; no training run has been done yet** — that needs a
dataset and a weights download (see the disk table below). Everything marked "measured" here was
checked on this machine; everything else is called out as unverified.

---

## Why ai-toolkit

It was the obvious pick, and one detail settled it: upstream's Linux install specifies
**torch 2.13.0 / torchvision 0.28.0 / torchaudio 2.11.0 on cu130** — byte-for-byte the combination
`CLAUDE.md` §4 already settled on for sm_120. No version negotiation, no second CUDA story.

It also supports every model family here (`zimage`, `flux2_klein_4b`, `flux2_klein_9b`, `flux2`),
has a web UI, and handles quantized + layer-offloaded training, which is what makes 16 GiB viable.

---

## What was installed, and where

```
~/AI/ai-toolkit/          upstream checkout (gitignored, like ComfyUI/)
~/AI/ai-toolkit/venv/     5.9 GiB — separate venv, on purpose
~/AI/configs/ai-toolkit/  our training configs (tracked in git)
```

**The venv is separate from `comfy-venv-cu130` deliberately.** ai-toolkit pins
`transformers==5.5.3`, `peft==0.18.1` and `huggingface_hub==1.23.0`; ComfyUI has its own versions
of all three. Sharing one venv would have put a working ComfyUI at risk to save ~6 GiB.

Upstream also ships an experimental "manager" (`run_linux.sh`) that provisions its *own* uv, Python,
torch, Node and FFmpeg inside the repo and auto-updates on every launch. It was **not** used —
this machine already has all of those, and a component that self-updates underneath a verified
CUDA setup is exactly the kind of thing §7 of `CLAUDE.md` says not to accept blindly.

### Verified after install

```
torch 2.13.0+cu130   cuda 13.0
arch_list [... sm_100, sm_120]   capability (12, 0)
```

Re-checked *after* installing all requirements to confirm no dependency quietly downgraded torch —
it did not. All four model classes import and report the expected arch strings.

---

## What can actually be trained here

This is the part the specs decide, and the answer is not "all of them".

| Model | Params | Download | Trainable on 16 GiB? |
|---|---:|---:|---|
| **Z-Image** | 6B | ~19-31 GiB | ✅ the comfortable choice |
| **FLUX.2-klein-4B** | 4B | ~15 GiB | ✅ easiest, and Apache 2.0 |
| FLUX.2-klein-9B | 9B | ~33 GiB | ⚠️ marginal — reports of OOM at 16 GiB even with offload |
| **FLUX.2-dev** | 32B | ~60 GiB+ | ❌ not feasible, don't try |

**FLUX.2-dev is out.** It already needs `comfy-aimdo` dynamic offload just to *infer* at 94% VRAM
occupancy. Training needs optimizer state and gradients on top of weights. There is no
configuration of this machine that trains a 32B model.

**klein-9B is the honest "probably not".** It fits on disk only if little else is added, and
community reports put it at the edge of OOM on 16 GiB. `configs/ai-toolkit/flux2_klein_lora.yaml`
defaults to **4B** for that reason, with the two lines to change clearly marked.

### The NVFP4 checkpoints cannot be used for training

The `~/AI/models/comfyui/*.safetensors` files are 4-bit **inference** checkpoints. Training needs
BF16 weights, which ai-toolkit pulls from HuggingFace into `HF_HOME` (`~/AI/models/hf`) on the
first run of a config. Nothing already on disk shortcuts this.

**Disk is the binding constraint** (44 GiB free after this install, `CLAUDE.md` §5). Pick one
model to start; two of them do not fit together.

---

## Configs

Two, tuned for this machine, both parsed successfully through ai-toolkit's own config loader:

| File | Model |
|---|---|
| `configs/ai-toolkit/zimage_lora.yaml` | Z-Image Turbo |
| `configs/ai-toolkit/flux2_klein_lora.yaml` | FLUX.2-klein-4B (9B by changing 2 lines) |

The 16 GiB memory profile in both:

```yaml
quantize: true                              # 8-bit transformer
quantize_te: true                           # 8-bit text encoder — matters as much
layer_offloading: true                      # stream layers from RAM
layer_offloading_transformer_percent: 0.5   # raise toward 1.0 if OOM, costs speed
layer_offloading_text_encoder_percent: 1.0
low_vram: true                              # this GPU also drives the desktop (~0.9 GiB)
```

Two behaviours worth knowing, both read out of ai-toolkit's source rather than assumed:

- Setting `layer_offloading: true` **silently rewrites `qtype` from `qfloat8` to `float8`**
  (`toolkit/config_modules.py:714`). Confirmed on our configs — they load as `qtype=float8`.
- Layer offloading spends **RAM**, and swap here is zram-only (~23 GiB usable, no disk swap).
  If training dies from host RAM rather than VRAM, lower the offload percentages rather than
  raising them.

`batch_size: 1` and `resolution: [768, 1024]` are set for headroom. Drop to `[640, 768]` before
touching anything else if you OOM.

---

## Running one

```fish
# 1. dataset: a flat folder of images + one .txt caption per image
#    (photo1.jpg + photo1.txt). 10-20 images is plenty.
mkdir -p ~/AI/datasets/my-subject

# 2. point the config at it, and set a trigger word
#    edit datasets[0].folder_path and trigger_word in the yaml

# 3. free the GPU first — ComfyUI and training cannot share 16 GiB
systemctl --user stop comfyui

# 4. train
cd ~/AI/ai-toolkit
./venv/bin/python run.py ~/AI/configs/ai-toolkit/zimage_lora.yaml
```

The first run downloads BF16 weights (see the table above) — expect a long wait before step 1.
Checkpoints and sample images land in `~/AI/ai-toolkit/output/<config name>/`.

**Web UI** (optional): `cd ~/AI/ai-toolkit/ui && npm run build_and_start` → <http://localhost:8675>.
Node 24 is already installed. Not wired to a systemd unit, and not verified here.

---

## Using the result

Trained LoRAs go in `~/AI/models/comfyui/loras/` — already wired into ComfyUI via
`extra_model_paths.yaml`, so the file appears in the `LoraLoaderModelOnly` dropdown with no config
change. Add that node between `UNETLoader` and `KSampler` in any workflow.

### Verified: LoRAs really do apply to the NVFP4 checkpoints

This gates the whole exercise — if a LoRA could not be applied to the 4-bit inference weights,
training one would be pointless. So it was tested rather than inferred from the source.

Two synthetic rank-8 LoRAs were built against the 60 attention linears of
`z_image_turbo_nvfp4.safetensors` — one with `lora_B` all zeros (delta exactly 0) and one with
random `lora_B` — then run through `LoraLoaderModelOnly` at strength 1.0, same seed and prompt:

| Check | Result |
|---|---|
| Unmatched keys (`lora key not loaded`) | **0** |
| Shape errors | **0** |
| Patches attached (log) | **60**, vs `0 patches attached` without a LoRA |
| Zero-LoRA vs non-zero-LoRA output | **differs** (mean \|Δ\| 26.8/255) |
| Baseline reproducibility | bit-identical across two runs (max \|Δ\| = 0) |

The delta reaches the quantized weights and changes the image. **LoRA on NVFP4 works.**

Two things that cost time and are worth knowing:

- **NVFP4 shapes in the file are packed two-per-byte.** A linear whose header says
  `[3840, 1920]` is logically `[3840, 3840]`. Building a LoRA against the header shape produces
  `shape '[3840, 3840]' is invalid for input of size 7372800` on every layer — and ComfyUI logs
  that as an error per layer while still reporting the job as `success`. Check the log, not the
  status.
- **A zero-delta LoRA is not a no-op on a quantized checkpoint.** It still changed the output
  against a verified-deterministic baseline, because the patch path dequantizes and re-quantizes
  each patched weight. Practical effect: adding a LoRA perturbs the base render slightly
  regardless of its contents, so "with LoRA at low strength" is not a clean A/B against "no LoRA".

**Untested caveat:** a LoRA trained against Z-Image *base* (28-50 steps, real CFG) is not
guaranteed to behave identically on *Turbo* (8 steps, cfg 1.0). Community reports say they
transfer; that has not been checked here. Training against Turbo directly, which is what
`zimage_lora.yaml` does, avoids the question entirely.
