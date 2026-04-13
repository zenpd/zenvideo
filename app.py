"""
TTS Audio/Video Pipeline — Streamlit UI
Stage-wise interface for: WebM→MP4 | Format Transcript | Generate TTS | Sync & Merge

Run with:
  streamlit run app.py
"""

import os
import sys
from pathlib import Path

# Ensure we resolve imports relative to this file's directory
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from config import (
    WPM, GAP_SEC, GAP_MS,
    KOKORO_MODEL, VOICES_BIN, TTS_VOICE, TTS_SPEED, TTS_LANG, AVAILABLE_VOICES,
    RAW_TRANSCRIPT, TRANSCRIPT, SEGMENTS_DIR, FINAL_AUDIO, OUTPUT_VIDEO,
    VIDEO_FILE, AUDIO_BITRATE, SAMPLE_RATE, VIDEO_PRESET, VIDEO_CRF,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TTS Video Pipeline",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _file_badge(path: str) -> tuple[bool, str]:
    p = Path(path)
    if p.exists():
        size = p.stat().st_size
        label = f"{size/(1024*1024):.1f} MB" if size > 1_048_576 else f"{size/1024:.1f} KB"
        return True, f"**{p.name}** — {label}"
    return False, f"**{p.name}** — not found"


def _run(func, **kwargs):
    """Call func(log=..., **kwargs), capture log lines, return (success, logs, result)."""
    lines = []
    def _log(msg):
        lines.append(str(msg))
    try:
        result = func(log=_log, **kwargs)
        return True, lines, result
    except Exception as exc:
        lines.append(f"ERROR: {exc}")
        return False, lines, None


def _show_log(lines: list[str], success: bool):
    colour = "✅" if success else "❌"
    st.code(colour + "\n" + "\n".join(lines), language="")


# ── Sidebar — pipeline status ─────────────────────────────────────────────────

PIPELINE_FILES = {
    "Raw Transcript":       RAW_TRANSCRIPT,
    "Formatted Transcript": TRANSCRIPT,
    "TTS Audio":            FINAL_AUDIO,
    "Input Video":          VIDEO_FILE,
    "Output Video":         OUTPUT_VIDEO,
    "Kokoro Model":         KOKORO_MODEL,
    "Voices File":          VOICES_BIN,
}

with st.sidebar:
    st.title("🎬 TTS Pipeline")
    st.markdown("---")
    st.subheader("File Status")
    for label, fpath in PIPELINE_FILES.items():
        ok, msg = _file_badge(fpath)
        (st.success if ok else st.error)(f"{label}: {msg}")
    st.markdown("---")
    if st.button("🔄 Refresh status"):
        st.rerun()
    st.caption("Edit `.env` to change default paths & settings.")

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🎬 TTS Audio / Video Pipeline")
st.markdown(
    "**Stage-by-stage pipeline:** "
    "`0: WebM → MP4` → `1: Format Transcript` → `2: Generate TTS` → `3: Sync & Merge`"
)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "🎥  Stage 0 — WebM → MP4",
    "📝  Stage 1 — Format Transcript",
    "🔊  Stage 2 — Generate TTS",
    "🎬  Stage 3 — Sync & Merge",
    "📊  Status & Config",
])

# ─────────────────────────────────────────────────────────────────────────────
# Stage 0: WebM → MP4
# ─────────────────────────────────────────────────────────────────────────────
with tab0:
    st.header("Stage 0 — Convert WebM → MP4")
    st.info(
        "Optional preprocessing step. "
        "Use this if your screen recording was saved as `.webm`."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        webm_in  = st.text_input("WebM input file", value="Recording.webm",
                                  help="Path to the .webm screen recording")
        mp4_out  = st.text_input("MP4 output file", value="Recording.mp4",
                                  help="Destination .mp4 path")
    with col_b:
        preset_0 = st.selectbox("Encoding preset", ["fast", "medium", "slow"],
                                 index=["fast", "medium", "slow"].index(VIDEO_PRESET),
                                 help="Slower preset = better compression")
        crf_0    = st.slider("CRF quality (lower = better)", 0, 51,
                              int(VIDEO_CRF), help="23 is the ffmpeg default")

    col_c, col_d = st.columns(2)
    with col_c:
        start_0 = st.text_input("Start time (optional)", value="",
                                placeholder="HH:MM:SS (e.g. 00:02:30)",
                                help="Trim video from this timestamp")
    with col_d:
        end_0   = st.text_input("End time (optional)", value="",
                                placeholder="HH:MM:SS (e.g. 00:10:00)",
                                help="Trim video to this timestamp")

    webm_exists = Path(webm_in).exists()
    if not webm_exists:
        st.warning(f"File not found: `{webm_in}` — enter the correct path above.")

    if st.button("▶️  Convert", key="btn_webm", disabled=not webm_exists):
        with st.spinner("Converting…"):
            from convert_webm_to_mp4 import convert_webm
            ok, logs, out = _run(convert_webm,
                                  webm_path=webm_in,
                                  output_path=mp4_out,
                                  preset=preset_0,
                                  crf=str(crf_0),
                                  start=start_0 if start_0 else None,
                                  end=end_0 if end_0 else None)
        _show_log(logs, ok)
        if ok and Path(mp4_out).exists():
            st.success(f"Created `{mp4_out}` — ready for Stage 3.")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Format Transcript
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.header("Stage 1 — Format Raw Transcript")
    st.info(
        "Reads `raw_transcript.txt`, converts numbers to spoken words, "
        "computes timestamps at your chosen WPM, and writes `transcript.txt`."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        raw_in  = st.text_input("Raw transcript", value=RAW_TRANSCRIPT)
        fmt_out = st.text_input("Output transcript", value=TRANSCRIPT)
    with col_b:
        wpm_1   = st.number_input("WPM (words per minute)", value=WPM,
                                   min_value=60, max_value=400,
                                   help="Higher = tighter timestamps")
        gap_1   = st.number_input("Gap between segments (seconds)", value=GAP_SEC,
                                   min_value=0, max_value=10)

    raw_exists = Path(raw_in).exists()
    if raw_exists:
        with st.expander("👁  Preview raw_transcript.txt"):
            txt = Path(raw_in).read_text(encoding="utf-8")
            st.text(txt[:3000] + ("…" if len(txt) > 3000 else ""))
    else:
        st.warning(f"File not found: `{raw_in}`")

    if st.button("▶️  Format Transcript", key="btn_fmt", disabled=not raw_exists):
        with st.spinner("Formatting…"):
            from format_transcript import format_transcript
            ok, logs, result = _run(format_transcript,
                                     raw_path=raw_in,
                                     out_path=fmt_out,
                                     wpm=wpm_1,
                                     gap_sec=gap_1)
        _show_log(logs, ok)
        if ok and Path(fmt_out).exists():
            st.success(f"Created `{fmt_out}`")
            with st.expander("👁  Preview transcript.txt"):
                st.text(Path(fmt_out).read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Generate TTS
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.header("Stage 2 — Generate TTS Audio")
    st.info(
        "Loads the Kokoro ONNX model and synthesises speech for each segment "
        "in `transcript.txt`. Produces individual segment MP3s and a combined `final_audio.mp3`."
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("Files")
        t_path   = st.text_input("Transcript file",  value=TRANSCRIPT)
        m_path   = st.text_input("Kokoro model (.onnx)", value=KOKORO_MODEL)
        v_path   = st.text_input("Voices file (.bin)",   value=VOICES_BIN)
        seg_dir  = st.text_input("Segments folder",  value=SEGMENTS_DIR)
        aud_out  = st.text_input("Output audio",     value=FINAL_AUDIO)
    with col_b:
        st.subheader("Voice settings")
        voice_2  = st.selectbox("Voice ID", AVAILABLE_VOICES,
                                  index=AVAILABLE_VOICES.index(TTS_VOICE) if TTS_VOICE in AVAILABLE_VOICES else 0,
                                  help="Choose from available Kokoro voices")
        speed_2  = st.slider("Speed", 0.5, 2.0, TTS_SPEED, 0.05)
        lang_2   = st.selectbox("Language", ["en-us", "en-gb", "ja", "zh", "ko", "fr", "de"],
                                  index=["en-us","en-gb","ja","zh","ko","fr","de"].index(TTS_LANG)
                                  if TTS_LANG in ["en-us","en-gb","ja","zh","ko","fr","de"] else 0)
        gap_2    = st.number_input("Gap between segments (ms)", value=GAP_MS,
                                    min_value=0, max_value=5000, step=100)
    with col_c:
        st.subheader("Readiness")
        for label, fpath in [("Kokoro model", m_path),
                               ("Voices file",  v_path),
                               ("Transcript",   t_path)]:
            ok_f, msg = _file_badge(fpath)
            (st.success if ok_f else st.error)(f"{label}: {msg}")

    can_run = all(Path(p).exists() for p in [m_path, v_path, t_path])
    if not can_run:
        st.warning("Missing files — see Readiness panel above.")

    if st.button("▶️  Generate TTS Audio", key="btn_tts", disabled=not can_run):
        with st.spinner("Generating TTS — this may take a few minutes…"):
            from tts_generator import generate_audio
            ok, logs, out_path = _run(
                generate_audio,
                transcript_path=t_path,
                model_path=m_path,
                voices_path=v_path,
                voice=voice_2,
                speed=speed_2,
                lang=lang_2,
                segments_dir=seg_dir,
                final_audio_path=aud_out,
                gap_ms=gap_2,
            )
        _show_log(logs, ok)
        if ok and out_path and Path(out_path).exists():
            st.success(f"Created `{out_path}`")
            st.audio(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Sync & Merge
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.header("Stage 3 — Sync & Merge")
    st.info(
        "Merges TTS audio with your video. "
        "If durations differ beyond the tolerance, audio tempo is automatically adjusted."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        vid_in   = st.text_input("Input video",  value=VIDEO_FILE)
        aud_in   = st.text_input("TTS audio",    value=FINAL_AUDIO)
        merge_out= st.text_input("Output video", value=OUTPUT_VIDEO)
    with col_b:
        bitrate_3   = st.text_input("Audio bitrate", value=AUDIO_BITRATE)
        sr_3        = st.number_input("Sample rate (Hz)", value=SAMPLE_RATE, step=1000)
        tolerance_3 = st.slider(
            "Auto-adjust tolerance (%)", 1, 30, 10,
            help="If durations differ by less than this %, no tempo adjustment is applied.",
        )

    vid_ok = Path(vid_in).exists()
    aud_ok = Path(aud_in).exists()
    for label, fpath, ok_f in [("Input video", vid_in, vid_ok),
                                 ("TTS audio",   aud_in, aud_ok)]:
        _, msg = _file_badge(fpath)
        (st.success if ok_f else st.warning)(f"{label}: {msg}")

    if st.button("▶️  Sync & Merge", key="btn_merge", disabled=not (vid_ok and aud_ok)):
        with st.spinner("Merging audio and video…"):
            from sync_and_merge import sync_and_merge
            ok, logs, out_path = _run(
                sync_and_merge,
                video_path=vid_in,
                audio_path=aud_in,
                output_path=merge_out,
                audio_bitrate=bitrate_3,
                sample_rate=int(sr_3),
                tolerance=tolerance_3 / 100.0,
            )
        _show_log(logs, ok)
        if ok and out_path and Path(out_path).exists():
            size_mb = Path(out_path).stat().st_size / 1_048_576
            st.success(f"Created `{out_path}` ({size_mb:.1f} MB)")


# ─────────────────────────────────────────────────────────────────────────────
# Status & Config
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.header("Pipeline Status & Configuration")

    st.subheader("File status")
    extra_files = {
        "Segments folder": SEGMENTS_DIR,
    }
    for label, fpath in {**PIPELINE_FILES, **extra_files}.items():
        p = Path(fpath)
        col1, col2, col3 = st.columns([2, 4, 2])
        col1.write(f"**{label}**")
        ok_f, msg = _file_badge(fpath)
        (col2.success if ok_f else col2.error)(msg)
        if ok_f and p.suffix in (".mp3", ".wav"):
            col3.audio(str(p))
        elif ok_f and p.suffix == ".mp4":
            col3.write("🎬 video ready")

    st.divider()
    st.subheader("Active configuration (from `.env`)")
    with st.expander("View all settings"):
        cfg = {
            "WPM": WPM, "GAP_SEC": GAP_SEC, "GAP_MS": GAP_MS,
            "TTS_VOICE": TTS_VOICE, "TTS_SPEED": TTS_SPEED, "TTS_LANG": TTS_LANG,
            "KOKORO_MODEL": KOKORO_MODEL, "VOICES_BIN": VOICES_BIN,
            "RAW_TRANSCRIPT": RAW_TRANSCRIPT, "TRANSCRIPT": TRANSCRIPT,
            "SEGMENTS_DIR": SEGMENTS_DIR, "FINAL_AUDIO": FINAL_AUDIO,
            "OUTPUT_VIDEO": OUTPUT_VIDEO, "VIDEO_FILE": VIDEO_FILE,
            "AUDIO_BITRATE": AUDIO_BITRATE, "SAMPLE_RATE": SAMPLE_RATE,
            "VIDEO_PRESET": VIDEO_PRESET, "VIDEO_CRF": VIDEO_CRF,
        }
        for k, v in cfg.items():
            st.text(f"{k:<20} = {v}")

    st.divider()
    st.subheader("Quick start")
    st.code(
        "# 1. Install dependencies\n"
        "pip install -r requirements.txt\n\n"
        "# 2. Download Kokoro model files\n"
        "#    kokoro-v0_19.onnx and voices.bin → place in this folder\n\n"
        "# 3. Copy .env.example → .env and adjust paths\n"
        "cp .env.example .env\n\n"
        "# 4. Launch the UI\n"
        "streamlit run app.py\n\n"
        "# Or run the CLI pipeline directly\n"
        "python format_transcript.py\n"
        "python tts_generator.py\n"
        "python sync_and_merge.py",
        language="bash",
    )
