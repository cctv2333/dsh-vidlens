#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vidlens bridge — newline-delimited JSON worker used by the DSH vidlens plugin.

Why a bridge instead of the MCP server
--------------------------------------
* It reuses the already-tested ``vl_mcp`` tool bodies verbatim. No second copy of
  the video logic exists, so behaviour cannot drift between the MCP shell and the
  plugin.
* The process stays warm: model weights, the ffmpeg shim and the ``out/`` cache
  survive between tool calls.
* stdout carries protocol frames only. ``sys.stdout`` is pointed at stderr before
  any library is imported, so a stray ``print`` from a dependency can never
  corrupt the protocol.

Protocol
--------
in : {"id": 1, "tool": "meta", "args": {"url": "..."}}
out: {"id": 1, "ok": true,  "text": "...", "images": [{"path": "...", "mediaType": "image/jpeg", "name": "..."}]}
     {"id": 1, "ok": false, "error": "TypeError: ...", "trace": "..."}
boot: {"op": "ready", "ok": true, "pid": 1234, "project": "...", "python": "3.12.10"}

Ops : {"op": "shutdown"}

Every request is handled in order on one thread. The underlying library already
serialises media work with its own locks, so the bridge adds no scheduling
policy of its own.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

# ------------------------------------------------------------------ protocol fd
PROTO = sys.stdout
try:  # keep frames UTF-8 regardless of the Windows console code page
    PROTO.reconfigure(encoding="utf-8", newline="\n")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - very old / exotic stdout
    pass
sys.stdout = sys.stderr  # stray prints from libraries must not corrupt the protocol


def _send(obj) -> None:
    try:
        PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
        PROTO.flush()
    except Exception:  # pragma: no cover - the host may be gone already
        pass


# ------------------------------------------------------------- project discovery
HERE = Path(__file__).resolve().parent
BRIDGE_VERSION = "1.0.0"


def _find_project() -> Path:
    cands = []
    env = os.environ.get("VIDLENS_PROJECT")
    if env:
        cands.append(Path(env).expanduser())
    cands.append(HERE.parent.parent / "vidlens")  # <plugin>/../vidlens
    cands.append(Path.cwd())
    for c in cands:
        try:
            if (c / "vidlens.py").exists():
                return c
        except OSError:
            continue
    return Path.cwd()


PROJECT = _find_project()
try:
    os.chdir(str(PROJECT))
except OSError:
    pass
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
# The bridge turns `Image` objects into file paths (see `_image_entry`), so a
# large sheet costs the plugin nothing. Say so, or vl_mcp's `auto` policy would
# drop the picture here and the tool would return a path with no attachment.
os.environ.setdefault("VIDLENS_INLINE_IMAGES", "always")
# This surface exposes vidlens_* names; core text must not say video_* (R-3).
os.environ.setdefault("VIDLENS_TOOL_PREFIX", "vidlens_")

# ---------------------------------------------------------------------- imports
IMPORT_ERROR = None
core = extra = S = web = vl = None
MCPImage = None
try:
    import vidlens as core  # noqa: F401
    import vidlens_extra as extra  # noqa: F401
    import vidlens_sanitize as S  # noqa: F401
    import vidlens_web as web  # noqa: F401
    import vl_mcp as vl  # noqa: F401
    from mcp.server.mcpserver import Image as MCPImage  # noqa: F401
except BaseException as exc:  # noqa: BLE001 - report, never crash the loop
    IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
    traceback.print_exc(file=sys.stderr)

_INSTALL_HINT = (
    "vidlens 依赖没法导入。两种修法（任选一种）：\n"
    "  1) pip install vidlens-mcp —— 然后让插件用同一个解释器：\n"
    "     插件配置项 pythonPath，或环境变量 VIDLENS_PYTHON。\n"
    "  2) 用已有的 checkout：把 VIDLENS_PROJECT 设成含 vidlens.py 的目录。\n"
    "     本进程已经找过: {project}"
)


def _import_error_text() -> str:
    """Turn a bare ImportError into something the user can act on.

    The raw traceback goes to stderr (visible in the bridge log); what reaches the
    model is the failure plus the two ways to fix it. Without this the whole plugin
    answers every call with ``No module named 'vidlens'`` and no lead on why.
    """
    err = IMPORT_ERROR or ""
    hint = _INSTALL_HINT.format(project=PROJECT)
    match = re.search(r"No module named '([^']+)'", err)
    if not match:
        return f"{err}\n\n{hint}"
    missing = match.group(1).split(".")[0]
    if missing == "mcp":
        pip = "pip install mcp"
    elif missing in ("vl_mcp",) or missing.startswith("vidlens"):
        pip = "pip install vidlens-mcp"
    else:
        pip = f"pip install {missing}"
    return f"{err}\n\n缺 Python 包 {missing}。先试：{pip}\n{hint}"


# ---------------------------------------------------------------- result shaping
_EXT_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
MAX_IMAGES = 6


def _image_entry(im):
    p = getattr(im, "path", None)
    if p is None:
        return None
    p = Path(p)
    if not p.exists() or not p.is_file():
        return None
    return {
        "path": str(p),
        "mediaType": _EXT_MEDIA.get(p.suffix.lower(), "image/jpeg"),
        "name": p.name,
    }


def _normalize(res):
    """(text, images) — mirrors what the MCP tools returned, images as files."""
    texts: list[str] = []
    images: list[dict] = []

    def walk(x):
        if x is None:
            return
        if isinstance(x, str):
            if x.strip():
                texts.append(x)
            return
        if MCPImage is not None and isinstance(x, MCPImage):
            entry = _image_entry(x)
            if entry:
                images.append(entry)
            return
        if isinstance(x, (list, tuple)):
            for item in x:
                walk(item)
            return
        if isinstance(x, dict):
            texts.append(json.dumps(x, ensure_ascii=False))
            return
        texts.append(str(x))

    walk(res)
    return "\n".join(texts).strip(), images


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _transcript_rows(d: Path) -> list[dict]:
    p = d / "transcript.jsonl"
    if not p.exists():
        return []
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows


def _cache_dirs() -> list[Path]:
    root = web.out_root()
    if not root.exists():
        return []
    return [d for d in root.iterdir() if d.is_dir()]


_BVID = re.compile(r"(BV[0-9A-Za-z]{10})")


def _ident_of(url: str) -> str:
    url = (url or "").strip()
    m = _BVID.search(url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]v=([\w-]{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([\w-]{6,})", url)
    if m:
        return m.group(1)
    tail = url.rstrip("/").split("/")[-1]
    return tail.split("?")[0].split("#")[0] or url


def _dir_for_url(url: str):
    ident = _ident_of(url)
    if not ident:
        return None
    dirs = _cache_dirs()
    low = ident.lower()
    for d in dirs:
        if d.name.lower() == low:
            return d
    for d in dirs:  # multi-part uploads: BV1xx_p1, BV1xx_p2 ...
        if d.name.lower().startswith(low + "_"):
            return d
    # A local file gets an id like `local-<stem>-<sha1>`, so `D:\a.mp4` must also
    # match on the stem -- otherwise `vidlens_seek` cannot find the transcript that
    # `vidlens_brief` just wrote for the very same file.
    stem = os.path.splitext(os.path.basename(url.rstrip("\\/")))[0]
    stem = re.sub(r"[^\w.-]+", "-", stem.strip()).strip("-._").lower()
    if stem and os.path.isfile(url):
        for d in dirs:
            if d.name.lower().startswith(f"local-{stem}-"):
                return d
    return None


# ------------------------------------------------------------------ extra tools
# These three are the plugin's additions over the MCP shell. All of them work on
# local cache or on metadata only: zero media bytes.

def tool_library(args: dict) -> str:
    """List what is already cached under out/ (no network at all)."""
    limit = _clamp(args.get("limit"), 1, 100, 20)
    query = (args.get("query") or "").strip().lower()
    root = web.out_root()
    dirs = _cache_dirs()
    if not dirs:
        return f"# 本地缓存为空\n\n目录: {root}\n\n先用 `vidlens_meta` / `vidlens_plan` 处理一个链接。"

    entries = []
    for d in dirs:
        # out/ also holds scratch dirs (bili/, comment_pics/); only real video
        # caches carry metadata or a transcript.
        if not (d / "meta.json").exists() and not (d / "transcript.jsonl").exists():
            continue
        payload = _read_json(d / "meta.json", {}) or {}
        meta = (payload.get("meta") if isinstance(payload, dict) else None) or {}
        title = str(meta.get("title") or "").strip()
        if query and query not in (title + " " + d.name).lower():
            continue
        rows = _transcript_rows(d)
        info = _read_json(d / "speech_info.json", {}) or {}
        try:
            size_mb = round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1048576, 2)
            mtime = d.stat().st_mtime
        except Exception:
            size_mb, mtime = 0.0, 0.0
        entries.append({
            "id": d.name,
            "title": title or "(无标题)",
            "duration": float(meta.get("duration") or 0),
            "uploader": str(meta.get("uploader") or "").strip(),
            "source": str(info.get("source") or ""),
            "lines": len(rows),
            "brief": (d / "brief.md").exists(),
            "sheets": len(list(d.glob("sheet_*"))) + len(list(d.glob("visual_*"))),
            "frames": len(list((d / "frames").glob("*.jpg"))) if (d / "frames").exists() else 0,
            "mb": size_mb,
            "mtime": mtime,
        })

    if not entries:
        suffix = f"（query={query!r} 没有匹配）" if query else ""
        return f"# 本地缓存没有匹配项{suffix}\n\n目录: {root}"

    entries.sort(key=lambda e: -e["mtime"])
    shown = entries[:limit]
    total_mb = round(sum(e["mb"] for e in entries), 1)
    # The cache grows by design and nothing prunes it automatically: say how big it
    # is here, where people actually look, instead of only in `vidlens_doctor`.
    out = [f"# 本地缓存 {len(entries)} 个视频（显示 {len(shown)}），共 {total_mb} MB",
           "", f"目录: {root}",
           f"清理: `vl clean --days 7`（默认只删媒体，保留 brief.md）", ""]
    for e in shown:
        flags = []
        if e["brief"]:
            flags.append("brief")
        if e["sheets"]:
            flags.append(f"拼图×{e['sheets']}")
        if e["frames"]:
            flags.append(f"帧×{e['frames']}")
        # A cache dir can be a leftover: no meta, no transcript, 0 bytes. Saying so
        # here is cheaper than a caller wondering why "19 个视频" includes 2 duds (R-4).
        if not e["lines"]:
            flags.append("⚠无转写")
        if not e.get("title"):
            flags.append("⚠无元数据")
        if not e["mb"]:
            flags.append("⚠空目录")
        meta_bits = [core.hms(e["duration"])]
        if e["lines"]:
            meta_bits.append(f"{e['lines']} 段")
        if e["source"]:
            meta_bits.append(e["source"])
        meta_bits.append(f"{e['mb']}MB")
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["mtime"])) if e["mtime"] else "?"
        out.append(f"- `{e['id']}` · " + " · ".join(meta_bits) + (" · " + " / ".join(flags) if flags else ""))
        out.append(f"    {e['title']}    ({when})")
    if len(entries) > len(shown):
        out += ["", f"- …另有 {len(entries) - len(shown)} 个（用 limit 调大）"]
    out += ["", "下一步：`vidlens_seek(query=...)` 在缓存里找原话；要看画面用原链接 + "
                "`vidlens_sheet`。这些复盘动作全部零网络。"]
    return "\n".join(out)


def tool_seek(args: dict) -> str:
    """Search cached transcripts for a phrase; return absolute timecodes."""
    query = str(args.get("query") or "").strip()
    if not query:
        return "ERROR: 请给 query（要查的关键词或原话片段）"
    limit = _clamp(args.get("limit"), 1, 100, 20)
    url = str(args.get("url") or "").strip()

    if url:
        d = _dir_for_url(url)
        if d is None:
            return (f"ERROR: 缓存里没有这个视频（{_ident_of(url)}）。\n"
                    "先用 `vidlens_brief` 或 `vidlens_window` 处理一次，再用 `vidlens_seek`。")
        dirs = [d]
    else:
        dirs = _cache_dirs()

    needle = query.lower()
    hits = []
    scanned = 0
    for d in dirs:
        rows = _transcript_rows(d)
        if not rows:
            continue
        scanned += 1
        for r in rows:
            text = r.get("text") or ""
            if needle in text.lower():
                hits.append((d.name, float(r.get("t0") or 0), text))
    if not hits:
        scope = f"视频 {dirs[0].name}" if url else f"{scanned} 个有转写的视频"
        return f"# 没查到 {query!r}\n\n已扫描 {scope}；可能是用词不同，或该视频还没有转写（先 `vidlens_brief`）。"
    hits.sort(key=lambda h: (h[0], h[1]))
    out = [f"# 缓存里 {len(hits)} 条匹配 {query!r}", ""]
    for vid, t0, text in hits[:limit]:
        out.append(f"- `{vid}` `{core.hms(t0)}` {S.clean(text, 240)}")
    if len(hits) > limit:
        out.append(f"- …另有 {len(hits) - limit} 条（用 limit 调大）")
    out += ["", "核对建议：拿到时间码后用 `vidlens_window` 取上下文，`vidlens_sheet` 看那一秒的画面。"]
    return "\n".join(out)


def tool_compare(args: dict) -> str:
    """Metadata for several URLs at once, zero media bytes."""
    urls = args.get("urls")
    if isinstance(urls, str):
        urls = [u for u in re.split(r"[\s,]+", urls) if u.strip()]
    if not isinstance(urls, list):
        urls = []
    urls = [str(u).strip() for u in urls if str(u).strip()][:8]
    if not urls:
        return "ERROR: urls 至少给一个链接（最多 8 个）"

    out = ["# 批量元数据（每个链接 0 媒体下载）", "",
           "| # | id | 时长 | 字幕 | 播放 | 标题 |", "|---|---|---|---|---|---|"]
    problems = []
    for i, u in enumerate(urls, 1):
        try:
            meta, _threats = web.fetch_meta(u)
        except BaseException as exc:  # noqa: BLE001 - SystemExit is used for user-facing stops
            problems.append(f"- `{u}` → {type(exc).__name__}: {exc}")
            out.append(f"| {i} | — | — | — | — | （取不到，见下） |")
            continue
        dur = core.hms(float(meta.get("duration") or 0))
        subs = len(meta.get("has_subs") or [])
        auto = len(meta.get("has_auto_subs") or [])
        sub_txt = f"人工{subs}/自动{auto}" if (subs or auto) else "无"
        cached = "✓" if _dir_for_url(u) else ""
        title = str(meta.get("title") or "").replace("|", "\\|").strip()
        views = meta.get("view_count")
        out.append(f"| {i} | {meta.get('id')} {cached} | {dur} | {sub_txt} | {views} | {title} |")
    if problems:
        out += ["", "## 取不到"] + problems
    out += ["", "下一步：挑 1-2 个用 `vidlens_plan` 拿章节，再 `vidlens_window` / `vidlens_sheet` 取样。"]
    return "\n".join(out)


# ------------------------------------------------------------------- dispatching
# ("kwargs", fn) -> fn(**filtered_args)   ("dict", fn) -> fn(args)
DISPATCH: dict[str, tuple[str, object]] = {}


def _install_dispatch() -> None:
    if IMPORT_ERROR:
        return
    kwargs_tools = {
        "meta": vl.video_meta,
        "plan": vl.video_plan,
        "subs": vl.video_subs,
        "brief": vl.video_brief,
        "window": vl.video_window,
        "watch": vl.video_watch,
        "audio": vl.video_audio,
        "soundscape": vl.video_soundscape,
        "sheet": vl.video_sheet,
        "frames": vl.video_frames,
        "scan": vl.video_visual_scan,
        "ocr": vl.video_ocr,
        "comments": vl.video_comments,
        "job_start": vl.video_job_start,
        "job": vl.video_job,
        "models": vl.vidlens_models,
        "doctor": vl.vidlens_doctor,
    }
    for name, fn in kwargs_tools.items():
        DISPATCH[name] = ("kwargs", fn)
    DISPATCH["library"] = ("dict", tool_library)
    DISPATCH["seek"] = ("dict", tool_seek)
    DISPATCH["compare"] = ("dict", tool_compare)


_install_dispatch()


def _handle(req: dict) -> dict:
    if IMPORT_ERROR:
        raise RuntimeError("vidlens 依赖导入失败: " + _import_error_text())
    tool = str(req.get("tool") or "")
    entry = DISPATCH.get(tool)
    if entry is None:
        raise KeyError(f"未知工具 {tool!r}（可用: {', '.join(sorted(DISPATCH))}）")
    mode, fn = entry
    args = req.get("args") or {}
    if not isinstance(args, dict):
        raise TypeError("args 必须是对象")
    if mode == "dict":
        res = fn(args)
    else:
        sig = inspect.signature(fn)
        kwargs = {k: v for k, v in args.items() if k in sig.parameters}
        res = fn(**kwargs)
    text, images = _normalize(res)
    # vl_mcp truncates the brief at MAX_BRIEF_CHARS and then appends the saved
    # path; a caller that stops reading there has no idea content was cut.
    if tool == "brief" and len(text) >= int(getattr(vl, "MAX_BRIEF_CHARS", 9000)):
        text += ("\n\n[注意] 上面的报告已按 "
                 + str(getattr(vl, "MAX_BRIEF_CHARS", 9000))
                 + " 字截断；全文在结果末尾的 brief.md 里。"
                 "要某段细节用 vidlens_window（读台词）或 vidlens_seek（定位原话）。")
    return {"ok": True, "text": text, "images": images[:MAX_IMAGES]}


def main() -> int:
    _send({
        "op": "ready",
        "ok": IMPORT_ERROR is None,
        "pid": os.getpid(),
        "bridge": BRIDGE_VERSION,
        "project": str(PROJECT),
        "python": sys.version.split()[0],
        "tools": sorted(DISPATCH),
        "error": _import_error_text() if IMPORT_ERROR else None,
    })
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            _send({"id": None, "ok": False, "error": f"bad json: {exc}"})
            continue
        if req.get("op") == "shutdown":
            break
        rid = req.get("id")
        started = time.time()
        try:
            payload = _handle(req)
            payload["id"] = rid
            payload["ms"] = int((time.time() - started) * 1000)
            _send(payload)
        except BaseException as exc:  # noqa: BLE001 - SystemExit is a normal stop path here
            _send({
                "id": rid,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-1500:],
                "ms": int((time.time() - started) * 1000),
            })
    return 0


if __name__ == "__main__":
    sys.exit(main())
