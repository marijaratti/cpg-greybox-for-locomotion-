#!/usr/bin/env python3
"""
findings.py - a tiny, git-native API for recording research findings.

Why this exists
---------------
Claude Code (or you) runs experiments in this repo. Every time something is
learned - a result, a negative result, a bug, a decision - it gets written down
as ONE Markdown file in `findings/`, with a machine-readable header. Git is the
transport: commit + push and the finding is on GitHub, with a timestamp and the
exact code version (commit hash) it came from.

No server, no database, no extra dependencies (standard library only).

Two ways to use it
------------------
1. Command line (what Claude Code calls):

    python tools/findings.py add \
        --title "Removing reciprocal inhibition abolishes alternation" \
        --type result \
        --summary "With w_inh=0 both half-centres fire in phase (lag 0.02)." \
        --metric phase_lag=0.02 --metric w_inh=0 \
        --tag half-centre --tag ablation \
        --evidence figures/ablation_phase.png \
        --commit --push

    python tools/findings.py list            # table of all findings
    python tools/findings.py show F-0003      # print one finding
    python tools/findings.py status F-0003 confirmed
    python tools/findings.py index           # rebuild findings/INDEX.md

2. From Python (e.g. at the end of a training script):

    from tools.findings import log_finding
    log_finding(title="...", summary="...", metrics={"val_r2": 0.81})

File format
-----------
findings/F-0003-removing-reciprocal-inhibition.md

    ---
    id: "F-0003"
    title: "Removing reciprocal inhibition abolishes alternation"
    date: "2026-11-23T12:04:11Z"
    type: "result"
    status: "tentative"
    tags: ["half-centre", "ablation"]
    metrics: {"phase_lag": 0.02, "w_inh": 0}
    evidence: ["figures/ablation_phase.png"]
    code_version: "a1b2c3d"
    supersedes: null
    ---
    ## Summary
    ...

Every header value is JSON, which is also valid YAML, so the files can be read
by this script, by any YAML/JSON parser, and by a human on GitHub.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINDINGS_DIR = ROOT / "findings"
INDEX_PATH = FINDINGS_DIR / "INDEX.md"

TYPES = ("result", "negative", "bug", "decision", "idea", "question")
STATUSES = ("tentative", "confirmed", "superseded", "retracted")
HEADER_KEYS = ("id", "title", "date", "type", "status", "tags", "metrics",
               "evidence", "code_version", "supersedes")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _git(*args: str, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{out.stderr.strip()}")
    return out.stdout.strip()


def _code_version() -> str | None:
    """Short hash of HEAD, plus '-dirty' if there are uncommitted code changes."""
    try:
        head = _git("rev-parse", "--short", "HEAD")
    except Exception:
        return None
    # ignore changes inside findings/ itself when deciding "dirty"
    dirty = _git("status", "--porcelain", "--", ".", ":(exclude)findings", check=False)
    return head + ("-dirty" if dirty else "")


def _slug(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "finding"


def _parse_value(raw: str):
    """'0.5' -> 0.5, '3' -> 3, 'true' -> True, anything else -> str."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _next_id() -> str:
    nums = [int(m.group(1)) for p in FINDINGS_DIR.glob("F-*.md")
            if (m := re.match(r"F-(\d+)", p.name))]
    return f"F-{(max(nums) + 1 if nums else 1):04d}"


def _path_for(fid: str) -> Path:
    matches = sorted(FINDINGS_DIR.glob(f"{fid}-*.md")) + sorted(FINDINGS_DIR.glob(f"{fid}.md"))
    if not matches:
        raise SystemExit(f"No finding with id {fid}")
    return matches[0]


# --------------------------------------------------------------------------- #
# read / write
# --------------------------------------------------------------------------- #
def _render(meta: dict, body: str) -> str:
    header = "\n".join(f"{k}: {json.dumps(meta.get(k), ensure_ascii=False)}"
                       for k in HEADER_KEYS)
    return f"---\n{header}\n---\n{body.rstrip()}\n"


def read_finding(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path} has no header")
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = json.loads(v.strip())
    meta["_path"] = path
    return meta, m.group(2)


def load_findings() -> list[dict]:
    return [read_finding(p)[0] for p in sorted(FINDINGS_DIR.glob("F-*.md"))]


def log_finding(title: str,
                summary: str,
                type: str = "result",
                status: str = "tentative",
                tags: list[str] | tuple = (),
                metrics: dict | None = None,
                evidence: list[str] | tuple = (),
                details: str = "",
                next_steps: str = "",
                supersedes: str | None = None) -> Path:
    """Write one finding to findings/ and rebuild the index. Returns the file path."""
    if type not in TYPES:
        raise ValueError(f"type must be one of {TYPES}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    FINDINGS_DIR.mkdir(exist_ok=True)

    fid = _next_id()
    meta = {
        "id": fid,
        "title": title.strip(),
        "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "type": type,
        "status": status,
        "tags": list(tags),
        "metrics": metrics or {},
        "evidence": list(evidence),
        "code_version": _code_version(),
        "supersedes": supersedes,
    }
    body = f"## Summary\n{summary.strip()}\n"
    if details.strip():
        body += f"\n## Details\n{details.strip()}\n"
    if next_steps.strip():
        body += f"\n## Next steps\n{next_steps.strip()}\n"

    path = FINDINGS_DIR / f"{fid}-{_slug(title)}.md"
    path.write_text(_render(meta, body), encoding="utf-8")

    if supersedes:
        set_status(supersedes, "superseded", rebuild=False)
    build_index()
    return path


def set_status(fid: str, status: str, rebuild: bool = True) -> Path:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    path = _path_for(fid)
    meta, body = read_finding(path)
    meta["status"] = status
    path.write_text(_render(meta, body), encoding="utf-8")
    if rebuild:
        build_index()
    return path


def build_index() -> Path:
    rows = load_findings()
    lines = [
        "# Findings index",
        "",
        "_Auto-generated by `tools/findings.py` - do not edit by hand._",
        "",
        "| ID | Date | Type | Status | Title | Key metrics |",
        "|----|------|------|--------|-------|-------------|",
    ]
    for f in reversed(rows):  # newest first
        metrics = ", ".join(f"{k}={v}" for k, v in list(f["metrics"].items())[:3])
        title = f["title"].replace("|", "\\|")
        if f["status"] in ("superseded", "retracted"):
            title = f"~~{title}~~"
        lines.append(f"| [{f['id']}]({f['_path'].name}) | {f['date'][:10]} | "
                     f"{f['type']} | {f['status']} | {title} | {metrics} |")
    if not rows:
        lines.append("| - | - | - | - | No findings yet | - |")
    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return INDEX_PATH


def commit(message: str, push: bool = False) -> None:
    _git("add", "findings")
    if not _git("diff", "--cached", "--name-only", check=False):
        print("Nothing new to commit.")
        return
    _git("commit", "-m", message)
    print(f"Committed: {message}")
    if push:
        _git("push")
        print("Pushed.")


# --------------------------------------------------------------------------- #
# command line
# --------------------------------------------------------------------------- #
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Record and browse research findings.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record a new finding")
    a.add_argument("--title", required=True)
    a.add_argument("--summary", required=True, help="2-4 sentences: what was found")
    a.add_argument("--type", default="result", choices=TYPES)
    a.add_argument("--status", default="tentative", choices=STATUSES)
    a.add_argument("--tag", action="append", default=[], dest="tags")
    a.add_argument("--metric", action="append", default=[], metavar="KEY=VALUE")
    a.add_argument("--evidence", action="append", default=[],
                   help="path to a figure, log, notebook or results file")
    a.add_argument("--details", default="", help="longer explanation / method")
    a.add_argument("--details-file", help="read details from a Markdown file")
    a.add_argument("--next", default="", dest="next_steps")
    a.add_argument("--supersedes", help="id of an older finding this replaces")
    a.add_argument("--commit", action="store_true", help="git commit findings/")
    a.add_argument("--push", action="store_true", help="also git push (implies --commit)")

    sub.add_parser("list", help="print all findings")
    s = sub.add_parser("show", help="print one finding")
    s.add_argument("id")
    st = sub.add_parser("status", help="change a finding's status")
    st.add_argument("id")
    st.add_argument("status", choices=STATUSES)
    st.add_argument("--commit", action="store_true")
    st.add_argument("--push", action="store_true")
    sub.add_parser("index", help="rebuild findings/INDEX.md")

    args = ap.parse_args(argv)

    if args.cmd == "add":
        metrics = {}
        for kv in args.metric:
            if "=" not in kv:
                ap.error(f"--metric must look like key=value, got {kv!r}")
            k, v = kv.split("=", 1)
            metrics[k.strip()] = _parse_value(v.strip())
        details = args.details
        if args.details_file:
            details = Path(args.details_file).read_text(encoding="utf-8")
        missing = [e for e in args.evidence if not (ROOT / e).exists()]
        if missing:
            print(f"warning: evidence not found in repo: {missing}", file=sys.stderr)
        path = log_finding(args.title, args.summary, args.type, args.status,
                           args.tags, metrics, args.evidence, details,
                           args.next_steps, args.supersedes)
        print(f"Wrote {path.relative_to(ROOT)}")
        if args.commit or args.push:
            fid = path.name[:6]
            commit(f"finding {fid}: {args.title}", push=args.push)

    elif args.cmd == "list":
        rows = load_findings()
        if not rows:
            print("No findings yet.")
        for f in rows:
            print(f"{f['id']}  {f['date'][:10]}  {f['type']:<9} {f['status']:<10} {f['title']}")

    elif args.cmd == "show":
        print(_path_for(args.id).read_text(encoding="utf-8"))

    elif args.cmd == "status":
        set_status(args.id, args.status)
        print(f"{args.id} -> {args.status}")
        if args.commit or args.push:
            commit(f"finding {args.id}: mark {args.status}", push=args.push)

    elif args.cmd == "index":
        print(f"Wrote {build_index().relative_to(ROOT)}")


if __name__ == "__main__":
    main()
