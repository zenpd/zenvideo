"""
The explainer's voice-over and timeline: each scene's words through Kokoro (exact word timings, cached like the video
studio's), then when every scene and every revealed item happens.

    narrate(plan, work_dir, voice, speed, log) -> timeline (also saved as timeline.json)

Times are in seconds of the final video. A scene's visuals start a moment before its voice (the transition is done by
the time the first word is said); an item with a cue appears just before its words, items without one are spread
over the scene.
"""

import json
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from demo import media, tts
from demo.text import find_phrase, spoken, tokens

LEAD_IN = 0.9          # before the first word
GAP = 0.55             # silence between two scenes' voice-overs
OUTRO = 2.6            # after the last word
LEAD = 0.45            # a scene's visuals start this long before its voice
EARLY = 0.15           # an item appears this long before its cue word
SILENT_SCENE = 3.2     # a scene with nothing to say (e.g. an added closing) stays this long
CACHE_VERSION = 1


# acronyms said letter by letter (the voice model would read some as words)
SPELL = re.compile(r"\b(CLI|QA|UX|UI|API|SDK|IDE|CI|CD|LLM)\b")


def _speak(text: str, voice: str, speed: float, cache: Path, phones: bool = False):
    """WAV (48 kHz mono) and word timings of one scene's voice-over, cached by text, voice, speed and model; with
    phones, also every phoneme's (phoneme, start, end) - for lip-sync (an empty list without exact timing)."""
    say = spoken(SPELL.sub(lambda m: ".".join(m[1]) + ".", text))
    toks = tokens(say)
    key = tts._hash({"v": CACHE_VERSION, "text": say, "voice": voice, "speed": speed, "lang": "en-us",
                     "model": tts._model_id()})
    wav, words = cache / "tts" / f"{key}.wav", cache / "words" / f"{key}-x.json"
    ph_file = cache / "words" / f"{key}-ph.json"
    exact = tts.timing_available()
    if not (wav.exists() and words.exists()) or (phones and exact and not ph_file.exists()):
        for d in (wav.parent, words.parent):
            d.mkdir(parents=True, exist_ok=True)
        if exact:
            ph: list = []
            samples, rate, timed = tts.synthesize_timed(say, voice, speed, "en-us", toks, ph)
            tts._write_wav(samples, rate, wav)
            ph_file.write_text(json.dumps(ph, ensure_ascii=False), encoding="utf-8")
        else:
            tts._synthesize(say, voice, speed, "en-us", wav)
            samples, rate = sf.read(wav, dtype="float32")
            timed = tts.estimate_words(toks, samples, rate)
        words.write_text(json.dumps(timed), encoding="utf-8")
    timed = json.loads(words.read_text(encoding="utf-8"))
    if phones:
        return wav, timed, json.loads(ph_file.read_text(encoding="utf-8")) if ph_file.exists() else []
    return wav, timed


def _cue_times(items: list[dict], words: list[dict], start: float, voice_start: float, end: float) -> list[float]:
    """When each item appears: just before its cue words; items without a cue (or with one said out of order) are
    spread evenly between their neighbours."""
    toks = [w["word"] for w in words]
    times: list[float | None] = []
    floor = start + 0.6
    for it in items:
        i = find_phrase(toks, it["cue"]) if it.get("cue") else None
        t = voice_start + words[i]["start"] - EARLY if i is not None else None
        if t is not None and (t < floor or (times and any(x is not None and t <= x for x in times))):
            t = None
        times.append(t)
    last = max(start + 0.8, end - 1.4)
    k = 0
    while k < len(times):         # fill the gaps between known times evenly
        if times[k] is not None:
            k += 1
            continue
        j = k
        while j < len(times) and times[j] is None:
            j += 1
        lo = times[k - 1] if k > 0 else floor - 0.45
        hi = times[j] if j < len(times) else min(last, lo + 0.9 * (j - k + 1))
        step = (hi - lo) / (j - k + 1)
        for n in range(k, j):
            times[n] = lo + step * (n - k + 1)
        k = j
    return [round(t, 3) for t in times]


ITEM_KEYS = {"points": "items", "stats": "stats", "steps": "steps", "compare": "rows", "icons": "items", "chart": "bars"}


def narrate(plan: dict, work_dir: Path, voice: str, speed: float = 1.0, log=print, cache: Path | None = None) -> dict:
    cache = cache or work_dir.parent / "_cache"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    t = LEAD_IN
    clips, scenes = [], []
    for n, sc in enumerate(plan["scenes"], 1):
        if sc["say"].strip():
            wav, words = _speak(sc["say"], voice, speed, cache)
            dur = media.duration(wav)
            clips.append((t, wav))
            voice_start, voice_end = t, t + dur
            log(f"  scene {n:02d} {sc['type']:<9} {dur:5.1f}s  {sc['say'][:60]}...")
        else:
            words, voice_start, voice_end = [], t, t + SILENT_SCENE
        scenes.append({**sc, "start": round(max(0.0, voice_start - LEAD), 3), "voice_start": round(voice_start, 3),
                       "voice_end": round(voice_end, 3), "words": [{**w, "start": round(w["start"] + voice_start, 3),
                                                                     "end": round(w["end"] + voice_start, 3)}
                                                                    for w in words]})
        t = voice_end + GAP
    duration = round(scenes[-1]["voice_end"] + OUTRO, 3)
    for i, sc in enumerate(scenes):
        sc["end"] = scenes[i + 1]["start"] if i + 1 < len(scenes) else duration
        key = ITEM_KEYS.get(sc["type"])
        if key:
            local = [{**w, "start": w["start"] - sc["voice_start"]} for w in sc["words"]]
            for item, at in zip(sc[key], _cue_times(sc[key], local, sc["start"], sc["voice_start"], sc["voice_end"])):
                item["at"] = at

    # the voice-over: every clip at its start, in one 48 kHz track
    rate = media.SAMPLE_RATE
    buf = np.zeros(int(round(duration * rate)), dtype=np.float32)
    for start, wav in clips:
        clip, clip_rate = sf.read(wav, dtype="float32")
        if clip_rate != rate:
            raise ValueError(f"{wav} is {clip_rate} Hz, expected {rate}")
        pos = int(round(start * rate))
        buf[pos:pos + len(clip)] += clip[:len(buf) - pos]
    sf.write(audio_dir / "voice.wav", buf, rate, subtype="PCM_16")

    timeline = {"title": plan["title"], "app_name": plan.get("app_name", ""), "voice": voice, "speed": speed,
                "duration": duration, "scenes": scenes}
    (work_dir / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Voice-over: {len(clips)} scene(s), {duration:.1f}s in all")
    return timeline


# ── the conversation style ───────────────────────────────────────────────────

TALK_LEAD_IN = 2.4     # the office, and the title over it, before the first word
TURN_GAP = 0.35        # between two people's lines
SAME_GAP = 0.25        # when the same person goes on
TALK_OUTRO = 3.4       # the closing card after the last word
SCREEN_EARLY = 0.35    # the wall screen changes this long before the line that brings it

# mouth shapes from Kokoro's phonemes: M closed (m b p), F lip under teeth (f v), A wide open, E open and wide,
# O round, U small round (and w), C a little open with teeth (most consonants); X is the mouth at rest
VISEME = {**{c: "M" for c in "mbp"}, **{c: "F" for c in "fv"}, **{c: "A" for c in "aɑɐæʌ"},
          **{c: "E" for c in "eɛəɚɜiɪ"}, **{c: "O" for c in "oɔɒ"}, **{c: "U" for c in "uʊw"}}


def mouth_track(phones: list, offset: float) -> list:
    """[[time, shape], ...] for one line: a shape per phoneme, merged when repeated, the mouth at rest in pauses;
    shapes shorter than a frame and a half are dropped so the mouth never flickers."""
    out: list = []
    prev_end = None
    for c, s, e in phones:
        if prev_end is not None and s - prev_end > 0.09:
            out.append([prev_end, "X"])
        shape = VISEME.get(c, "C")
        if not out or out[-1][1] != shape:
            out.append([s, shape])
        prev_end = e
    if prev_end is not None:
        out.append([prev_end, "X"])
    clean: list = []
    for i, (t, shape) in enumerate(out):
        nxt = out[i + 1][0] if i + 1 < len(out) else t + 1
        if nxt - t < 0.05 and shape != "X" and clean:
            continue
        if clean and clean[-1][1] == shape:
            continue
        clean.append([round(t + offset, 3), shape])
    return clean


def narrate_dialogue(plan: dict, work_dir: Path, speed: float = 1.0, log=print, cache: Path | None = None) -> dict:
    """Each line in its speaker's voice, one after another like a real conversation; the timeline has every line's
    words, mouth shapes and sentence ends (where the listener nods), and when the wall screen changes."""
    cache = cache or work_dir.parent / "_cache"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    t = TALK_LEAD_IN
    clips, lines = [], []
    for n, ln in enumerate(plan["lines"]):
        voice = plan["cast"][ln["speaker"]]["voice"]
        wav, words, phones = _speak(ln["say"], voice, speed, cache, phones=True)
        dur = media.duration(wav)
        if n and plan["lines"][n - 1]["speaker"] != ln["speaker"]:
            t += TURN_GAP - SAME_GAP
        clips.append((t, wav))
        abs_words = [{**w, "start": round(w["start"] + t, 3), "end": round(w["end"] + t, 3)} for w in words]
        out = {**ln, "start": round(t, 3), "end": round(t + dur, 3), "words": abs_words,
               "mouth": mouth_track(phones, t) if phones else [],
               "beats": [w["end"] for w in abs_words if w["word"][-1:] in ".?!,;"]}
        if ln.get("screen"):
            sc = ln["screen"]
            local = [{**w, "start": w["start"]} for w in words]
            at = _cue_times(sc["points"], local, -0.6, 0.0, dur) if sc["points"] else []
            sc = {**sc, "at": round(max(0.0, t - SCREEN_EARLY), 3),
                  "points": [{**p, "at": round(max(t + 0.3, t + a), 3)} for p, a in zip(sc["points"], at)]}
            out["screen"] = sc
        lines.append(out)
        log(f"  line {n + 1:02d}/{len(plan['lines'])} {plan['cast'][ln['speaker']]['name']:<7} {dur:5.1f}s  {ln['say'][:60]}...")
        t += dur + SAME_GAP
    duration = round(lines[-1]["end"] + TALK_OUTRO, 3)

    rate = media.SAMPLE_RATE
    buf = np.zeros(int(round(duration * rate)), dtype=np.float32)
    for start, wav in clips:
        clip, clip_rate = sf.read(wav, dtype="float32")
        pos = int(round(start * rate))
        buf[pos:pos + len(clip)] += clip[:len(buf) - pos]
    sf.write(audio_dir / "voice.wav", buf, rate, subtype="PCM_16")
    timeline = {"style": plan.get("style", "conversation"), "title": plan["title"], "app_name": plan.get("app_name", ""),
                "closing": plan.get("closing", ""), "cast": plan["cast"], "speed": speed, "duration": duration,
                "lines": lines,
                # captions and the poster read "scenes": one per line here
                "scenes": [{"start": ln["start"], "end": ln["end"], "voice_end": ln["end"], "say": ln["say"],
                            "type": "line", "words": ln["words"]} for ln in lines]}
    (work_dir / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"Conversation: {len(lines)} lines, {duration:.1f}s in all")
    return timeline
