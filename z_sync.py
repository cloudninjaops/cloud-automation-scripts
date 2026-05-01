#!/usr/bin/env python3
"""
sync_config.py — Sync YAML configs from reference-config/ into app-config/.

Folder layout (all relative to where you run the script):
  reference-config/     ← template files, source of truth for structure
  app-config/           ← your real values, never overwritten
  new-config/           ← output (created automatically)

What it does for every key in every YAML file:
  • Key in reference + same file in app        → keep app value, same location
  • Key in reference + different file in app   → carry app value to new location (moved)
  • Key in reference + missing in app (new)    → insert with ref value, tagged for review
  • Key in app + missing in reference (orphan) → warn and keep (or drop with --drop-orphans)

Usage:
  python3 sync_config.py [OPTIONS]

Options:
  --ref-dir        Reference config folder       (default: reference-config)
  --app-dir        App config folder             (default: app-config)
  --out-dir        Output folder                 (default: new-config)
  --in-place       Write results back into app-dir instead of out-dir
  --files          Comma-separated files to sync (default: all .yaml in ref-dir)
  --drop-orphans   Remove app keys not present in reference
  --marker         Tag prefix for new keys       (default: REVIEW_ME)
  --no-color       Disable colored output
  --dry-run        Preview changes without writing files
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("ERROR: PyYAML not installed. Run: pip install pyyaml")


# ─────────────────────────────────────────────────────────────────────────────
# YAML helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}

def dump_yaml(data: dict) -> str:
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

def load_folder(folder: Path, files: list) -> dict:
    return {f: load_yaml(folder / f) for f in files}


# ─────────────────────────────────────────────────────────────────────────────
# Deep dict utils (dot-path based)
# ─────────────────────────────────────────────────────────────────────────────

def flatten(d: dict, prefix="") -> dict:
    """Flatten nested dict → {dot.path: value}"""
    out = {}
    if not isinstance(d, dict):
        return {prefix: d} if prefix else {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out

def set_in(d: dict, dotpath: str, value):
    keys = dotpath.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value

def prune_empty(d):
    if not isinstance(d, dict):
        return d
    return {k: prune_empty(v) for k, v in d.items()
            if not (isinstance(v, dict) and not v)}


# ─────────────────────────────────────────────────────────────────────────────
# Core sync logic
# ─────────────────────────────────────────────────────────────────────────────

def sync(ref: dict, app: dict, files: list, marker: str, drop_orphans: bool):
    result = {f: {} for f in files}
    log    = {"moved": [], "added": [], "kept": [], "orphaned": []}

    # Build cross-file app index: dot.path → (filename, value)
    app_index = {}
    for f in files:
        for dotpath, val in flatten(app.get(f, {})).items():
            app_index[dotpath] = (f, val)

    # Walk every reference key — this defines output structure & file placement
    ref_keys = set()
    for ref_file in files:
        for dotpath, ref_val in flatten(ref.get(ref_file, {})).items():
            ref_keys.add(dotpath)
            if dotpath in app_index:
                app_file, app_val = app_index[dotpath]
                set_in(result[ref_file], dotpath, app_val)
                if app_file != ref_file:
                    log["moved"].append((dotpath, app_file, ref_file, app_val))
                else:
                    log["kept"].append((dotpath, ref_file, app_val))
            else:
                set_in(result[ref_file], dotpath, f"{marker}: {ref_val}")
                log["added"].append((dotpath, ref_file, ref_val))

    # Handle orphaned app keys (in app but not in any reference file)
    for dotpath, (app_file, app_val) in app_index.items():
        if dotpath not in ref_keys:
            if not drop_orphans:
                set_in(result[app_file], dotpath, app_val)
            log["orphaned"].append((dotpath, app_file, app_val))

    result = {f: prune_empty(v) for f, v in result.items()}
    return result, log


# ─────────────────────────────────────────────────────────────────────────────
# Terminal output
# ─────────────────────────────────────────────────────────────────────────────

USE_COLOR = True

def c(code, text):
    if not USE_COLOR:
        return text
    codes = {"green": 92, "yellow": 93, "red": 91, "cyan": 96, "bold": 1, "dim": 2}
    return f"\033[{codes[code]}m{text}\033[0m"

def print_report(log, out_dir, files, marker, dry_run, drop_orphans):
    print()
    print(c("bold", "━" * 60))
    print(c("bold", "  SYNC REPORT" + ("  (DRY RUN)" if dry_run else "")))
    print(c("bold", "━" * 60))

    if log["moved"]:
        print(c("cyan", f"\n  🔀  MOVED  ({len(log['moved'])} keys)"))
        print(c("dim",  "      App value preserved, relocated to reference's file"))
        for dotpath, from_f, to_f, val in log["moved"]:
            print(f"      {from_f}  →  {to_f}  |  {dotpath} = {val!r}")

    if log["added"]:
        print(c("green", f"\n  ✚   ADDED  ({len(log['added'])} keys — fill in real values)"))
        for dotpath, ref_f, ref_val in log["added"]:
            print(f"      {ref_f}  |  {dotpath}  [ref default: {ref_val!r}]")

    if log["orphaned"]:
        status = c("red", "DROPPED") if drop_orphans else c("yellow", "KEPT")
        print(c("yellow", f"\n  ⚠   ORPHANED  ({len(log['orphaned'])} keys, {status} — in app but not in reference)"))
        for dotpath, app_f, val in log["orphaned"]:
            print(f"      {app_f}  |  {dotpath} = {val!r}")

    print(c("dim", f"\n  ✓   {len(log['kept'])} existing app keys carried over unchanged"))

    if not dry_run:
        print(c("green", f"\n  Output → {out_dir}/"))
        for f in files:
            print(f"      {out_dir}/{f}")

    if log["added"]:
        print()
        print(c("yellow", f"  Find new keys to fill in:  grep -r '{marker}' {out_dir}/"))

    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    global USE_COLOR

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ref-dir",      default="reference-config")
    parser.add_argument("--app-dir",      default="app-config")
    parser.add_argument("--out-dir",      default="new-config")
    parser.add_argument("--in-place",     action="store_true")
    parser.add_argument("--files",        default=None)
    parser.add_argument("--drop-orphans", action="store_true")
    parser.add_argument("--marker",       default="REVIEW_ME")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--no-color",     action="store_true")
    args = parser.parse_args()

    if args.no_color:
        USE_COLOR = False

    ref_dir = Path(args.ref_dir)
    app_dir = Path(args.app_dir)
    out_dir = Path(args.app_dir if args.in_place else args.out_dir)

    if not ref_dir.exists():
        sys.exit(f"ERROR: --ref-dir '{ref_dir}' does not exist.")
    if not app_dir.exists():
        sys.exit(f"ERROR: --app-dir '{app_dir}' does not exist.")

    files = [f.strip() for f in args.files.split(",")] if args.files \
            else sorted(p.name for p in ref_dir.glob("*.yaml"))

    if not files:
        sys.exit(f"ERROR: No .yaml files found in '{ref_dir}'.")

    print(c("bold", f"\n  ref  →  {ref_dir}/  ({', '.join(files)})"))
    print(c("bold", f"  app  →  {app_dir}/"))
    print(c("bold", f"  out  →  {out_dir}/\n"))

    ref = load_folder(ref_dir, files)
    app = load_folder(app_dir, files)

    for f in files:
        print(f"  {f:25s}  ref={len(flatten(ref.get(f,{})))} keys   app={len(flatten(app.get(f,{})))} keys")

    result, log = sync(ref, app, files, args.marker, args.drop_orphans)
    print_report(log, out_dir, files, args.marker, args.dry_run, args.drop_orphans)

    if args.dry_run:
        for f in files:
            print(c("bold", f"\n── {f} (preview) ──"))
            print(dump_yaml(result[f]))
        return

    out_dir.mkdir(exist_ok=True)
    for f in files:
        (out_dir / f).write_text(dump_yaml(result[f]))

    print(c("green", "  Done.\n"))

if __name__ == "__main__":
    main()