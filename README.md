ZenVideoMaker — TTS Audio/Video Pipeline
=========================================

Turns a text transcript into a narrated video: TTS narration (Kokoro ONNX),
optional browser-action recording (Playwright), and FFmpeg-based sync/merge.
Runs as a CLI, a Streamlit UI, or a FastAPI + React UI — same pipeline modules
underneath.

TOOL Functions
-------------------
kokoro-onnx     : Converts text to speech (TTS engine)
static-ffmpeg   : Handles audio/video processing
pydub           : Audio manipulation — silence, concat, MP3 export
soundfile       : Writes WAV audio files
num2words       : Converts numbers to words (e.g. 3.5% -> three point five percent)
playwright      : Drives a real browser to record UI-action demos
openai (Azure)  : Converts narration text into concrete browser actions for Stage 4


INSTALL STEPS
-------------

Step 1 — Install packages (run in terminal)
  pip install -r requirements.txt
  python -m playwright install chromium

Step 2 — Download model files (run in terminal inside project folder)
  python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx', 'kokoro-v0_19.onnx'); print('onnx done'); urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin', 'voices.bin'); print('voices done')"

Step 3 — Configure
  cp .env.example .env
  # then edit .env — paths, TTS voice/speed, and Azure OpenAI creds if using Stage 4


HOW TO USE — CLI
-----------------
Step 1 — Add your raw text in raw_transcript.txt
         Use --- to separate segments
         First line after --- is heading (will be skipped in audio)

Step 2 — Run format script
         python format_transcript.py
         This will: split segments, convert numbers, add timestamps
         Output: transcript.txt

Step 3 — Run audio script
         python tts_generator.py
         Output: final_audio.mp3 + segments/ folder

Step 4 — Merge with a video
         python sync_and_merge.py
         Output: output.mp4


HOW TO USE — Web UI (FastAPI + React)
--------------------------------------
  uvicorn api.main:app --reload --port 8000     # backend, http://localhost:8000
  cd ui && npm install && npm run dev            # frontend, http://localhost:5173

Each stage (WebM→MP4, Format Transcript, Generate TTS, Sync & Merge, Browser
Recording) can be run independently from its own card — no fixed ordering.
Live logs stream over SSE while a stage runs.


HOW TO USE — Streamlit UI
---------------------------
  streamlit run app.py                           # http://localhost:8501


PIPELINE STAGES
----------------
Stage 0  Convert WebM → MP4              convert_webm_to_mp4.py
Stage 1  Format Transcript               format_transcript.py
Stage 2  Generate TTS Audio              tts_generator.py
Stage 3  Sync & Merge                    sync_and_merge.py
Stage 4  Browser Recording               generate_recording.py       (Playwright + Azure OpenAI)
Stage 5  Screen Recorder                 screen_recorder.py          (FFmpeg avfoundation, macOS)
Stage 6  WebM + Transcript → Synced MP4  webm_transcript_pipeline.py (one-shot: Stage 0+2+3 combined)

Stage 5 records your own screen + mic straight to a .webm — an alternative to
Stage 4's automated browser recording. Stage 6 skips the intermediate files
and turns that .webm plus a transcript directly into a synced MP4.

Stage 5 needs Screen Recording permission for whatever process runs ffmpeg
(your terminal app, or the venv's bundled ffmpeg binary the first time it's
used) — System Settings → Privacy & Security → Screen Recording. Without it,
avfoundation capture can silently hang instead of erroring.


FILES IN THIS FOLDER
--------------------
config.py                    : Central settings, reads from .env
format_transcript.py         : Converts raw_transcript.txt -> transcript.txt
tts_generator.py             : Generates audio from transcript.txt
sync_and_merge.py            : Merges TTS audio with a video (Stage 3)
generate_recording.py        : Drives a browser to record a narrated UI demo (Stage 4)
cursor_fx.py                 : Visible synthetic cursor/highlight/ripple overlay for recordings
convert_webm_to_mp4.py       : WebM → MP4 conversion (Stage 0)
screen_recorder.py           : Screen + mic capture via FFmpeg avfoundation (Stage 5)
webm_transcript_pipeline.py  : One-shot WebM+transcript → synced MP4 (Stage 6)
app.py                       : Streamlit UI
api/main.py                  : FastAPI backend for the React UI
ui/                          : React + Vite frontend
raw_transcript.txt           : Your input (create this manually)
kokoro-v0_19.onnx            : TTS model file (downloaded above)
voices.bin                   : Voice data file (downloaded above)
