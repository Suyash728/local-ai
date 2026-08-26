# ComfyUI Web UI — how to use it

Companion to `README.md` (what's installed) and `MODEL-COMPARISON.md` (which model to pick). This
file is about the browser interface itself: starting it, reading the node graph, and the specific
gotchas for the three models installed on this machine.

Everything below describes the **manual, click-through** way of using ComfyUI. For scripted batch
generation (the way every comparison in `MODEL-COMPARISON.md` and `PROMPTING.md` was actually
produced), see "Scripting instead of clicking" at the bottom — the web UI queues one image at a
time by hand, which doesn't scale past a handful of renders.

---

## Starting it

```fish
systemctl --user start comfyui
```

Then open **http://127.0.0.1:8188** in a browser. It takes ~15-20 seconds to be reachable — the
server is loading Python, scanning `~/AI/models/comfyui/` for weights, and initializing CUDA.

**Stop it when you're done** to free VRAM (nothing else can use the GPU while a model is loaded):

```fish
systemctl --user stop comfyui
```

It does **not** start automatically at boot or login — that's deliberate, to avoid idle GPU draw.
`systemctl --user status comfyui` shows whether it's currently running.

Check it's actually up:

```fish
curl -s http://127.0.0.1:8188/system_stats
```

---

## The interface

**Canvas (center)** — a node graph. Each box is one step in the pipeline: load a model, encode a
text prompt, sample, decode to pixels, save. Data flows left to right along the connecting lines.

| Action | How |
|---|---|
| Pan | middle-mouse drag, or two-finger trackpad scroll |
| Zoom | scroll wheel |
| Add a node | double-click empty canvas → search, or right-click → Add Node |
| Run the graph | **Queue** button (bottom bar), or `Ctrl+Enter` |
| Load a saved workflow | Workflow menu (top toolbar) → Open |
| Reconstruct a workflow from a past image | drag the PNG into the browser window |

That last one matters here: **every image ComfyUI saves has its full workflow embedded in the PNG
metadata.** Drag any file from `ComfyUI/output/` or `docs/samples/` into the browser and you get
back the exact node graph that produced it — model, prompt, seed, sampler settings, all of it.
This is the fastest way to get a working starting graph for any of the three installed models,
since every one of them has already been run and saved at least once.

**Or skip that and use the saved one.** A verified, correctly-wired Z-Image Turbo workflow lives
at `ComfyUI/user/default/workflows/z-image-turbo.json` — it appears directly in the browser's
Workflows sidebar (or Workflow menu → Open) as **"z-image-turbo-verified"**. Confirmed executing
end-to-end with no shape errors before being saved. Just replace the placeholder positive-prompt
text and hit Queue. Not tracked in git (`ComfyUI/` is gitignored — see `.gitignore`); if it's ever
missing, the node graph to rebuild it is exactly the Z-Image settings table below, wired
`UNETLoader → CLIPLoader → CLIPTextEncode(×2) → KSampler → VAEDecode → SaveImage`.

**Queue button** runs the current graph once. Progress shows on the currently-executing node;
finished images land in `ComfyUI/output/` and also appear in a preview panel. Queueing again while
one job runs adds a second job rather than interrupting the first.

**Workflow menu** — save the current graph as a `.json` file, load one back, or browse the bundled
example templates (Workflow → Browse Templates) if starting from nothing.

---

## Minimum working graph

For any of the three text-to-image models here, the graph is the same six nodes:

```
Load Diffusion Model  ─┐
Load CLIP             ─┤→ CLIP Text Encode (positive) ─┐
                        │  CLIP Text Encode (negative) ─┤→ KSampler → VAE Decode → Save Image
Load VAE               │  Empty Latent Image ───────────┘
                        └──────────────────────────────────┘
```

The dropdowns in `Load Diffusion Model`, `Load CLIP` and `Load VAE` list every file under
`~/AI/models/comfyui/{diffusion_models,text_encoders,vae}/` — the same `extra_model_paths.yaml`
config that the scripted batches use, so there's exactly one copy of every weight regardless of
which way you generate.

## Model-specific settings — get these wrong and it errors or silently mis-loads

These are the exact values used for every comparison in `MODEL-COMPARISON.md`.

### Z-Image Turbo

| Node | Setting |
|---|---|
| Load Diffusion Model | `z_image_turbo_nvfp4.safetensors` |
| Load CLIP | `qwen_3_4b_fp4_mixed.safetensors`, type **`stable_diffusion`** |
| Load VAE | `ae.safetensors` |
| Empty Latent Image | the **default** `EmptySD3LatentImage` node — no special node needed |
| KSampler | 8 steps, cfg **1.0**, euler / simple |
| Guidance node | none — Z-Image doesn't use one |

### FLUX.2-klein-9B

| Node | Setting |
|---|---|
| Load Diffusion Model | `flux-2-klein-9b-nvfp4.safetensors` |
| Load CLIP | `qwen_3_8b_fp4mixed.safetensors`, type **`stable_diffusion`** |
| Load VAE | `flux2-vae.safetensors` — **not** `ae.safetensors`, different file |
| Empty Latent Image | **`Empty Flux 2 Latent`** node (`EmptyFlux2LatentImage`) — search for "flux 2" when adding the node |
| Flux Guidance node | insert between positive CLIP Text Encode and KSampler, value **2.0** |
| KSampler | 28 steps, cfg **1.0**, euler / simple |

### FLUX.2-dev

Same shape as klein-9B, different files:

| Node | Setting |
|---|---|
| Load Diffusion Model | `flux2-dev-nvfp4.safetensors` |
| Load CLIP | `mistral_3_small_flux2_fp4_mixed.safetensors`, type **`flux2`** |
| Load VAE | `flux2-vae.safetensors` |
| Empty Latent Image | **`Empty Flux 2 Latent`**, same as klein |
| Flux Guidance node | value **4.0** |
| KSampler | 28 steps, cfg **1.0**, euler / simple |

⚠️ **`Empty Flux 2 Latent` is not optional for the two FLUX.2 models.** FLUX.2's latent space is
128 channels at 16x spatial downscale; FLUX.1/Z-Image's is 16 channels at 8x. Using the default
latent node with a FLUX.2 model fails with a shape-mismatch error rather than silently producing
garbage — annoying but not dangerous.

⚠️ **`type` on Load CLIP matters even though it looks cosmetic.** ComfyUI auto-detects the actual
text-encoder architecture from the weights (by tensor shape), and `type` only disambiguates edge
cases. `stable_diffusion` is correct for both Z-Image and klein-9B despite neither being
Stable Diffusion — this is a ComfyUI enum quirk, not a mistake. FLUX.2-dev needs `flux2`
specifically because its Mistral encoder is shared with `klein_te` internally and the type is
what tells ComfyUI which of the two encoder wrappers to use.

⚠️ **`ae.safetensors` vs `flux2-vae.safetensors` — these are two different files, not a naming
inconsistency.** FLUX.1-dev and Z-Image Turbo share one VAE (`ae.safetensors`, verified
byte-identical). Both FLUX.2 models use a different one (`flux2-vae.safetensors`). Loading the
wrong one for a given model will not error — it will produce a corrupted or garbled image, which
is a much worse failure mode than an error message.

---

## Reading progress and errors

- A green outline on a node = currently executing.
- The bottom-left corner shows queue depth if more than one job is queued.
- Errors appear as a red-bordered node with the failure reason in a popup — usually a shape
  mismatch (wrong latent node) or a missing file (wrong model/CLIP/VAE name).
- Full server logs: `journalctl --user -u comfyui -f` in a terminal, useful for anything the UI
  popup doesn't explain — e.g. confirming NVFP4 acceleration is actually active
  (`Native ops: ... nvfp4` in the log) rather than falling back to emulation.

---

## Scripting instead of clicking

The web UI is the right tool for interactive exploration — tweaking one prompt, trying a few
seeds, building a new workflow. It is the wrong tool for generating more than a handful of images,
because each one needs a manual Queue click and a wait.

Every batch comparison in this repo (`PROMPTING.md`, `MODEL-COMPARISON.md`) was produced by
posting the same JSON graph structure shown above directly to ComfyUI's HTTP API instead:

```fish
curl -s http://127.0.0.1:8188/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": { ...six nodes as JSON... }, "client_id": "..."}'
```

The response includes a `prompt_id`; poll `http://127.0.0.1:8188/history/<prompt_id>` until
`status.status_str` is `"success"` to get the output filename. This is how dozens of images get
generated back-to-back without touching the browser — worth reaching for once you're past
one-off experimentation and want to sweep prompts, seeds, or settings.
