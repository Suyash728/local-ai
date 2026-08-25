# Z-Image Turbo vs FLUX.2-klein-9B — strengths and weaknesses

Both NVFP4, both on an RTX 5060 Ti (sm_120), both at 832x1216. Findings below come from
**~100 generated images across five batches** on 2026-08-24/25, all inspected individually.
FLUX.1-dev was also compared before being removed from the machine; its results are kept where
they add contrast.

**Settings used throughout:** Z-Image 8 steps / cfg 1.0 / euler-simple. klein-9B 28 steps /
guidance 2.0 / cfg 1.0 / euler-simple, `EmptyFlux2LatentImage`.

---

## The one-line answer

**Z-Image Turbo is the better default. klein-9B is the better instrument.**

Z-Image is ~3.7x faster, uses 4 GiB less VRAM, and has produced zero defects in ~50 renders.
klein-9B produces visibly finer material and environmental detail when it works, but needs
checking — and is markedly riskier in low light.

---

## Head-to-head summary

| Axis | Z-Image Turbo | FLUX.2-klein-9B | Winner |
|---|---|---|---|
| **Speed** (832x1216, warm) | **6.0 s** (8 steps) | 22 s (28 steps) | **Z-Image, 3.7x** |
| **Peak VRAM** | **8.0 GiB** | 11.7 GiB | **Z-Image** |
| **Model size on disk** | **4.20 + 3.24 GiB** | 5.37 + 6.34 GiB | **Z-Image** |
| **Reliability** | ~50 renders, **0 defects** | ~1 in 5 dim scenes need a re-roll | **Z-Image** |
| **Skin rendering** | consistently clean | speckle artifact risk in low light | **Z-Image** |
| **Hands** | clean, incl. two-hand tool grips | clean, occasionally softer | **Z-Image, narrowly** |
| **Prompt adherence** | excellent | excellent | tie |
| **Material / texture detail** | good | **noticeably finer** | **klein** |
| **Environmental complexity** | good | **best available here** | **klein** |
| **Reflection geometry** | good, occasional pose mismatch | **excellent, multi-mirror consistent** | **klein** |
| **Small metallic detail** | good | **excellent (filigree, chain links)** | **klein** |
| **Multiple faces** | good | good, distinct faces | tie |
| **Text rendering** | gibberish words, correct numbers | gibberish words, correct numbers | tie (both poor) |
| **Licence** | **Apache 2.0 — commercial OK** | non-commercial only | **Z-Image** |

---

## Z-Image Turbo — strengths

**Reliability is its headline feature.** Roughly 50 renders across five batches, zero skin
artifacts, zero anatomical failures, zero re-rolls needed. No other model tested here can say that.

**Speed changes how you work.** At 6 s a render, iterating on a prompt is conversational. At 22 s
it is a considered decision. This matters more in practice than any single-image quality gap.

**Hands are not a weakness.** Documented as a FLUX-family failure mode early in this project, and
Z-Image simply has not exhibited it: both hands gripping a wok handle and ladle simultaneously,
both arms raised pegging laundry, a two-hand guitar pose, phone-in-hand mirror selfies.

**Reflections work.** Rendered a faint window reflection on a train and a correct phone-in-mirror
gym selfie — both cases where FLUX.1 failed outright.

**Apache 2.0.** The only commercially usable image model installed here. klein-9B, FLUX.2-dev and
FLUX.1-dev are all non-commercial.

## Z-Image Turbo — weaknesses

**Lower texture ceiling.** Side by side on the same prompt, klein resolves finer fabric weave,
grain, filigree and small hardware. Z-Image's output is clean but comparatively smoother.

**Reflection pose can mismatch.** In the fitting-room probe the subject holds a phone at her face
while her reflection reaches sideways to the mirror — geometrically plausible mirror, wrong pose
inside it. klein got the same probe right.

**Slightly plainer environments.** Backgrounds are convincing but less densely detailed than
klein's on identical prompts.

---

## FLUX.2-klein-9B — strengths

**Best material and environmental detail available on this machine.** The fish-market render
(cold dawn light against warm bulbs, visible breath, wet rubber-glove specularity, ice texture) and
the night-market render (string-light bokeh, steam physics, produce in bags) are the two most
detailed images this project produced.

**Reflection geometry is excellent.** The two-angled-mirror fitting-room probe kept pose, garment
and phone position consistent across all three instances of the subject. The salon scene rendered
multiple mirrors with consistent geometry.

**Small metallic detail.** Filigree earrings with resolved perforations, individual links in a fine
chain necklace.

**Numbers in text render correctly** — prices like `$50`, `$60`, `795` come out clean even though
the words around them do not.

## FLUX.2-klein-9B — weaknesses

**The low-light skin artifact.** The single most important thing to know. Speckled dark noise
across cheeks and neck, at worst bleeding garment texture onto the face. Established across three
batches:

- appears **only in dim scenes**, never in a well-lit one
- **not** correlated with skin tone — a dark-skinned subject in bright midday sun was clean,
  a light-skinned subject in a dim pub was clean, and failures occurred with both
- **severity is reduced but not eliminated** by removing skin-imperfection language from prompts
  ("blemishes", "scars", "under-eye shadows")
- guidance 4.0 makes it much worse; 2.0 is the working value

Roughly 1 in 5 dim-scene renders needs a re-roll. Bright scenes have been reliable.

**3.7x slower and 3.7 GiB more VRAM** than Z-Image for output that is better but not categorically
better.

**Non-commercial licence.** `flux-non-commercial-license`. Fine for personal and research work,
not for anything revenue-generating.

**Gated download.** Requires manually accepting a licence on the Hugging Face page — no token
bypasses it.

---

## Shared weaknesses (both models)

**Text is unusable.** Words on signs, menus, book spines and packaging are consistently
gibberish on both. Numbers and currency symbols render correctly, which is a curious and
reproducible split. If a render needs legible words, neither model will provide them.

**Ethnicity adherence is inconsistent.** Both occasionally return a subject who does not match the
requested ethnicity — a requested Latina reading as ambiguous/white on Z-Image, and a
two-subject prompt returning two East Asian women when one was specified as Latina on klein.
Naming specific features (skin tone, hair texture) rather than a demonym alone appears to help,
though this has not been tested systematically.

**Prompt scope drift on wardrobe.** Soft realism cues like "unretouched" and "no makeup" can pull
a render toward more undressed framing than the scene implied. Stating wardrobe explicitly
("fully clothed", "wearing a t-shirt") reliably prevents this on both.

---

## Practical guidance

**Use Z-Image when:** iterating on prompts, generating volume, the scene is dim, hands are in
frame, the output might be used commercially, or you want a result you can trust without
inspecting it.

**Use klein-9B when:** the scene is well-lit, material or environmental texture is the point
(fabric, food, tools, weathered surfaces), reflections need to be geometrically correct, or you
are producing a small number of hero images and will inspect each one.

**Always, for klein-9B face renders in low light:** generate 2-3 seeds and look at each. Do not
trust a single render because the log showed no errors.
