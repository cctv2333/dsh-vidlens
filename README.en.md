# VidLens for DeepSeek Harness

[中文](README.md) · **English**

[![ci](https://github.com/cctv2333/dsh-vidlens/actions/workflows/ci.yml/badge.svg)](https://github.com/cctv2333/dsh-vidlens/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/dsh-vidlens.svg)](https://www.npmjs.com/package/dsh-vidlens)
[![PyPI](https://img.shields.io/pypi/v/vidlens-mcp.svg?cacheSeconds=600)](https://pypi.org/project/vidlens-mcp/)
[![DSH plugin](https://img.shields.io/badge/topic-dsh--plugin-4B5563)](https://github.com/topics/dsh-plugin)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Native **video evidence** tools for DeepSeek Harness. Point it at a public link — or a local
file — and get something a model can actually read: timecoded lines, timecoded pictures, sound
classes, comment signals. 21 tools, no cloud API, no vision model, no GPU, no telemetry.

The Python engine is a separate package: [vidlens](https://github.com/cctv2333/vidlens)
(`pip install vidlens-mcp`). This repository is only the DSH plugin plus its long-lived bridge.

## What this plugin adds over the plain MCP shell

| Capability | MCP shell | This plugin |
|---|---|---|
| Tool names | `mcp__vidlens__video_meta` | `vidlens_meta` (short, readable) |
| Timeouts | one global 60s per client | per-tool budgets (`vidlens_brief` 15 min, `vidlens_scan` 15 min) |
| Images | depends on client support for MCP image content | goes through the host's `attachments.saveImage`, so it becomes a **persistent image attachment** you can look at in the same turn |
| Cache awareness | none | `vidlens_library` (list cache, zero network), `vidlens_seek` (find a quote, zero network) |
| Batch triage | none | `vidlens_compare` (up to 8 links, 0 media bytes) |
| Behaviour | MCP instructions only | its own system-prompt section: meta → plan → sample, never download the whole film |
| Cancellation | drop the connection | `exec.signal` restarts the bridge process, leaving no stuck downloads |
| Whole-file download | `video_full(confirm=true)` exists | **deliberately absent**: use sheet/frames/scan for picture |
| Local files | same Python core (since 1.6.0) | every `url` argument accepts a local path: `D:\a.mp4`, `file:///D:/a.mp4`, `~/a.mov` |

## Install

**First, get the vidlens core.** Either:

```bash
pipx install "vidlens-mcp[all]"          # recommended: no checkout; commands are vidlens / vidlens-mcp
# or
git clone https://github.com/cctv2333/vidlens && cd vidlens && install.cmd
```

Then install this plugin (pick one):

```powershell
# A. Local directory (development; point at your own clone)
plugin_manager action=install_bundle target=<your path>\dsh-vidlens

# B. Straight from GitHub (no build/prepare script, so no allowBuilds permission needed)
#    Note: this really does `git clone`, and GitHub will count it as one clone
dsh plugin --profile desktop add github:cctv2333/dsh-vidlens#<sha>

# C. npm (registry, does not touch GitHub)
dsh plugin --profile desktop add dsh-vidlens
```

The plugin finds the Python project itself: `config.projectDir` → `$VIDLENS_PROJECT` →
`<this package>/../vidlens` → the current directory (only directories that actually exist;
no personal paths are baked in). Python is resolved as `$VIDLENS_PYTHON` → that project's
`.venv` → `python`. With a PyPI install, either point `projectDir` at the pipx venv or set
`VIDLENS_PROJECT` — the module name does not change.

Installing the bundle inserts one Host plugin entry:

```yaml
- insert:
    - id: dsh-vidlens
      name: 'dsh-vidlens'
      config: {}
```

Override paths per machine:

```yaml
- insert:
    - id: dsh-vidlens
      name: 'dsh-vidlens'
      config:
        projectDir: D:\path\to\vidlens
        pythonPath: D:\path\to\vidlens\.venv\Scripts\python.exe
        warm: true
```

## Tools (21)

`url` accepts a public link **or a local path**.

**Basics (0 download)**

| Tool | Purpose |
|---|---|
| `vidlens_meta(url)` | title / channel / duration / views / platform subtitles / platform BGM + injection risk scan |
| `vidlens_plan(url, window=300)` | chapters from shot cuts and long silences, plus a viewing order |
| `vidlens_subs(url, lang=zh)` | platform subtitles (human over auto/AI) |
| `vidlens_library(limit=20, query='')` | **added**: what is already cached, so nothing is downloaded twice |

**Reading content**

| Tool | Downloads | Purpose |
|---|---|---|
| `vidlens_watch(url, minutes=5, cursor="next")` | that segment's audio (or cache) | **added**: watch in segments (5 min ≈ 0.5k chars), returns the section plus "watched X / of Y (%)" and asks before continuing |
| `vidlens_window(url, start, end)` | 0 (cache/subtitles) or that window's audio | transcript and pauses for one window |
| `vidlens_brief(url, ..., level="digest")` | subtitles 0; audio only when there are none | **digest** (~1.5k chars: chapters + 5 key lines + path to the full report); `level="full"` for the 6–9k report |
| `vidlens_seek(query, url='')` | 0 | **added**: search cached transcripts for a phrase, return absolute timecodes |
| `vidlens_audio(url, start, end)` | that segment's audio | SenseVoice language/emotion/event + beat and energy |
| `vidlens_soundscape(url, start, end)` | that segment's audio | **added**: AudioSet's 527 sound classes + probability + timecode |

**Picture (images land in the conversation)**

| Tool | Downloads | Purpose |
|---|---|---|
| `vidlens_sheet(url, start, end, cols, rows)` | that segment (20 s ≈ 0.9MB) | contact sheet with absolute timecodes |
| `vidlens_frames(url, at=[...])` | that segment | up to 6 exact frames (for reading small text) |
| `vidlens_scan(url, n=24)` | lowest-quality whole file (7 min ≈ 14–21MB, deleted after) | sampled sheets across the film |
| `vidlens_ocr(url, start, end, n=12)` | lowest quality of that range | **read on-screen text into text** (local OCR, offline); the workhorse for videos with no speech and no subtitles |

OCR is an optional extra (RapidOCR, Apache-2.0, PP-OCRv6 models shipped inside the wheel, fully
offline once installed). **The first call does not download in secret**: it reports the size,
the target directory and how to change it; call again with `install: true` to proceed, and the
result states where it went. Not installing it breaks nothing.

| Variable | Effect | Default |
|---|---|---|
| `VIDLENS_OCR_TARGET` | install here (added to the import path, never into system dirs) | this interpreter's `site-packages` (usually **C:** on Windows) |
| `VIDLENS_OCR_AUTO_INSTALL` | `ask` / `auto` / `off` | `ask` |

**Judging / long videos / self-check**

| Tool | Purpose |
|---|---|
| `vidlens_comments(url, limit=40)` | engagement ratio, sentiment, controversy, top comments (+ optional images) |
| `vidlens_compare(urls=[...])` | **added**: metadata comparison for up to 8 links, 0 media bytes |
| `vidlens_job_start(url, ..., full=False)` | background job for long videos, returns `job_id` immediately |
| `vidlens_job(job_id, wait_seconds=20)` | poll phase/percentage, then the report |
| `vidlens_models(action=list)` | local model dirs with real paths; `action=download, name=..., confirm=true` to fetch (ced-mini 10MB / whisper 75–484MB) |
| `vidlens_doctor()` | self-check: python / ffmpeg / yt-dlp / extras / models / disk / network |

## Context budget (why the default is a digest)

Measured, the old "watch a video" path cost this many characters:

| Call | Chars | Note |
|---|---|---|
| `meta` + `plan` | ~730 | cheap |
| `window` × 3 (one minute each) | ~2,800 | ~0.9k per minute |
| `soundscape` (60 s) | ~1,500 | 12 windows × 8 labels |
| `brief` (old full report) | **~9,000** | 6–9k chars ≈ 4–6k tokens |
| total | **~14,200** | images not included |

The problem is not one call, it is that **all of it stays in context for every later turn**.
In a 64k window, two or three videos plus a normal conversation hits the ceiling — the
"after watching the video I'm already out of context" failure.

So the default is three tiers, upgraded on demand:

1. `vidlens_brief` → **digest** (~0.7–1.5k chars: title/duration/speech coverage/chapters/
   5 evenly sampled key lines/path to the full report);
2. `vidlens_window` → one segment only (~0.8k chars per minute); use it for detail, not `brief`;
3. `vidlens_brief(level="full")` → the full 6–9k report, **only** when the user asks for it.

The full text is always written to `out/<id>/brief.md`, and the digest carries the path plus
what to call next. `vidlens_window` is capped at 80 lines and says "there are N more lines,
narrow the range" instead of flooding the context.

## Architecture

```
DSH Host (index.js)
  ├─ 21 × ctx.tools.register(...)        native tools + per-tool timeoutMs
  ├─ ctx.systemPrompt.section('vidlens') the sampling protocol (meta -> plan -> sample)
  └─ Bridge (long-lived) ──stdin/stdout JSONL──▶ python -u bridge/vidlens_bridge.py
                                                  │
                                                  ├─ import vl_mcp      (reuse the tool functions)
                                                  ├─ import vidlens_web / _extra / _sanitize
                                                  └─ out/<id>/          (cache, survives restarts)
```

**Why not just attach the MCP server**: an MCP client only has one global tool timeout, so a
long ASR pass gets killed as a failure; whether images reach the model depends on the client;
and "what is cached / where a phrase was said" can only be answered locally. The bridge joins
the already-verified Python logic with the host's native abilities without rewriting either side.

**Protocol** (one JSON per line)

```jsonc
// boot
{"op":"ready","ok":true,"pid":1234,"project":"D:\\projects\\vidlens","python":"3.12.10","tools":["meta",...]}
// request -> response
{"id":7,"tool":"sheet","args":{"url":"...","start":"0","end":"20"}}
{"id":7,"ok":true,"text":"...","images":[{"path":"...jpg","mediaType":"image/jpeg","name":"sheet_0_20000.jpg"}]}
{"id":8,"ok":false,"error":"ValueError: ...","trace":"..."}
```

`sys.stdout` is redirected to stderr *before* any library import, so stray `print` calls inside
dependencies cannot corrupt the protocol; the bridge writes frames only to the saved real stdout.

**Multi-process safety**: a DSH session, an MCP server and a plugin bridge are **different
processes**, and an in-process `threading.Lock` cannot see across them. The core provides
`vidlens_web.CrossProcessLock` (in-process RLock + an `out/.media.lock` file lock via
msvcrt/flock), extending the single download mouth to the whole machine. Timeout is tunable
with `VIDLENS_LOCK_TIMEOUT` (default 900s). Measured with two processes calling `video_sheet`
at once: the second acquires only after the first finishes — serialized, no collision.

## Verification

**Offline (no network, no media)**

```powershell
node tools/selftest.mjs
# 130/130 checks passed (tool table + bridge handshake + library/models/seek
#                        + local-path declarations + self-heal after a forced kill)
```

**With the real pipeline (~1MB of media)**

```powershell
node tools/selftest.mjs --live
# 130/130 plus 3 live checks
```

## License

MIT. The engine is [vidlens](https://github.com/cctv2333/vidlens) (MIT) with its own
attribution file for third-party components and models.
