"""
python -m demo <command> <demo.yaml> [--lang en] [--build-dir DIR]

  validate  check the script without running anything
  tts       narration WAVs, durations.json, words.json
  record    screen-capture the scripted browser run -> raw.mp4, timeline.json, events.jsonl
            (source-video scripts: read the existing recording and write timeline.json, events.jsonl)
  render    final.mp4 + final.srt from the recording and narration
  check     sync acceptance check on final.mp4
  all       tts -> record -> render -> check
  auth      open a normal browser window, log in by hand, save storage_state for later runs
"""

import argparse
import sys
import time

from demo.script import ScriptError, load


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m demo", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["validate", "tts", "record", "render", "check", "all", "auth"])
    p.add_argument("script", help="path to demo.yaml")
    p.add_argument("--lang", help="language to build (default: every language in the script)")
    p.add_argument("--build-dir", help="default: build/<script name>")
    args = p.parse_args()

    try:
        # Only `validate`/`record`/`all` need the upload file(s) to actually be on disk right now —
        # `tts`/`render`/`check` operate on an already-recorded run and never touch them, so an upload
        # file that moved or was cleaned up after recording shouldn't block re-running those.
        needs_uploads = args.command in ("validate", "record", "all")
        demo = load(args.script, args.build_dir, require_uploads=needs_uploads)
    except ScriptError as e:
        print(f"Script error: {e}", file=sys.stderr)
        return 2

    if args.lang and args.lang not in demo.languages:
        print(f"--lang {args.lang!r} is not in the script's languages {demo.languages}", file=sys.stderr)
        return 2
    langs = [args.lang] if args.lang else demo.languages

    if args.command == "validate":
        n = sum(len(s.actions) for s in demo.segments)
        print(f"OK: {demo.title!r}, {len(demo.segments)} segments, {n} actions, languages {demo.languages}")
        return 0

    if args.command == "auth":
        from demo.record import run_auth
        run_auth(demo)
        return 0

    stages = ["tts", "record", "render", "check"] if args.command == "all" else [args.command]
    for lang in langs:
        for stage in stages:
            print(f"\n=== {stage} [{lang}] ===")
            t0 = time.perf_counter()
            if stage == "tts":
                from demo.tts import run_tts
                run_tts(demo, lang)
            elif stage == "record" and demo.mode == "source":
                from demo.source import run_ingest
                run_ingest(demo, lang)
            elif stage == "record":
                from demo.record import run_record
                run_record(demo, lang)
            elif stage == "render":
                from demo.render import run_render
                run_render(demo, lang)
            elif stage == "check":
                from demo.check import run_check
                if not run_check(demo, lang):
                    return 1
            print(f"--- {stage} done in {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
