# CLAUDE.md — Local AI Stack (`~/AI`)

Guidance for Claude Code sessions working in this directory.
**Read `PLAN.md` for the full build plan and rationale. This file is the short version: the rules.**

---

## 1. Machine facts (verified 2026-08-23, not assumed)

| | |
|---|---|
| CPU | AMD Ryzen 5 5600 — 6C/12T, Zen 3, no iGPU |
| GPU | RTX 5060 Ti 16G — Blackwell GB206, **sm_120**, 15.52 GiB usable, HW NVFP4 |
| Driver | `nvidia-open` 610.57.04, CUDA UMD **13.3** (`linux-cachyos-nvidia-open` 7.2.0-1) |
| PCIe | Gen4 x8 (board caps at Gen4 — this is correct, not a fault) |
| RAM | 31 GiB DDR4 + **zram-only swap (31.3 GiB). There is NO disk swap.** |
| OS | CachyOS rolling, kernel 7.2.0-1-cachyos, KDE Plasma / Wayland |
| Root FS | Btrfs on `/dev/nvme0n1p5`, `noatime,compress=zstd:1,ssd,discard=async` |
| `~/AI` | lives on the `@home` subvolume |
| Snapshots | `snapper` + `snap-pac` + `limine-snapper-sync` are **installed and active** |

**Desktop already consumes ~0.7 GiB VRAM.** Budget models against **~14.8 GiB**, not 16.

---

## 2. Shell — this matters, get it right

The login shell is **fish** (`/bin/fish`). Commands you hand the user must be fish-valid.

| Don't (bash) | Do (fish) |
|---|---|
| `export VAR=x` | `set -gx VAR x` (session) / `set -Ux VAR x` (persistent) |
| `cmd <<EOF … EOF` | write the file with the Write tool, or `bash -c '…'` |
| `$(cmd)` | `(cmd)` |
| `for f in *; do …; done` | `for f in *; …; end` |
| `VAR=x cmd` | `env VAR=x cmd` |
| `cmd && cmd2` | `cmd; and cmd2` (though `&&` works in fish ≥3.0) |

Note: the agent harness's own Bash tool does **not** run fish — heredocs work fine *for you*.
The fish rules apply to commands you print for the user to run.

---

## 3. Hard rules — do not violate

1. **Never install `python-pytorch` / `python-torchvision` from the Arch repos.** They break on every
   Python bump. PyTorch comes from `download.pytorch.org` wheels into a uv venv. Always.
2. **Never install `xformers`.** PyPI wheels top out at sm_89; it silently downgrades torch.
   ComfyUI's SDPA path (`--use-pytorch-cross-attention`) is the supported fast path here.
3. **Never use system Python (3.14.7) for ML.** Too new for ML wheels. Use the uv-managed 3.12 venv.
4. **PyTorch must be a cu130 build.** See §4. cu126 and older produce
   `no kernel image is available for execution on the device` on sm_120.
5. **Storage is the binding constraint.** 102 GiB free on a single drive shared with Windows 11.
   State the size of any download *before* proposing it, and keep a running total.
6. **Do not enable services at boot.** systemd **user** units, started on demand, to avoid idle GPU draw.
7. **Verify, don't assume.** VRAM figures, quant sizes and sm_120 library support change monthly.
   If you're stating something you did not check on this machine, say so explicitly.

---

## 4. The cu130 decision (settled — don't relitigate without new evidence)

**PyTorch 2.13.0+cu130** is the target. Verified available on the PyTorch index alongside
matching `torchvision 0.28.0+cu130` and `torchaudio 2.11.0+cu130` for cp312.

- NVFP4 acceleration in ComfyUI requires a **cu130** torch build **plus** `comfy-kitchen[cublas]`.
  Without cu130 an NVFP4 checkpoint still loads but falls back to emulation and can be
  **up to 2× slower than fp8** — which makes the 8.56 GiB FLUX NVFP4 download actively harmful.
- Driver UMD is 13.3, i.e. newer than cu130. No driver constraint.
- **Not cu132** (it exists): `comfy-kitchen` and all community SageAttention wheels target cu130.
  cu132 is ahead of the ecosystem with no upside here.
- **SageAttention:** compiled against an exact torch ABI. No prebuilt sm_120 wheel targets torch
  2.13 — so it is a build-from-source job on cu129 *and* cu130 alike. cu130 does not make this worse,
  and a second cu129 venv would **not** fix it. One venv. SDPA is the default launch profile.

---

## 5. Layout

```
~/AI/
├── CLAUDE.md            this file
├── PLAN.md              full plan + rationale + phase checklists
├── README.md            written during BUILD: what's installed, how to start it
├── comfy-venv/          CURRENT: torch 2.13.0+cu129, working but to be replaced
├── comfy-venv-cu130/    TARGET: built fresh, verified, then old one deleted
├── ComfyUI/             (not yet installed)
└── models/              ← dedicated Btrfs subvolume, chattr +C, snapshot-isolated
    ├── hf/              ← HF_HOME
    ├── ollama/          ← OLLAMA_MODELS
    └── comfyui/{diffusion_models,text_encoders,vae,loras,clip_vision}
```

**Every weight file goes under `~/AI/models/`. Nothing downloads twice.**

### Why a subvolume and not just `chattr +C`
Btrfs snapshots silently re-enable CoW for the first write after each snapshot, so `+C` alone is not
durable on a snapshotted subvolume — and `snap-pac` snapshots on **every pacman transaction**.
A nested subvolume is excluded from its parent's snapshots (btrfs snapshots are not recursive), which
both isolates the model store and makes `+C` actually stick. `+C` must be set on the directory
**before** files land in it; it does not apply retroactively.

---

## 6. Network flakiness

`pypi.nvidia.com` has timed out before (124s, 3 retries, failed). All hosts responded sub-second on
2026-08-23, but assume it will happen again.

- Always: `env UV_HTTP_TIMEOUT=300 uv pip install …`
- Fallback if resolution fights across indexes: `--index-strategy unsafe-best-match`
- Large weights: use `hf download` (resumable) — never plain `curl` for multi-GB files.
- **Never destroy a working install before its replacement is verified.** This is why the cu130 venv
  is built *alongside* `comfy-venv`, not on top of it.

---

## 7. Gotchas discovered during the audit

- `ollama-cuda` **depends on the full `cuda` package** (2.20 GiB down / 4.71 GiB installed).
  This is the one justified system-wide CUDA install — it is a hard dependency, it is pacman-managed
  so it tracks driver updates, and it provides the `nvcc` needed to build SageAttention later.
- The uv venv has **no `pip`**. Use `uv pip …`, always.
- HF hub leaves orphaned `*.incomplete` blobs after an interrupted download; they are **not** cleaned
  up on retry. Check `find ~/AI/models/hf -name '*.incomplete'` after any failed pull.
- `cmake` and `ninja` are **not installed** — needed only if SageAttention gets built from source.
- systemd user services do **not** inherit fish variables. Env vars must be repeated as
  `Environment=` lines inside each unit file.
- Linger is off, so user services stop at logout. That is the desired behaviour.

---

## 8. Verification gates

Never report a track as done without showing the proof.

- **Torch:** `torch.cuda.get_device_capability()` must return `(12, 0)`, `torch.cuda.get_arch_list()`
  must contain `sm_120`, and a real fp16 matmul on device must complete. Import success is not proof.
- **Ollama:** a real completion streamed back from `qwen2.5-coder:14b`, plus `nvidia-smi` showing the
  model resident in VRAM.
- **ComfyUI:** server reaches "To see the GUI go to…", and a FLUX NVFP4 sample actually renders.

If something fails: **stop and report it.** Do not silently work around it.

---

## 9. Git

This repo tracks **documentation and configs only** — never weights, never venvs. See `.gitignore`.
Identity is set repo-locally (`git config --local`); commits are authored solely by the repo owner.
