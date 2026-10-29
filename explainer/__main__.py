"""python -m explainer narration.txt [--title ...] [--theme midnight|daylight|sunrise|forest] [--voice af_sky]
[--tighten --seconds 120] [--captions soft|burned|none] [--replan] [--out build/explainers/<name>]
[--style conversation [--cast maya sam] [--voices af_sarah am_michael]]"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from explainer.dialogue import CAST, STUDIO_CAST
from explainer.office3d import AVATARS
from explainer.render import THEMES
from explainer.service import STYLES, generate, stage_of
from ppt.writer import StoryError


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m explainer", description="Narration -> animated explainer video")
    ap.add_argument("narration", help="text file with the narration (or transcript, or notes)")
    ap.add_argument("--title", default="", help="product or topic name")
    ap.add_argument("--style", default="explainer", choices=list(STYLES),
                    help="explainer (motion graphics), conversation (two people in an office) or presenters (two "
                         "presenters in a branded studio)")
    ap.add_argument("--theme", default="midnight", choices=list(THEMES))
    ap.add_argument("--voice", default="af_sky", help="explainer: the narrator's voice")
    ap.add_argument("--cast", nargs=2, choices=list(CAST) + list(STUDIO_CAST) + list(AVATARS),
                    help="conversation: who asks and who explains; presenters: the two presenters")
    ap.add_argument("--logo", help="presenters: the company's logo (PNG or JPG), on the studio wall")
    ap.add_argument("--brand", default="", help="presenters: the company's name (shown when there is no logo)")
    ap.add_argument("--voices", nargs=2, help="conversation: their voices (default: each person's own)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--tighten", action="store_true", help="explainer: let the AI rewrite the voice-over to --seconds")
    ap.add_argument("--seconds", type=int, default=120, help="target length (tighten, or a conversation)")
    ap.add_argument("--captions", default="soft", choices=["soft", "burned", "none"])
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--replan", action="store_true", help="plan the scenes or dialogue again (costs tokens)")
    ap.add_argument("--out", help="work folder (default build/explainers/<narration file name>)")
    a = ap.parse_args()
    src = Path(a.narration)
    out = Path(a.out) if a.out else Path("build") / "explainers" / src.stem
    out.mkdir(parents=True, exist_ok=True)
    # a job record like the studio's (explainer.api reads it), so the studio shows this run, its progress and log
    now = lambda: datetime.datetime.now().isoformat(timespec="seconds")   # noqa: E731
    job = {"id": out.name, "title": a.title or src.stem, "custom_title": a.title, "created": now(), "status": "running",
           "error": None, "progress": 0, "stage": "Writing the script", "style": a.style, "cast": a.cast or [],
           "voices": a.voices or ["", ""], "theme": a.theme, "voice": a.voice, "speed": a.speed,
           "mode": "tighten" if a.tighten else "as_written", "seconds": a.seconds, "captions": a.captions,
           "music": not a.no_music, "brand_name": a.brand, "source": "command line"}
    (out / "job.log").write_text("", encoding="utf-8")
    saved = [0.0]

    def save(**fields) -> None:
        job.update(fields, updated=now())
        tmp = out / "job.json.tmp"
        tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
        tmp.replace(out / "job.json")

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(out / "job.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
        stage = stage_of(msg)
        if stage:
            save(stage=stage)

    def progress(p: float) -> None:
        if p - saved[0] >= 0.02 or p >= 1:
            saved[0] = p
            save(progress=round(p, 3), stage=f"Animating · {round(p * 100)}%")

    save()
    try:
        video, usage = generate(out, src.read_text(encoding="utf-8"), a.title, a.theme, a.voice, a.speed,
                                "tighten" if a.tighten else "as_written", a.seconds, a.captions, not a.no_music,
                                a.replan, style=a.style, cast=tuple(a.cast) if a.cast else None,
                                voices=tuple(a.voices or ()), logo=Path(a.logo) if a.logo else None,
                                brand_name=a.brand, log=log, progress=progress)
    except Exception as e:  # noqa: BLE001 - recorded for the studio, then shown here
        log(f"ERROR: {e}")
        save(status="failed", error=str(e).splitlines()[0][:300])
        if isinstance(e, StoryError):
            print(f"error: {e}", file=sys.stderr)
            return 1
        raise
    from demo import media
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    save(status="done", progress=1, stage="", built=now(), duration=round(media.duration(video), 1),
         scenes_count=len(plan.get("scenes") or plan.get("lines") or []),
         title=a.title or plan.get("app_name") or plan.get("title") or src.stem,
         usage={"calls": 1, **{k: usage[k] for k in ("input_tokens", "output_tokens", "cost_usd", "model")}} if usage else None)
    print(video)
    if usage:
        print(f"tokens: {usage['input_tokens']:,} + {usage['output_tokens']:,} (about ${usage['cost_usd']:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
