# Z-Image Turbo vs FLUX.2-klein-9B vs FLUX.2-dev — strengths and weaknesses

All three NVFP4, on an RTX 5060 Ti (sm_120), all at 832x1216. Findings come from
**~115 generated images across six batches** on 2026-08-24/25, all inspected individually.
FLUX.1-dev was also compared before being removed from the machine; its results are kept where
they add contrast.

**Settings used throughout:** Z-Image 8 steps / cfg 1.0 / euler-simple. klein-9B 28 steps /
guidance 2.0. FLUX.2-dev 28 steps / guidance 4.0. Both FLUX.2 models use `EmptyFlux2LatentImage`
and cfg 1.0 / euler-simple.

---

## The one-line answer

**Z-Image Turbo is the better default. klein-9B is the better instrument. FLUX.2-dev is the
quality ceiling you pay dearly for.**

Z-Image is 13x faster than FLUX.2-dev, uses half the VRAM, and has produced zero defects in ~50
renders. klein-9B gives most of FLUX.2-dev's detail at a quarter of the time. FLUX.2-dev is the
best renderer here but takes **80 seconds an image** and runs at 94% VRAM occupancy.

---

## Head-to-head summary

| Axis | Z-Image Turbo | FLUX.2-klein-9B | FLUX.2-dev | Winner |
|---|---|---|---|---|
| **Speed** (832x1216, warm) | **6.0 s** | 22 s | 80 s | **Z-Image, 13x over dev** |
| **Peak VRAM** | **8.0 GiB** | 11.7 GiB | **15.0 GiB (94% full)** | **Z-Image** |
| **Disk (transformer + encoder)** | **7.4 GiB** | 11.7 GiB | 31.0 GiB | **Z-Image** |
| **Reliability** | ~50 renders, **0 defects** | ~1 in 5 dim scenes re-roll | 16 renders, 0 skin defects | **Z-Image** |
| **Skin rendering** | consistently clean | speckle risk in low light | **clean, incl. dim scenes** | Z-Image / dev |
| **Hands** | clean | clean, sometimes softer | clean | tie |
| **Prompt adherence** | excellent | excellent | good, occasional scene miss | Z-Image / klein |
| **Material / texture detail** | good | very fine | **finest** | **dev, narrowly over klein** |
| **Environmental complexity** | good | excellent | excellent | klein / dev |
| **Reflection geometry** | pose mismatch seen | **excellent** | coherent but missed the subject | **klein** |
| **Small metallic detail** | good | **excellent** | **excellent** | klein / dev |
| **Colour handling** | natural | natural | **pushes saturation harder** | Z-Image / klein |
| **Unprompted artifacts** | none | none | **film-border frame edges** | Z-Image / klein |
| **Text rendering** | gibberish words, correct numbers | same | same | tie (all poor) |
| **Licence** | **Apache 2.0 — commercial OK** | non-commercial | non-commercial | **Z-Image** |

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

## FLUX.2-dev — strengths

**The highest quality ceiling of the three.** Skin rendering is genuinely filmic, jewellery
filigree and chain links resolve as well as klein's, and lighting is handled with more subtlety.

**Clean skin in low light — the artifact is klein-specific.** The `bus_night` scene that produced
speckling on klein-9B came out completely clean on FLUX.2-dev, as did `pub_night`. This is useful
diagnostic information: the low-light skin artifact is **not** a FLUX.2 family trait, it is
specific to klein-9B (and most likely to its quantized Qwen3-8B encoder).

**It runs at all**, which was not a given. The 19.59 GiB transformer against 14.4 GiB usable VRAM
works via `comfy-aimdo` dynamic offload — the log shows `Model Flux2 prepared for dynamic VRAM
loading. 20061MB Staged`.

## FLUX.2-dev — weaknesses

**80 seconds per image.** Warm renders were remarkably consistent at 75.8–81.9 s across 16
generations (97.7 s cold). That is **13x Z-Image and 3.6x klein-9B** for output that is better but
not 13x better.

**94% VRAM occupancy.** Peak observed 15,397 MiB of 16,311. Nothing else can touch the GPU while
it runs, and there is very little headroom — a larger resolution would likely OOM.

**31.0 GiB of disk** for transformer plus encoder, versus 7.4 GiB for Z-Image.

**Unprompted film-border artifact.** Several renders came back with a visible film-frame border
drawn around all four edges that was never requested. Neither other model does this.

**Pushes colour harder.** The `fish_market` scene came out considerably more saturated blue than
klein's version of the identical prompt.

**Missed the subject in the reflection probe.** The two-mirror fitting-room scene produced two
geometrically consistent reflections but no real subject in frame — coherent, but not what the
prompt described. klein handled the same probe correctly.

## Shared weaknesses (all three models)

**Text is unusable.** Words on signs, menus, book spines and packaging are consistently
gibberish on all three. Numbers and currency symbols render correctly, which is a curious and
reproducible split. If a render needs legible words, neither model will provide them.

**Ethnicity adherence is inconsistent.** Both occasionally return a subject who does not match the
requested ethnicity — a requested Latina reading as ambiguous/white on Z-Image, and a
two-subject prompt returning two East Asian women when one was specified as Latina on klein.
Naming specific features (skin tone, hair texture) rather than a demonym alone appears to help,
though this has not been tested systematically. Affects all three.

**Prompt scope drift on wardrobe.** Soft realism cues like "unretouched" and "no makeup" can pull
a render toward more undressed framing than the scene implied. Stating wardrobe explicitly
("fully clothed", "wearing a t-shirt") reliably prevents this on all three.

---

## Practical guidance

**Use Z-Image when:** iterating on prompts, generating volume, the scene is dim, hands are in
frame, the output might be used commercially, or you want a result you can trust without
inspecting it.

**Use klein-9B when:** the scene is well-lit, material or environmental texture is the point
(fabric, food, tools, weathered surfaces), reflections need to be geometrically correct, or you
are producing a small number of hero images and will inspect each one.

**Use FLUX.2-dev when:** the image genuinely matters more than the 80 seconds — a hero shot, a
final render, something where klein's texture is not quite enough. Not for iteration, not for
volume, and not while you need the GPU for anything else.

**Always, for klein-9B face renders in low light:** generate 2-3 seeds and look at each. Do not
trust a single render because the log showed no errors.

For exploratory work, the speed ratio in the table above matters more than it looks: thirteen
Z-Image attempts at a prompt will almost always beat one FLUX.2-dev attempt, because the real
bottleneck is finding the right prompt and seed, not any single model's quality ceiling.
