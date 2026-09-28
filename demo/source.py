"""
Stage 2 for source-video scripts: turn an existing screen recording + the script's action timings into the same
timeline.json / events.jsonl a live recording produces (times in the source video's own clock).
"""

import json

from demo import media
from demo.script import Demo


def run_ingest(demo: Demo, lang: str, log=print) -> None:
    out_dir = demo.lang_dir(lang)
    out_dir.mkdir(parents=True, exist_ok=True)
    video = demo.source_video
    v = media.stream(video, "video")
    fps_num, fps_den = map(int, v["r_frame_rate"].split("/"))
    if fps_num / fps_den != demo.fps:
        raise ValueError(f"{video.name} is {fps_num / fps_den:g} fps but the script says fps: {demo.fps}")
    ok, detail = media.cfr_report(video, demo.fps)
    if not ok:
        raise ValueError(f"{video.name} is not constant frame rate ({detail}); re-encode it with -fps_mode cfr first")
    dur = media.stream_duration(video, "video")
    last = demo.segments[-1].span[1]
    if last > dur + 0.05:
        raise ValueError(f"last segment span ends at {last}s but {video.name} is only {dur:.2f}s long")

    events = []
    for seg in demo.segments:
        for a in seg.actions:
            e = {"t": a.at, "type": {"fill": "type"}.get(a.kind, a.kind), "segment": seg.index, "action": a.where}
            if a.t_end is not None:
                e["t_end"] = a.t_end
            if a.box:
                e.update(x=a.box[0], y=a.box[1], width=a.box[2], height=a.box[3])
            if a.at_word:
                e["at_word"] = a.at_word[lang]
            if a.target:
                e["target"] = a.target.describe()
            for k in ("zoom", "ripple", "by", "value", "key"):
                if k in a.params:
                    e[k] = a.params[k]
            events.append(e)

    timeline = {
        "mode": "source",
        "fps": demo.fps,
        "video": str(video),
        "video_size": [int(v["width"]), int(v["height"])],
        "usable": [0.0, round(dur, 4)],
        "sync": {"cfr": detail},
        "segments": [{"index": s.index, "id": s.id, "span": list(s.span)} for s in demo.segments],
    }
    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    with open(out_dir / "events.jsonl", "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    log(f"{video.name}: {dur:.1f}s, {v['width']}x{v['height']}, {detail}")
    log(f"{len(demo.segments)} segments, {len(events)} events -> {out_dir}")
