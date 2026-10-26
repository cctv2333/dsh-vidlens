#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch the CED-mini audio-tagging model used by vidlens sound events.

Downloads two files (~10.4 MB + 14.7 KB) from Hugging Face:

    model.int8.onnx            int8 CED-mini, AudioSet 527 classes
    class_labels_indices.csv   the AudioSet label table

Destination (override with VIDLENS_TAGGING_DIR / --dir):

    <root>/audio-tagging/ced-mini/

Nothing else is downloaded, no torch, no onnxruntime plumbing: sherpa-onnx does
the feature extraction and inference.

    python tools/fetch_sound_model.py            # download
    python tools/fetch_sound_model.py --check    # only report what is present
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = "k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19"
BASE = f"https://huggingface.co/{REPO}/resolve/main"
MIRROR = f"https://hf-mirror.com/{REPO}/resolve/main"
FILES = ("model.int8.onnx", "class_labels_indices.csv")


def default_dir() -> Path:
    """Same rule as vidlens.models_root(), without importing the project.

    The legacy `D:\\dev\\models` is a candidate only if it exists: on anybody
    else's machine that directory is not theirs to write into.
    """
    env = os.environ.get("VIDLENS_TAGGING_DIR")
    if env:
        return Path(env).expanduser()
    root = os.environ.get("VIDLENS_MODEL_ROOT")
    if root:
        base = Path(root).expanduser()
    else:
        legacy = Path(r"D:\dev\models")
        if legacy.is_dir():
            base = legacy
        elif os.name == "nt":
            base = (Path(os.environ.get("LOCALAPPDATA")
                         or (Path.home() / "AppData" / "Local")) / "vidlens" / "models")
        else:
            base = (Path(os.environ.get("XDG_DATA_HOME")
                         or (Path.home() / ".local" / "share")) / "vidlens" / "models")
    return base / "audio-tagging" / "ced-mini"


def human(n: int) -> str:
    return f"{n / 1048576:.1f}MB" if n >= 1048576 else f"{n / 1024:.1f}KB"


def report(dst: Path) -> bool:
    ok = True
    for name in FILES:
        p = dst / name
        if p.exists() and p.stat().st_size > 0:
            print(f"  OK   {name:<26} {human(p.stat().st_size)}")
        else:
            print(f"  MISS {name}")
            ok = False
    return ok


def download(url: str, dst: Path) -> None:
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {dst.name}: {pct:3d}%  {human(done)} / {human(total)}",
                      end="", flush=True)
    print()
    tmp.replace(dst)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", help="destination directory")
    ap.add_argument("--check", action="store_true", help="report only, do not download")
    ap.add_argument("--mirror", action="store_true", help="use hf-mirror.com instead of huggingface.co")
    args = ap.parse_args(argv)

    dst = Path(args.dir).expanduser() if args.dir else default_dir()
    dst.mkdir(parents=True, exist_ok=True)
    print(f"target: {dst}")
    if args.check:
        return 0 if report(dst) else 1
    if report(dst):
        print("already complete; nothing to do")
        return 0

    base = MIRROR if args.mirror else BASE
    for name in FILES:
        if (dst / name).exists() and (dst / name).stat().st_size > 0:
            continue
        print(f"downloading {name} ...")
        try:
            download(f"{base}/{name}", dst / name)
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if not args.mirror:
                print("hint: retry with --mirror (hf-mirror.com, for networks that "
                      "cannot reach huggingface.co)", file=sys.stderr)
            return 1
    print("\nresult:")
    ok = report(dst)
    if ok:
        print("\nnext: set VIDLENS_TAGGING_MODEL / VIDLENS_TAGGING_LABELS only if you moved them;"
              "\nthe default path above is picked up automatically.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
