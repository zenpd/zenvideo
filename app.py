"""
TTS Audio/Video Pipeline — Streamlit UI
Stage-wise interface for: WebM→MP4 | Format Transcript | Generate TTS | Sync & Merge |
Browser Recording | Screen Recorder | One-Shot WebM+Transcript Sync

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
    KOKORO_MODEL, VOICES_BIN, TTS_VOICE, TTS_SPEED, TTS_LANG,
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
    "`0: WebM → MP4` → `1: Format Transcript` → `2: Generate TTS` → `3: Sync & Merge` — "
    "plus independent stages `4: Browser Recording`, `5: Screen Recorder`, `6: One-Shot Sync`"
)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab_status = st.tabs([
    "🎥  Stage 0 — WebM → MP4",
    "📝  Stage 1 — Format Transcript",
    "🔊  Stage 2 — Generate TTS",
    "🎬  Stage 3 — Sync & Merge",
    "🌐  Stage 4 — Browser Recording",
    "🖥️  Stage 5 — Screen Recorder",
    "🧩  Stage 6 — One-Shot Sync",
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
                                  crf=str(crf_0))
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
        voice_2  = st.text_input("Voice ID", value=TTS_VOICE,
                                  help="e.g. af_sky, af_bella, am_adam")
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

            st.subheader("🎬 Output Video")
            st.video(str(out_path))


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: Browser Recording
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.header("Stage 4 — Browser Recording")
    st.info(
        "Drives a real Chromium window (Playwright) through a narrated demo: for each "
        "transcript segment, Azure OpenAI turns the narration into concrete UI actions "
        "(click/type/scroll) against the page's currently visible elements, and the "
        "whole session is screen-recorded to a `.webm`. Independent of Stages 0-3 — "
        "run it any time. A visible browser window will open on your screen."
    )

    azure_ok = all(os.environ.get(k) for k in
                   ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"))
    if not azure_ok:
        st.warning(
            "Azure OpenAI credentials not found in the environment "
            "(`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_DEPLOYMENT`) — "
            "set them in `.env` before running this stage."
        )

    col_a, col_b = st.columns(2)
    with col_a:
        url_4 = st.text_input("Target URL", value="", placeholder="https://…",
                               help="The page Playwright will open and interact with")
        transcript_4 = st.text_input("Transcript (narration script)", value=RAW_TRANSCRIPT,
                                      key="t4_transcript")
    with col_b:
        output_4 = st.text_input("Output .webm path", value="video-recordings/recording.webm",
                                  key="t4_output")

    transcript_4_ok = Path(transcript_4).exists()
    if not transcript_4_ok:
        st.warning(f"Transcript not found: `{transcript_4}`")

    can_run_4 = bool(url_4.strip()) and transcript_4_ok
    if st.button("▶️  Start Browser Recording", key="btn_stage4", disabled=not can_run_4):
        with st.spinner("Recording — a Chromium window will open on your screen…"):
            from generate_recording import generate_recording
            ok, logs, out_path = _run(
                generate_recording,
                url=url_4,
                transcript_path=transcript_4,
                output_path=output_4,
            )
        _show_log(logs, ok)
        if ok and out_path and Path(out_path).exists():
            st.success(f"Created `{out_path}`")
            st.video(str(out_path))


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5: Screen Recorder
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.header("Stage 5 — Screen Recorder")
    st.info(
        "Captures your own screen + microphone straight to a `.webm`/`.mp4` via FFmpeg "
        "avfoundation (macOS) — an alternative to Stage 4's automated browser recording. "
        "Requires Screen Recording permission for the process running ffmpeg "
        "(System Settings → Privacy & Security → Screen Recording), or capture can "
        "silently hang instead of erroring."
    )

    from screen_recorder import list_devices, start_recording, stop_recording, recording_status

    status_5 = recording_status()
    is_recording = status_5.get("active", False)

    col_status, col_refresh = st.columns([4, 1])
    with col_status:
        if is_recording:
            st.error(f"🔴 Recording in progress (PID {status_5.get('pid')})")
        else:
            st.success("⚪ Not recording")
    with col_refresh:
        if st.button("🔄 Refresh", key="btn_stage5_refresh"):
            st.rerun()

    if st.button("🔍  List devices", key="btn_stage5_devices"):
        ok, logs, devices = _run(list_devices)
        _show_log(logs, ok)
        if ok:
            st.session_state["stage5_devices"] = devices

    devices_5 = st.session_state.get("stage5_devices")
    video_choices = {f'{d["idx"]} — {d["name"]}': d["idx"] for d in devices_5["video"]} if devices_5 else {}
    audio_choices = {f'{d["idx"]} — {d["name"]}': d["idx"] for d in devices_5["audio"]} if devices_5 else {}

    col_a, col_b = st.columns(2)
    with col_a:
        output_5 = st.text_input("Output path", value="recording.webm", key="t5_output",
                                  disabled=is_recording)
        if video_choices:
            video_idx_5 = video_choices[st.selectbox("Video device", list(video_choices),
                                                       key="t5_video_sel", disabled=is_recording)]
        else:
            video_idx_5 = st.text_input("Video device index", value="1", key="t5_video_idx",
                                         help="List devices above to see indices — \"1\" is usually \"Capture screen 0\"",
                                         disabled=is_recording)
        if audio_choices:
            audio_idx_5 = audio_choices[st.selectbox("Audio device", list(audio_choices),
                                                       key="t5_audio_sel", disabled=is_recording)]
        else:
            audio_idx_5 = st.text_input("Audio device index", value="0", key="t5_audio_idx",
                                         disabled=is_recording)
    with col_b:
        framerate_5 = st.number_input("Framerate (fps)", value=30, min_value=1, max_value=60,
                                       key="t5_framerate", disabled=is_recording)
        bitrate_5 = st.text_input("Audio bitrate", value=AUDIO_BITRATE, key="t5_bitrate",
                                   disabled=is_recording)

    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("⏺️  Start Recording", key="btn_stage5_start", disabled=is_recording,
                     use_container_width=True):
            ok, logs, result = _run(
                start_recording,
                output_path=output_5,
                video_idx=str(video_idx_5),
                audio_idx=str(audio_idx_5),
                framerate=int(framerate_5),
                audio_bitrate=bitrate_5,
            )
            _show_log(logs, ok and not (result or {}).get("error"))
            st.rerun()
    with col_stop:
        if st.button("⏹️  Stop Recording", key="btn_stage5_stop", disabled=not is_recording,
                     use_container_width=True):
            ok, logs, result = _run(stop_recording)
            _show_log(logs, ok and not (result or {}).get("error"))
            st.rerun()

    if not is_recording and Path(output_5).exists():
        st.subheader("Last recording")
        p5 = Path(output_5)
        if p5.suffix.lower() in (".mp4",):
            st.video(str(p5))
        else:
            st.caption(f"`{p5}` — {p5.stat().st_size/1_048_576:.1f} MB "
                       f"(convert to `.mp4` via Stage 0 to preview here)")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6: One-Shot WebM + Transcript → Synced MP4
# ─────────────────────────────────────────────────────────────────────────────
with tab6:
    st.header("Stage 6 — WebM + Transcript → Synced MP4 (one-shot)")
    st.info(
        "Skips the intermediate files: takes a raw `.webm` recording (from Stage 4 or 5) "
        "plus a transcript, generates TTS per segment, places each segment at its own "
        "transcript timestamp (no uniform tempo-stretching), and merges straight to a "
        "synced MP4 — combining Stages 0 + 2 + 3 into one run."
    )

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("Files")
        webm_6 = st.text_input("Input .webm", value="recording.webm", key="t6_webm")
        transcript_6 = st.text_input("Transcript (raw or formatted)", value=RAW_TRANSCRIPT,
                                      key="t6_transcript")
        output_6 = st.text_input("Output .mp4", value="output_synced.mp4", key="t6_output")
    with col_b:
        st.subheader("Voice settings")
        voice_6 = st.text_input("Voice ID", value=TTS_VOICE, key="t6_voice")
        speed_6 = st.slider("Speed", 0.5, 2.0, TTS_SPEED, 0.05, key="t6_speed")
        lang_6 = st.selectbox("Language", ["en-us", "en-gb", "ja", "zh", "ko", "fr", "de"],
                               index=["en-us", "en-gb", "ja", "zh", "ko", "fr", "de"].index(TTS_LANG)
                               if TTS_LANG in ["en-us", "en-gb", "ja", "zh", "ko", "fr", "de"] else 0,
                               key="t6_lang")
        wpm_6 = st.number_input("WPM (for raw transcripts)", value=WPM, min_value=60, max_value=400,
                                 key="t6_wpm")
        gap_6 = st.number_input("Gap between segments (seconds)", value=GAP_SEC,
                                 min_value=0, max_value=10, key="t6_gap")
    with col_c:
        st.subheader("Encoding")
        bitrate_6 = st.text_input("Audio bitrate", value=AUDIO_BITRATE, key="t6_bitrate")
        sr_6 = st.number_input("Sample rate (Hz)", value=SAMPLE_RATE, step=1000, key="t6_sr")
        preset_6 = st.selectbox("Video preset", ["fast", "medium", "slow"],
                                 index=["fast", "medium", "slow"].index(VIDEO_PRESET),
                                 key="t6_preset")
        crf_6 = st.slider("CRF quality (lower = better)", 0, 51, int(VIDEO_CRF), key="t6_crf")

    webm_6_ok = Path(webm_6).exists()
    transcript_6_ok = Path(transcript_6).exists()
    for label, fpath, ok_f in [("Input .webm", webm_6, webm_6_ok),
                                ("Transcript", transcript_6, transcript_6_ok)]:
        _, msg = _file_badge(fpath)
        (st.success if ok_f else st.warning)(f"{label}: {msg}")

    can_run_6 = webm_6_ok and transcript_6_ok
    if st.button("▶️  Run One-Shot Sync", key="btn_stage6", disabled=not can_run_6):
        with st.spinner("Converting, generating TTS, and syncing — this may take a while…"):
            from webm_transcript_pipeline import webm_to_mp4
            ok, logs, out_path = _run(
                webm_to_mp4,
                webm_path=webm_6,
                transcript_path=transcript_6,
                output_path=output_6,
                voice=voice_6,
                speed=speed_6,
                lang=lang_6,
                wpm=int(wpm_6),
                gap_sec=int(gap_6),
                audio_bitrate=bitrate_6,
                sample_rate=int(sr_6),
                video_preset=preset_6,
                video_crf=str(crf_6),
            )
        _show_log(logs, ok)
        if ok and out_path and Path(out_path).exists():
            size_mb = Path(out_path).stat().st_size / 1_048_576
            st.success(f"Created `{out_path}` ({size_mb:.1f} MB)")
            st.video(str(out_path))


# ─────────────────────────────────────────────────────────────────────────────
# Status & Config
# ─────────────────────────────────────────────────────────────────────────────
with tab_status:
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
