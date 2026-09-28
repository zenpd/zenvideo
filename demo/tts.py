"""Stage 1: narration. Kokoro -> 48 kHz WAV per segment, exact durations, word timings."""

import difflib
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from demo import media
from demo.script import Demo
from demo.text import norm

REPO = Path(__file__).resolve().parent.parent
KOKORO_MODEL = Path(os.environ.get("KOKORO_MODEL", REPO / "kokoro-v0_19.onnx"))
VOICES_BIN = Path(os.environ.get("VOICES_BIN", REPO / "voices.bin"))
LOCAL_WHISPER = REPO / "models" / "faster-whisper-base.en"
CACHE_VERSION = 1
ESTIMATE_ALIGNER = "estimate-v1"

_kokoro = None
_whisper = None


def whisper_model_path() -> Path | None:
    """Whisper runs from a local folder only; we never reach the network during a build."""
    env = os.environ.get("DEMO_WHISPER_MODEL")
    if env:
        return None if env.lower() == "none" else Path(env)
    return LOCAL_WHISPER if (LOCAL_WHISPER / "model.bin").exists() else None


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        for p in (KOKORO_MODEL, VOICES_BIN):
            if not p.exists():
                raise FileNotFoundError(f"Kokoro file missing: {p}")
        _kokoro = Kokoro(str(KOKORO_MODEL), str(VOICES_BIN))
    return _kokoro


def _get_whisper(path: Path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        if not (path / "model.bin").exists():
            raise FileNotFoundError(f"Whisper model not found at {path} (expected model.bin, config.json, ...)")
        _whisper = WhisperModel(str(path), device="cpu", compute_type="int8")
    return _whisper


def _model_id() -> str:
    return f"{KOKORO_MODEL.name}:{KOKORO_MODEL.stat().st_size}|{VOICES_BIN.name}:{VOICES_BIN.stat().st_size}"


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:24]


def _write_wav(samples, rate: int, out: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "kokoro.wav"
        sf.write(raw, samples, rate, subtype="FLOAT")
        tmp = out.with_suffix(".tmp.wav")
        media.run_ffmpeg(["-i", raw, "-ar", media.SAMPLE_RATE, "-ac", 1, "-c:a", "pcm_s16le", tmp])
        tmp.replace(out)


def _synthesize(text: str, voice: str, speed: float, lang: str, out: Path) -> None:
    samples, rate = _get_kokoro().create(text, voice=voice, speed=speed, lang=lang)
    _write_wav(samples, rate, out)


# ── exact word timing from Kokoro itself ─────────────────────────────────────
# Kokoro predicts how many frames every phoneme lasts before it renders audio (the '/Clip' node right after
# the duration predictor). A copy of the model that also outputs that tensor gives exact phoneme timings,
# with bit-identical audio, so no speech-recognition model is needed.

TIMED_MODEL = REPO / "models" / (KOKORO_MODEL.stem + ".timed.onnx")
DURATION_TENSOR = "/Clip_output_0"
KOKORO_ALIGNER = "kokoro-durations-v1"
_timed = None


def _timed_session():
    global _timed
    if _timed is None:
        import onnxruntime as ort
        if not TIMED_MODEL.exists() or TIMED_MODEL.stat().st_mtime < KOKORO_MODEL.stat().st_mtime:
            import onnx
            from onnx import TensorProto, helper
            model = onnx.load(str(KOKORO_MODEL))
            if not any(n.output and DURATION_TENSOR in n.output for n in model.graph.node):
                raise RuntimeError(f"{KOKORO_MODEL.name} has no {DURATION_TENSOR} node - unsupported Kokoro export")
            model.graph.output.append(helper.make_tensor_value_info(DURATION_TENSOR, TensorProto.FLOAT, None))
            TIMED_MODEL.parent.mkdir(parents=True, exist_ok=True)
            tmp = TIMED_MODEL.with_suffix(".tmp")
            onnx.save(model, str(tmp))
            tmp.replace(TIMED_MODEL)
        _timed = ort.InferenceSession(str(TIMED_MODEL), providers=["CPUExecutionProvider"])
    return _timed


def timing_available() -> bool:
    try:
        _timed_session()
        return True
    except Exception:  # missing 'onnx' package or an incompatible model: fall back to estimates
        return False


_PHONE_MARKS = set("ˈˌːˑ")


def _phones(s: str) -> str:
    """Phoneme characters only (no stress/length marks, spaces or punctuation), for matching."""
    return "".join(c for c in s if c not in _PHONE_MARKS and not c.isspace() and c not in ".,!?;:—…\"'()-")


def synthesize_timed(text: str, voice: str, speed: float, lang: str, toks: list[str]):
    """Same audio as Kokoro.create(), plus the exact start/end of every script token."""
    from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
    from kokoro_onnx.trim import trim as trim_audio

    k = _get_kokoro()
    sess = _timed_session()
    style = k.get_voice_style(voice)
    parts, stream, offset = [], [], 0
    for chunk in k._split_phonemes(k.tokenizer.phonemize(text, lang)):
        chunk = chunk[:MAX_PHONEME_LENGTH]
        kept = [c for c in chunk if c in k.tokenizer.vocab]
        ids = [k.tokenizer.vocab[c] for c in kept]
        audio, frames = sess.run(None, {"tokens": [[0, *ids, 0]], "style": style[len(ids)],
                                        "speed": np.ones(1, dtype=np.float32) * speed})
        frames = np.asarray(frames, dtype=np.float64).reshape(-1)
        per_frame = len(audio) / frames.sum()
        bounds = np.concatenate([[0.0], np.cumsum(frames)]) * per_frame   # bounds[i+1] = end of token i (0 = pad)
        trimmed, (a, b) = trim_audio(audio)
        for i, c in enumerate(kept):
            s = min(max(bounds[i + 1] - a, 0), b - a)
            e = min(max(bounds[i + 2] - a, 0), b - a)
            if _phones(c):
                stream.append((c, (offset + s) / SAMPLE_RATE, (offset + e) / SAMPLE_RATE))
        parts.append(trimmed)
        offset += len(trimmed)
    samples = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)

    expected = [(c, ti) for ti, tok in enumerate(toks) for c in _phones(k.tokenizer.phonemize(tok, lang))]
    spans: list[list[float] | None] = [None] * len(toks)
    matcher = difflib.SequenceMatcher(None, [c for c, _ in expected], [c for c, _, _ in stream], autojunk=False)
    for blk in matcher.get_matching_blocks():
        for n in range(blk.size):
            ti = expected[blk.a + n][1]
            _, s, e = stream[blk.b + n]
            spans[ti] = [s, e] if spans[ti] is None else [min(spans[ti][0], s), max(spans[ti][1], e)]
    return samples, SAMPLE_RATE, _finish_words(toks, [tuple(x) if x else None for x in spans], len(samples) / SAMPLE_RATE)


def _finish_words(toks: list[str], times: list, clip_duration: float) -> list[dict]:
    """Fill tokens without a timing (nothing matched) between their neighbours, keep everything monotonic."""
    i = 0
    while i < len(toks):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(toks) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(toks) else clip_duration
        _spread(toks, range(i, j), t0, max(t0, t1), times)
        i = j
    words, prev_start = [], 0.0
    for tok, (s, e) in zip(toks, times):
        s = min(max(s, prev_start), clip_duration)
        e = min(max(e, s), clip_duration)
        words.append({"word": tok, "start": round(s, 3), "end": round(e, 3)})
        prev_start = s
    return words


def _spread(toks: list[str], idxs: range, t0: float, t1: float, times: list) -> None:
    """Share the span [t0, t1] between tokens in proportion to their length."""
    weights = [max(1, len(norm(toks[i]))) for i in idxs]
    total = sum(weights)
    t = t0
    for i, w in zip(idxs, weights):
        step = (t1 - t0) * w / total
        times[i] = (t, t + step)
        t += step


def map_words(toks: list[str], heard: list[tuple[str, float, float]], clip_duration: float) -> list[dict]:
    """Give every script token a time, using what Whisper heard. Script spelling always wins."""
    a = [norm(t) for t in toks]
    b = [norm(w) for w, _, _ in heard]
    times: list[tuple[float, float] | None] = [None] * len(toks)

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k][1], heard[j1 + k][2])
        elif tag == "replace":
            _spread(toks, range(i1, i2), heard[j1][1], heard[j2 - 1][2], times)

    i = 0
    while i < len(toks):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(toks) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(toks) else clip_duration
        _spread(toks, range(i, j), t0, max(t0, t1), times)
        i = j

    words, prev_start = [], 0.0
    for tok, (s, e) in zip(toks, times):
        s = min(max(s, prev_start), clip_duration)
        e = min(max(e, s), clip_duration)
        words.append({"word": tok, "start": round(s, 3), "end": round(e, 3)})
        prev_start = s
    return words


def _speech_regions(samples, rate: int, min_gap: float = 0.12) -> tuple[float, float, list[tuple[float, float]]]:
    """Speech start/end and the interior silent gaps of a clip, from 10 ms RMS frames."""
    hop = rate // 100
    n = len(samples) // hop
    if n == 0:
        return 0.0, len(samples) / rate, []
    frames = samples[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    loud = rms > max(rms.max() * 0.03, 1e-4)
    idx = np.flatnonzero(loud)
    if idx.size == 0:
        return 0.0, len(samples) / rate, []
    first, last = int(idx[0]), int(idx[-1]) + 1
    gaps, run = [], None
    for i in range(first, last):
        if not loud[i] and run is None:
            run = i
        elif loud[i] and run is not None:
            if (i - run) / 100 >= min_gap:
                gaps.append((run / 100, i / 100))
            run = None
    return first / 100, last / 100, gaps


def estimate_words(toks: list[str], samples, rate: int) -> list[dict]:
    """No Whisper: pin phrase boundaries (punctuation) to the clip's pauses, spread words inside each phrase."""
    start, end, gaps = _speech_regions(samples, rate)
    breaks = [i for i, t in enumerate(toks[:-1]) if t[-1] in ",.;:!?"]
    weights = [max(1, len(norm(t))) for t in toks]
    total = sum(weights)
    cum = np.cumsum(weights)

    anchors: dict[int, tuple[float, float]] = {}
    last_k = -1
    for g0, g1 in gaps:
        centre = (g0 + g1) / 2
        best = None
        for k, b in enumerate(breaks):
            if k <= last_k:
                continue
            expected = start + (end - start) * cum[b] / total
            if abs(expected - centre) <= 1.5 and (best is None or abs(expected - centre) < best[0]):
                best = (abs(expected - centre), k)
        if best:
            last_k = best[1]
            anchors[breaks[best[1]]] = (g0, g1)

    times: list = [None] * len(toks)
    phrase_start_tok, phrase_start_t = 0, start
    for b in sorted(anchors) + [len(toks) - 1]:
        t_end = anchors[b][0] if b in anchors else end
        _spread(toks, range(phrase_start_tok, b + 1), phrase_start_t, max(phrase_start_t, t_end), times)
        phrase_start_tok = b + 1
        if b in anchors:
            phrase_start_t = anchors[b][1]
    return [{"word": t, "start": round(s, 3), "end": round(e, 3)} for t, (s, e) in zip(toks, times)]


def _align(wav: Path, toks: list[str], whisper_path: Path | None) -> list[dict]:
    if whisper_path is None:
        samples, rate = sf.read(wav, dtype="float32")
        return estimate_words(toks, samples, rate)
    segments, _ = _get_whisper(whisper_path).transcribe(
        str(wav),
        language="en",
        word_timestamps=True,
        initial_prompt=" ".join(toks),
        condition_on_previous_text=False,
        beam_size=5,
    )
    heard = [(w.word, w.start, w.end) for s in segments for w in (s.words or [])]
    return map_words(toks, heard, media.duration(wav))


def run_tts(demo: Demo, lang: str, log=print, progress=None) -> None:
    voice = demo.voice[lang]
    klang = demo.kokoro_lang(lang)
    voices = _get_kokoro().get_voices()
    if voice not in voices:
        raise ValueError(f"voice {voice!r} not in voices.bin; available: {', '.join(sorted(voices))}")

    out_dir = demo.lang_dir(lang)
    audio_dir = out_dir / "audio"
    cache = demo.build_root.parent / "_cache"
    for d in (audio_dir, cache / "tts", cache / "words"):
        d.mkdir(parents=True, exist_ok=True)
    for stale in audio_dir.glob("seg_*.wav"):
        stale.unlink()

    exact = timing_available()
    whisper_path = None if exact else whisper_model_path()
    if exact:
        aligner = KOKORO_ALIGNER
        log("Word timing: exact, from Kokoro's own phoneme durations")
    elif whisper_path:
        aligner = f"whisper:{whisper_path.name}"
    else:
        aligner = ESTIMATE_ALIGNER
        log("WARNING: exact word timing unavailable (install the 'onnx' package) - word timings are ESTIMATED "
            "from pauses (expect roughly +/-150 ms).")

    model_id = _model_id()
    durations, words_out = [], []
    for seg in demo.segments:
        if progress:
            progress((seg.index - 1) / len(demo.segments))
        if seg.silent:
            durations.append({"index": seg.index, "id": seg.id, "file": None, "duration": 0.0, "text": ""})
            words_out.append({"index": seg.index, "id": seg.id, "words": []})
            log(f"  [{seg.index:03d}] {seg.id:<18}   silent")
            continue
        text = seg.spoken(lang)
        toks = seg.tokens(lang)
        key = _hash({"v": CACHE_VERSION, "text": text, "voice": voice, "speed": demo.speed,
                     "lang": klang, "model": model_id})
        wav_cached = cache / "tts" / f"{key}.wav"
        words_cached = cache / "words" / f"{_hash([key, aligner, CACHE_VERSION])}.json"

        status = "cached"
        if exact and not (wav_cached.exists() and words_cached.exists()):
            samples, rate, words = synthesize_timed(text, voice, demo.speed, klang, toks)
            _write_wav(samples, rate, wav_cached)
            words_cached.write_text(json.dumps(words), encoding="utf-8")
            status = "synthesized"
        if not wav_cached.exists():
            _synthesize(text, voice, demo.speed, klang, wav_cached)
            status = "synthesized"
        if not words_cached.exists():
            words_cached.write_text(json.dumps(_align(wav_cached, toks, whisper_path)), encoding="utf-8")

        seg_file = audio_dir / f"seg_{seg.index:03d}.wav"
        shutil.copyfile(wav_cached, seg_file)
        dur = media.duration(seg_file)
        durations.append({"index": seg.index, "id": seg.id, "file": f"audio/{seg_file.name}",
                          "duration": round(dur, 4), "text": text})
        words_out.append({"index": seg.index, "id": seg.id,
                          "words": json.loads(words_cached.read_text(encoding="utf-8"))})
        log(f"  [{seg.index:03d}] {seg.id:<18} {dur:6.2f}s  {status}")

    (out_dir / "durations.json").write_text(
        json.dumps({"sample_rate": media.SAMPLE_RATE, "voice": voice, "segments": durations}, indent=2),
        encoding="utf-8")
    (out_dir / "words.json").write_text(json.dumps({"aligner": aligner, "segments": words_out}, indent=2),
                                        encoding="utf-8")
    total = sum(d["duration"] for d in durations)
    log(f"Narration: {len(durations)} segments, {total:.1f}s of speech -> {out_dir}")
