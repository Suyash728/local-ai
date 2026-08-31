# CLAUDE.md — Local AI Stack (`~/AI`)

Rules for Claude Code sessions in this directory. **Build is complete** — `README.md` is the
current state, `PLAN.md` is the archived rationale. This file is the rules only.

---

## 1. Machine facts (verified on this machine, not assumed)

| | |
|---|---|
| CPU | AMD Ryzen 5 5600 — 6C/12T, Zen 3, no iGPU |
| GPU | RTX 5060 Ti 16G — Blackwell GB206, **sm_120**, 15.52 GiB usable, HW NVFP4 |
| Driver | `nvidia-open` 610.57.04, CUDA UMD **13.3** |
| PCIe | Gen4 x8 (board caps at Gen4 — correct, not a fault) |
| RAM | 31 GiB DDR4 + **zram-only swap. There is NO disk swap** (~23 GiB really usable) |
| OS | CachyOS rolling, kernel 7.2.0-1-cachyos, KDE Plasma / Wayland |
| Root FS | Btrfs on `/dev/nvme0n1p5`, `noatime,compress=zstd:1,ssd,discard=async` |
| Snapshots | `snapper` + `snap-pac` + `limine-snapper-sync` active |

**Desktop consumes ~0.9 GiB VRAM.** Budget against **~14.5 GiB**, not 16.
**Only one GPU workload at a time** — stop ComfyUI before training, and vice versa.

---

## 2. Shell — get this right

Login shell is **fish**. Commands you hand the user must be fish-valid.

| Don't (bash) | Do (fish) |
|---|---|
| `export VAR=x` | `set -gx VAR x` / `set -Ux VAR x` (persistent) |
| `cmd <<EOF … EOF` | write the file with the Write tool, or `bash -c '…'` |
| `$(cmd)` | `(cmd)` |
| `for f in *; do …; done` | `for f in *; …; end` |
| `VAR=x cmd` | `env VAR=x cmd` |

The harness's own Bash tool is **not** fish — heredocs work fine *for you*. These rules apply to
commands you print for the user.

---

## 3. Hard rules

1. **Never install `python-pytorch` / `python-torchvision` from Arch repos.** They break on every
   Python bump. PyTorch comes from `download.pytorch.org` wheels into a uv venv. Always.
2. **Never install `xformers`.** PyPI wheels top out at sm_89 and it silently downgrades torch.
   SDPA (`--use-pytorch-cross-attention`) is the supported fast path here.
3. **Never use system Python (3.14.x) for ML.** Use a uv-managed 3.12 venv.
4. **PyTorch must be cu130.** See §4. cu126 and older give
   `no kernel image is available for execution on the device` on sm_120.
5. **Storage is a real constraint.** ~55 GiB free on a drive shared with Windows 11.
   State the size of any download *before* proposing it, and keep a running total.
6. **Do not enable services at boot.** systemd **user** units, started on demand.
7. **Verify, don't assume.** VRAM figures, quant sizes and sm_120 support change monthly.
   If you state something you did not check on this machine, say so explicitly.

---

## 4. Pinned versions (settled — don't relitigate without new evidence)

**torch 2.13.0+cu130 / torchvision 0.28.0+cu130 / torchaudio 2.11.0+cu130**, cp312.

NVFP4 acceleration needs a cu130 build *plus* `comfy-kitchen`; without it NVFP4 falls back to
emulation and runs slower than fp8. Driver UMD 13.3 is newer than cu130, so no constraint. Not
cu132 — ahead of the ecosystem, no upside. ai-toolkit upstream pins the same three versions, so
both venvs agree.

---

## 5. Layout

```
~/AI/
├── CLAUDE.md PLAN.md README.md      rules / rationale / current state
├── IMG2IMG.md LORA-TRAINING.md      topic docs — see README.md for the full index
├── comfy-venv-cu130/                ComfyUI venv
├── ComfyUI/                         upstream checkout (gitignored)
├── ai-toolkit/                      LoRA trainer + its own venv/ (gitignored)
├── configs/                         TRACKED: ai-toolkit/, comfyui-workflows/, *.service
├── scripts/                         ollama_web.py, deep_research.py, memory.py
├── docs/samples/                    images referenced by the docs
└── models/                          ← Btrfs subvolume, chattr +C, snapshot-isolated
    ├── hf/ (HF_HOME)  ollama/ (OLLAMA_MODELS)
    └── comfyui/{diffusion_models,text_encoders,vae,loras,clip_vision}
```

**Every weight goes under `~/AI/models/`. Nothing downloads twice.**

**Two venvs, deliberately.** ai-toolkit pins `transformers`/`peft`/`huggingface_hub` versions that
ComfyUI also owns. Do not merge them to save disk.

**Why a subvolume, not just `chattr +C`:** Btrfs re-enables CoW for the first write after each
snapshot, and `snap-pac` snapshots on every pacman transaction, so `+C` alone would not stick. A
nested subvolume is excluded from its parent's snapshots. `+C` must be set on the directory
**before** files land in it.

---

## 6. Network

- Always `env UV_HTTP_TIMEOUT=300 uv pip install …` (`pypi.nvidia.com` has timed out before).
- If index resolution fights: `--index-strategy unsafe-best-match`.
- Multi-GB weights: `hf download`, never plain `curl`.
- `ollama pull` **is** resumable across invocations; `hf download` is **not**.
- **Never destroy a working install before its replacement is verified.**

---

## 7. Gotchas

- The uv venv has **no `pip`**. Use `uv pip …`.
- **ComfyUI reports `success` even when it logged per-layer errors.** A job can "succeed" and
  produce a corrupt or unpatched result. Check `journalctl --user -u comfyui`, not the status.
- **NVFP4 safetensors shapes are packed two-per-byte.** A header saying `[3840, 1920]` is
  logically `[3840, 3840]`. Building LoRAs against the header shape fails on every layer.
- `ollama-cuda` depends on the full `cuda` package (4.71 GiB installed). Justified: hard
  dependency, pacman-managed, provides `nvcc`.
- HF hub leaves orphaned `*.incomplete` blobs after an interrupted download and does **not** clean
  them up. Check `find ~/AI/models/hf -name '*.incomplete'` after any failed pull.
- systemd user services do **not** inherit fish variables — repeat them as `Environment=` lines.
  Linger is off, so user services stop at logout. That is intended.
- `cmake`/`ninja` are not installed (needed only for a SageAttention source build).

---

## 8. Verification gates

Never report work as done without showing proof.

- **Torch:** `get_device_capability()` == `(12, 0)`, `sm_120` in `get_arch_list()`, and a real
  matmul on device. Import success is not proof. Re-check *after* installing other requirements —
  a dependency can downgrade torch.
- **Ollama:** a real streamed completion, plus `nvidia-smi` showing the model resident.
- **ComfyUI:** an image actually renders — and for anything image-conditioned, *look at it*.
  Status `success` is not evidence the output is correct.

If something fails: **stop and report it.** Do not silently work around it.

---

## 9. Git

Tracks **documentation and configs only** — never weights, never venvs. Identity is repo-local
(`git config --local`); commits are authored solely by the repo owner, with no AI co-author trailer.

`.gitignore` patterns without a leading slash match at **any depth** — `ai-toolkit/` also silently
matched `configs/ai-toolkit/`. Anchor them (`/ai-toolkit/`) and confirm with `git check-ignore -v`.
