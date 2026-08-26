# OpenCode — agentic coding on local models

Companion to `OLLAMA-ACCESS.md` (talking to the models) and `WEB-ACCESS.md` (giving them web
access). This is the third leg: an actual coding agent — reads files, edits them, runs shell
commands, iterates — driven entirely by the local `gpt-oss:20b` model.

**Read "The real story" before trusting a run.** The setup here required finding and fixing a
genuine reliability bug, not just wiring an endpoint together. Skipping straight to Usage risks
using the broken configuration.

---

## What and how installed

[opencode.ai](https://opencode.ai) (`anomalyco/opencode` on GitHub), MIT licensed. Installed from
the **official `cachyos-extra-v3` repo** — not the generic `curl | bash` installer the project's
own docs lead with — matching how everything else on this machine has gone through pacman/shelly
rather than untracked install scripts:

```fish
sudo pacman -S opencode
```

45.95 MiB download, 169.21 MiB installed. Version 1.18.23 as installed 2026-08-26.

---

## The real story: default config silently produces broken agent runs

The obvious setup — point opencode at Ollama's OpenAI-compatible endpoint, pick a tool-capable
model — **looked complete and was actually broken.** This section exists so it doesn't have to be
rediscovered.

### Symptom

`gpt-oss:20b` (verified in `WEB-ACCESS.md` as categorically better than qwen2.5-coder at simple
tool-calling) hallucinated tool names that don't exist in opencode's actual toolset:

```
Model tried to call unavailable tool 'container.exec'. Available tools: bash, edit, glob,
grep, invalid, read, skill, task, todowrite, webfetch, write.
```

Reproduced twice, with **different** hallucinated names each time (`container.exec`,
`repo_browser.print_tree`) — not a one-off. This is a different failure from anything found
testing the model against my own simple two-tool schema in `WEB-ACCESS.md`; opencode's toolset is
larger and more specifically named, and something about it wasn't reaching the model intact.

### Root cause, found and verified — not assumed

Ollama's own integration docs (`docs.ollama.com/integrations/opencode`) state opencode requires
**64k or higher context length**. The config in every guide found online (including opencode's own
docs) never sets this — Ollama defaults to 4096. The likely mechanism: opencode's system prompt,
which enumerates its full real toolset, plus the growing conversation, doesn't fit in a 4096-token
window, so the model loses the actual tool list and falls back to plausible-sounding names from its
own training data.

**This was verified with a controlled A/B test, not taken on faith:**

1. Created `gpt-oss-agent-32k` — a custom Ollama model tag via `Modelfile` (`FROM gpt-oss:20b` +
   `PARAMETER num_ctx 32768`), reusing the existing weight layers (no re-download).
2. Ran the **identical task, identical directory, identical file** against both the plain 4096-ctx
   `gpt-oss:20b` and the 32k variant.
3. **4096 ctx: failed** with `repo_browser.print_tree` — the exact same failure class as before.
   **32k ctx: succeeded** — correct `glob` → `read` → `edit` → `read`-to-verify sequence, correct
   minimal diff, confirmed on disk with `git diff`.
4. Repeated the 32k run a second time to rule out a fluke: succeeded again, same clean tool
   sequence.

Only the context length differed between the failing and succeeding runs. Everything else —
model weights, task, directory, opencode version — was identical.

### The VRAM cost was much smaller than expected

Before testing, the concern was real: naive linear KV-cache scaling from 4096 to 65536 tokens
(16x) could plausibly demand another 15-20 GiB, nowhere near available. Measured instead:

| Context | VRAM used |
|---|---:|
| 4096 (default) | 14.2 GiB |
| **32768 (32k)** | **14.56 GiB** |

**+360 MB for 8x the context.** gpt-oss-20b's actual KV-cache footprint per token is far smaller
than the worst-case estimate — plausibly grouped-query attention with few KV heads. 32k was chosen
over the documented 64k specifically because it already fixed the problem in testing at negligible
extra cost; 64k was not tested and may cost more, proportionally or not — unverified either way.

### The fix does not transfer to qwen2.5-coder

Built `qwen2.5-coder-agent-32k` the same way, for parity. **It did not fix qwen2.5-coder's problem**
— which is a different bug: it emitted its tool call as literal fenced JSON text
(` ```json {"name": "read", ...} ``` `) instead of a structured call, the exact failure mode
already documented in `WEB-ACCESS.md` for this model. That bug is about the model's own
`<tool_call>` tag-wrapping consistency at Q4 quantization, unrelated to context length. Raising
context doesn't touch it.

**Conclusion: `gpt-oss-agent-32k` is the only model on this machine verified reliable for
opencode's actual tool loop.** qwen2.5-coder remains registered in the config for reference but is
not recommended here — same finding as `WEB-ACCESS.md`, now confirmed on a second, more complex
toolset.

### A second bug hit and fixed along the way: opencode's directory permission wall

While debugging, a run failed with `permission requested: external_directory (/tmp/...); auto-rejecting`.
This looked at first like more model unreliability — it wasn't. opencode's own permission system
auto-denies file access outside what it considers a safe project root when running non-interactively
(no TTY to prompt for approval), and this session's scratchpad lives under a `/tmp/claude-.../`
path that tripped it. Fixed by testing from an ordinary directory under `$HOME` instead, which is
also how anyone would actually use this day to day. Not an opencode or model defect — worth
knowing if a `run` invocation fails with this specific error and the directory is somewhere
unusual.

### A CLI shortcut that didn't work as documented

`ollama launch opencode --model gpt-oss:20b --config -y` — the "sanctioned" integration path
per Ollama's own docs — failed with `Error: model selection requires an interactive terminal; use
--model to run in headless mode` **despite `--model` being passed**, in every flag ordering and
model-name format tried. Not pursued further; the Modelfile + manual `opencode.json` approach above
is what's actually in use and verified working. Worth retesting on a future Ollama version.

---

## Configuration

`~/.config/opencode/opencode.json` — not tracked in this git repo (it's a per-user tool config
under `$HOME`, not project-scoped like everything under `~/AI/`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "http://127.0.0.1:11434/v1" },
      "models": {
        "gpt-oss-agent-32k": { "name": "gpt-oss 20B (local, 32k ctx, tool-calling verified)" },
        "qwen2.5-coder-agent-32k": { "name": "Qwen2.5-Coder 14B (local, 32k ctx)" },
        "gpt-oss:20b": { "name": "gpt-oss 20B (local, default 4k ctx - unreliable, see above)" },
        "qwen2.5-coder:14b-instruct-q4_K_M": { "name": "Qwen2.5-Coder 14B (default 4k ctx)" }
      }
    }
  },
  "model": "ollama/gpt-oss-agent-32k"
}
```

**The 4096-ctx model tags are kept registered deliberately** — as a live reminder and a way to
reproduce the original failure if this needs debugging again. `ollama/gpt-oss-agent-32k` is the
default; every other entry here is unreliable or unverified for actual agentic use.

### Recreating the custom model tags

Not stored as files in this repo — two lines each, reproduced here:

```fish
echo "FROM gpt-oss:20b
PARAMETER num_ctx 32768" | ollama create gpt-oss-agent-32k -f -

echo "FROM qwen2.5-coder:14b-instruct-q4_K_M
PARAMETER num_ctx 32768" | ollama create qwen2.5-coder-agent-32k -f -
```

Both reuse the base model's existing weight layers — no re-download, seconds to create.

---

## Usage

```fish
systemctl --user start ollama    # opencode needs a running Ollama server
cd your-project
opencode run "your task here"    # one-shot, non-interactive
opencode                         # interactive TUI
```

`opencode run` is what every verification in this file used — non-interactive, scriptable, and it
prints the actual tool calls made (`Glob`, `Read`, `Edit`, ...) so you can see what it did rather
than just trusting the final summary. Logs land at `~/.local/share/opencode/log/opencode.log` if a
run needs debugging — this is where the `UnknownError` messages above were actually diagnosed.

**Run it from an ordinary directory under `$HOME` or a normal project path** — not a deeply nested
temp/scratch path, per the permission-wall issue above.

**VRAM note:** same constraint as everything else on this GPU — opencode's model and ComfyUI/other
Ollama models can't be resident simultaneously. `systemctl --user stop ollama` when done to release
the ~14.6 GiB.

---

## Verified working, real transcript

```
$ opencode run --model ollama/gpt-oss-agent-32k \
    "Read greet.py and rewrite the print statement to use an f-string instead of \
     string concatenation. Then show me the final file contents."

> build · gpt-oss-agent-32k
✱ Glob "greet.py"                    1 match
→ Read greet.py                      [offset=1, limit=2000]
We need rewrite print statement to use f-string. So modify line 2. Let's edit.
← Edit greet.py
Index: /home/suyash/opencode-test/greet.py
@@ -1,2 +1,2 @@
 def greet(name):
-    print("Hello " + name)
+    print(f"Hello {name}")

**Updated greet.py**
```python
def greet(name):
    print(f"Hello {name}")
```

$ git diff
-    print("Hello " + name)
+    print(f"Hello {name}")
```

Confirmed on disk with `git diff`, not just the chat transcript. Reproduced twice.
