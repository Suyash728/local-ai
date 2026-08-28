# OpenCode — agentic coding on local models

Companion to `OLLAMA-ACCESS.md` (talking to the models) and `WEB-ACCESS.md` (giving them web
access). This is the third leg: an actual coding agent — reads files, edits them, runs shell
commands, iterates — driven entirely by the local `gpt-oss:20b` model.

Everything is already installed and configured. **Start here; the rest of this file is background
on how it got that way, and is only needed when something misbehaves.**

---

## Quick start

### 1. Start the model server (always, first)

```fish
systemctl --user start ollama
```

Nothing works without this — opencode talks to Ollama on `127.0.0.1:11434`. It is not enabled at
boot, so this is needed after every reboot. When you're done: `systemctl --user stop ollama` to
free the ~14 GiB of VRAM.

### 2a. Terminal

```fish
cd ~/my-project
opencode
```

That's it. It opens a TUI already set to `gpt-oss-agent-32k` (local) — the status line reads
`Build · gpt-oss 20B (local, 32k ctx…) Ollama (local)`. Type a task and press Enter. The footer
shows the keys: `tab` switches agents, `ctrl+p` opens the command palette.

### 2b. VS Code

Open a project, then press **`ctrl+escape`**. The opencode TUI opens in a terminal panel — same
tool, same config. Useful extras:

| Key | Does |
|---|---|
| `ctrl+escape` | open opencode |
| `ctrl+shift+escape` | open it in a new tab |
| **`ctrl+alt+K`** | insert the file you're viewing as an `@`-mention |

`ctrl+alt+K` is worth the muscle memory: it puts the exact file path into your prompt so the model
never has to guess it (see the hallucinated-path section below for why that matters).

### 3. Ask for something specific

A real run, start to finish. Given `config.py`:

```python
def parse_config(raw):
    # TODO: validate port
    return raw
```

asked: *"Implement port validation in parse_config in config.py and remove the TODO."* →

```diff
 def parse_config(raw):
-    # TODO: validate port
+    port = raw.get("port")
+    if not isinstance(port, int) or not (1 <= port <= 65535):
+        raise ValueError(f"Invalid port: {port}")
     return raw
```

Verified working: `parse_config({"port": 8080})` returns, `parse_config({"port": "abc"})` raises
`ValueError: Invalid port: abc`. It even chose a sensible range bound unprompted.

**Name the function and the file, and say what to remove.** This is a 20B model at 4-bit — "make
parse_config better" gets vague results. Measured on the same task: 3/3 correct with a precise
prompt, 2/4 with a vague one.

**Work in a git repo and read `git diff` before committing.** It succeeds often enough to be
genuinely useful and fails often enough that unreviewed commits would be a mistake.

### Scripting it

```fish
opencode run --format json "your task" > events.json
```

Use `--format json` whenever output is redirected or piped — see the warning under Usage below.

### If something looks wrong

```fish
opencode run --print-logs --log-level DEBUG "your task"   # see every step
systemctl --user status ollama                            # is the server up?
```

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

### The `external_directory` wall — and its real cause (corrected 2026-08-27)

A run first failed with `permission requested: external_directory (/tmp/...); auto-rejecting`, and
this file previously blamed the unusual scratchpad path. **That was only half right.** On
2026-08-27 the same rejection reproduced from an ordinary `~/oc-test` directory, and the JSON event
stream showed why:

```json
"tool": "read",
"input": { "filePath": "/home/suyark/oc-test/fib.py" },
"error": "The user rejected permission to use this specific tool call."
```

`/home/**suyark**/` — and on another run `/home/**suyany**/`. **The model was hallucinating the
absolute path**, mangling the username differently each time. opencode then correctly saw a path
outside the project, classified it `external_directory`, and auto-rejected. The sandbox was working
exactly as designed; the model was feeding it garbage.

The symptom is nasty because it does not look like a hallucination: `opencode run` with output
redirected produces **no output, no error, and a non-zero exit after the timeout**. Only a TTY or
`--format json` reveals the rejected path.

#### Why it happens — and why the first fix only half-worked

opencode's **own system prompt tells the model to construct absolute paths**:

> **Path Construction:** Before using any file system tool (e.g. `read` or `write`), you must
> construct the full absolute path for the file_path argument. Always combine the absolute path of
> the project's root directory with the file's path relative to the root.

(Read out of the binary: `strings (readlink -f (which opencode)) | grep -i "absolute path"`.)

The first attempt at a fix told the model the opposite — "never write an absolute path" — which
put `AGENTS.md` in direct conflict with the system prompt. The model followed one or the other
roughly half the time, which is exactly the intermittent failure rate observed. **Do not fight
opencode's prompt.**

#### The fix that works: pin the literal home directory

`~/.config/opencode/AGENTS.md` now works *with* the absolute-path requirement and removes the need
to recall the one string the model kept getting wrong:

> The home directory on this machine is exactly `/home/suyash`. It is spelled s-u-y-a-s-h. Never
> write any other spelling. When a tool returns a path, reuse that exact string. Before calling
> `write` or `edit`, check the path starts with the project root you were given.

Measured after this change — **7/7 writes succeeded, 0 mistyped paths**: 4 runs creating a file at
the project root, plus 3 creating `src/utils/slugify.py`, the harder nested case.

`external_directory` stays at `ask` rather than `allow`. Allowing it would silence the prompt by
letting the model write to `/home/suyark/...` — a directory that does not exist — instead of
failing visibly. The prompt is the symptom; the path is the bug.

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
  "model": "ollama/gpt-oss-agent-32k",
  "autoupdate": false,
  "share": "disabled",
  "permission": {
    "read": "allow", "glob": "allow", "grep": "allow",
    "edit": "allow", "write": "allow", "bash": "allow", "webfetch": "allow",
    "external_directory": "ask"
  }
}
```

**The 4096-ctx model tags are kept registered deliberately** — as a live reminder and a way to
reproduce the original failure if this needs debugging again. `ollama/gpt-oss-agent-32k` is the
default; every other entry here is unreliable or unverified for actual agentic use.

**On the `permission` block:** in-project tools are allowed so non-interactive runs don't stall
waiting for approval that can never arrive. `external_directory` stays at `ask` on purpose — see
the hallucinated-path section above. The valid keys were read out of the opencode binary
(`bash`, `edit`, `read`, `write`, `glob`, `webfetch`, `external_directory`).

### The other config file: `~/.config/opencode/AGENTS.md`

Loaded into every session regardless of project. This is what stops the hallucinated-path failure,
so **it is not optional** — if agentic runs start failing mysteriously, check it still exists.
It also carries house style (match surrounding code, don't add docstrings/type hints that the file
doesn't already use), which matters because gpt-oss otherwise writes very verbose Python.

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

### Interactive — the normal way to use it

```fish
systemctl --user start ollama    # opencode needs a running Ollama server
cd your-project
opencode                         # TUI, uses gpt-oss-agent-32k by default
```

The TUI is the recommended mode. Everything works there: it has a terminal, so it can prompt for
permissions, and output streams as it goes.

### Scripted / one-shot

```fish
opencode run "your task here"                     # needs a terminal
opencode run --format json "..."  > events.json   # for redirecting/piping
opencode run --print-logs --log-level DEBUG "..." # when something misbehaves
```

⚠️ **Use `--format json` whenever output is redirected or piped.** Plain `opencode run` with
stdout going to a file or pipe was observed doing the work but never exiting — the edit landed
correctly, then the process sat until killed. With a TTY it exits 0 normally. `--format json`
emits one JSON event per line and terminates cleanly, and is also far easier to check
programmatically (each tool call appears as `{"type":"tool", ...}` with its input and status).

⚠️ **`$SHELL` must be a shell that starts cleanly non-interactively.** opencode's bash tool spawns
`$SHELL`. With the login shell (fish) or bash it completes fine; a zsh configured with heavy
interactive startup hung every bash-tool call with no error. If bash-tool tasks hang, test with
`env SHELL=/bin/bash opencode run ...` to confirm before blaming the model.

Logs land at `~/.local/share/opencode/log/opencode.log`.

---

## Context and memory — measured

Three separate layers, often confused with each other. All figures below were measured on this
machine on 2026-08-28.

### Layer 1 — Ollama's KV cache (verified working)

Set in the ollama user unit:

```
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0     # 8-bit quantised KV cache
```

**Prefix reuse across turns is real, and large.** Ollama keeps up to 32 rolling context
checkpoints per slot (`created context checkpoint 1 of 32 …`). Continuing a session with
`opencode run --continue`:

| Turn | Tokens actually prefilled |
|---|---:|
| 1 | **6 774** (full prompt) |
| 2 | **19** |

Turn 2 re-processed 19 tokens instead of ~6.8k — the shared prefix came from cache. Prefill runs
at roughly **4 850 tok/s**, generation at **~90 tok/s**.

Note `opencode`'s own token report always shows `"cache": {"write": 0, "read": 0}`. That is the
OpenAI-compatible provider having no field to report Ollama's caching through — **not** an
indication that caching is off. Ollama's log is the authority.

### Layer 2 — how big the window can be

`gpt-oss:20b` supports **131 072** natively; our `gpt-oss-agent-32k` tag pins `num_ctx 32768`.
Raising it is cheap until it isn't:

| `num_ctx` | Placement | VRAM (total, incl. desktop) | Generation |
|---:|---|---:|---:|
| 32 768 (current) | 100% GPU | 13 615 MiB | 91.7 tok/s |
| 65 536 | 100% GPU | 14 085 MiB | 87.6 tok/s |
| 131 072 | **11% CPU / 89% GPU** | 14 821 MiB | 80.1 tok/s |

**64k is the practical ceiling on this card** — doubling the window costs only ~470 MiB thanks to
the q8_0 KV cache, and stays fully on the GPU. 128k spills 11% of the model to CPU and gives up
~13% of generation speed. To change it, recreate the tag (seconds, reuses existing weight layers):

```fish
printf 'FROM gpt-oss:20b\nPARAMETER num_ctx 65536\n' > /tmp/Modelfile
ollama create gpt-oss-agent-64k -f /tmp/Modelfile
```

### Layer 3 — what opencode spends it on

**opencode's own scaffolding costs ~6.3–6.8k tokens before you type anything** — its system
prompt plus the full schemas for `bash`, `edit`, `glob`, `grep`, `read`, `write`, `todowrite`,
`task`, `skill`, `webfetch`. Measured on a bare `"say hi"`:

```json
{"total": 6833, "input": 6774, "output": 59, "reasoning": 0}
```

So of a 32 768-token window, roughly **21% is gone at session start**, leaving ~26k for the
conversation, file contents and tool output. A couple of large file reads consume it quickly.

When it fills, opencode **auto-compacts** — it summarises the conversation so far and continues
(`compactAfterOverflow`; disable with `OPENCODE_DISABLE_AUTOCOMPACT=1`). Compaction is lossy: the
model keeps a summary, not the transcript. For long sessions this is the practical limit on
"memory", not the token count.

**Practical implications**

- Start a fresh session per task rather than one long-running one. Compaction loses detail, and a
  fresh session costs only the ~6.5k baseline.
- `AGENTS.md` is prepended to every session, so keep it short — it is charged against the window
  each time.
- If you routinely hit compaction, move to a 64k tag before anything else. It is nearly free.

---

## Keeping it local — it phones home by default

**opencode contacts `api.opencode.ai` on every run, even with a purely local model.** Observed
directly: a run using only `ollama/gpt-oss-agent-32k` opened a TLS connection to `104.20.32.17:443`,
which is in `api.opencode.ai`'s A records. It is syncing a provider/model catalog it does not need
here — our Ollama provider is defined locally in `opencode.json`, and a Modelfile tag like
`gpt-oss-agent-32k` does not exist in any public catalog.

Setting `"autoupdate": false` and `"share": "disabled"` in the config is **not** enough — the
connection still happens. The switch that stops it is an environment variable:

```fish
set -Ux OPENCODE_DISABLE_MODELS_FETCH 1
set -Ux OPENCODE_DISABLE_AUTOUPDATE 1
```

**Set it in three places — the fish universal variable alone is not enough.** Fish universals
exist only inside fish, so anything launched from the desktop (VS Code from the app menu, a
non-fish terminal) never sees them, and opencode goes on fetching.

1. **`~/.config/environment.d/opencode.conf`** — the systemd *user* environment, which applies to
   the whole graphical session including desktop-launched apps. This is the one that actually
   closes the hole. **Takes effect at next login**; to apply it to the running session without
   logging out, `systemctl --user import-environment OPENCODE_DISABLE_MODELS_FETCH OPENCODE_DISABLE_AUTOUPDATE`.

   ```
   OPENCODE_DISABLE_MODELS_FETCH=1
   OPENCODE_DISABLE_AUTOUPDATE=1
   ```

2. **fish universal variables** (`set -Ux …`) — covers interactive shells immediately, including
   sessions already open.

3. **VS Code `settings.json`** under `terminal.integrated.env.linux` — belt and braces for the
   extension's terminal whatever shell it launches:

   ```json
   "terminal.integrated.env.linux": {
     "OPENCODE_DISABLE_MODELS_FETCH": "1",
     "OPENCODE_DISABLE_AUTOUPDATE": "1"
   }
   ```

### Verifying it, properly

⚠️ **A warm cache will fool you.** The catalog is cached at `~/.cache/opencode/models.json`
(~4.3 MB) and only re-fetched when missing or stale, so "no connections observed" proves nothing
if that file already exists. Delete it first, and run a positive control:

```fish
rm -f ~/.cache/opencode/models.json
# control - genuinely unset, not set-to-empty (empty still counts as "set")
env -u OPENCODE_DISABLE_MODELS_FETCH opencode run -m ollama/gpt-oss-agent-32k "say hi"
```

Measured this way:

| Condition (cache deleted first) | Connection | `models.json` after |
|---|---|---|
| flag **unset** (control) | `104.20.32.17:443` | re-downloaded, 4.3 MB |
| flag **set** | none | stays absent |

With the flag set and no catalog on disk at all: the TUI and `opencode run` both stay offline,
`opencode models ollama` still lists all four local models, and a real edit task completes
(`fib(10) = 55`, TODO removed).

**Does disabling the catalog hurt quality?** No. A first sample suggested it might (0/3 vs 3/3),
but that was run-to-run variance — a second sample gave 2/3 with it enabled, matching 2/3 without.
Confirmed there is no mechanism: opencode's resolved model metadata is byte-identical with the
fetch on and off (`llm.provider=ollama llm.model=gpt-oss-agent-32k` both ways), because a local
Modelfile tag under a user-defined provider was never in the catalog to begin with.

Other `OPENCODE_DISABLE_*` variables exist (`_SHARE`, `_LSP_DOWNLOAD`, `_DEFAULT_PLUGINS`,
`_EXTERNAL_SKILLS`, …) — read the full list with
`strings (readlink -f (which opencode)) | grep -oE 'OPENCODE_[A-Z_]+' | sort -u`. Disabling the
models fetch alone was sufficient to silence all outbound traffic.

---

## VS Code

The extension is **`sst-dev.opencode`** (v0.0.13 installed). It is a thin wrapper — it opens the
opencode TUI inside a VS Code terminal, so everything above (model, `AGENTS.md`, permissions)
applies unchanged. There are no extension settings to configure.

```fish
code --install-extension sst-dev.opencode    # if not already present
```

| Shortcut (Linux) | Command | Does |
|---|---|---|
| `ctrl+escape` | `opencode.openTerminal` | open opencode in a terminal panel |
| `ctrl+shift+escape` | `opencode.openNewTerminal` | open it in a new tab |
| `ctrl+alt+K` | `opencode.addFilepathToTerminal` | insert the current file as an `@`-mention |

The extension ships correct Linux keybindings (its `key` field shows `cmd+…`, but `linux` variants
are defined), so nothing needs remapping. `ctrl+alt+K` is the one worth learning — it puts the file
you're looking at into the prompt without typing the path, which also sidesteps the hallucinated-path
problem entirely.

If `ctrl+shift+escape` doesn't fire, it's being grabbed by the desktop — rebind it in
**Keyboard Shortcuts** (`ctrl+K ctrl+S`).

A useful companion binding already present in `~/.config/Code/User/keybindings.json` sends
`shift+enter` as escape+CR in the terminal, which the TUI uses for multi-line input.

**Run it from an ordinary project directory** — not a deeply nested temp/scratch path.

**VRAM note:** same constraint as everything else on this GPU — opencode's model and ComfyUI/other
Ollama models can't be resident simultaneously. `systemctl --user stop ollama` when done to release
the ~14.6 GiB.

---

## Verified working — 2026-08-27, after the AGENTS.md fix

```
$ opencode run -m ollama/gpt-oss-agent-32k \
    "Use the bash tool to run: python3 -c \"print(6*7)\" and tell me the output."
> build · gpt-oss-agent-32k
$ python3 -c "print(6*7)"
42
```

Edit task, `--format json`, repeated runs against the same `fib.py` stub:

| Check | Result |
|---|---|
| Hallucinated absolute paths | **0** across all runs after `AGENTS.md` |
| Produces syntactically valid Python | 3/3 on a precise prompt |
| `fib(10) == 55` | 3/3 on a precise prompt |
| Same task, vaguer prompt | 2/4 — one run left the `TODO` in place, one produced bad indentation |

**Prompt precision matters more than it should.** "Edit fib.py so fib(n) returns the nth Fibonacci
number iteratively" was noticeably less reliable than "Replace the body of fib in fib.py with an
iterative implementation. Remove the TODO." Both are clear to a human; only the second was reliable
with a 20B model at Q4. Say exactly which construct to change and what to remove.

**Always review the diff.** This is a local 20B model, not a frontier one — it succeeds often
enough to be useful and fails often enough that unreviewed commits would be a mistake. Working in a
git repo so `git diff` shows what it did is the practical safeguard.

## Earlier transcript (2026-08-26)

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
