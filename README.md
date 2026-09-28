# ZenVideo — Zen Studio

Zen Studio turns a web app URL and a narration transcript into a finished demo video (MP4). It drafts the on-screen
steps with Azure OpenAI, you review them, and it then:

1. generates the voice-over with Kokoro TTS (offline),
2. records the app in a hidden browser while performing the steps in sync with the narration,
3. renders the final video with auto-zoom, click effects, word-highlighted captions and optional background music,
4. runs an automatic audio/video sync check.

Everything runs on your own machine. The only cloud call is Azure OpenAI, for drafting the script.

---

## Requirements

| What | Version / notes |
|---|---|
| Windows 10 or 11 | Required. The recorder uses Windows APIs (full-screen mode, window focus, speaker preview). |
| Python | 3.11 or newer (developed on 3.14) |
| Node.js | 18 or newer, only to build the Zen Studio web UI |
| Disk space | About 1.5 GB (Python packages, browser, voice model); each video's working files take 1–2 GB |
| Azure OpenAI | An endpoint, key and chat deployment, for drafting scripts |

No Docker or WSL needed.

---

## Setup

Run everything from the project folder.

### 1. Python environment and packages

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Browser for recording

```powershell
python -m playwright install chromium
```

### 3. Voice model files

Download the Kokoro model and voices into the project folder (about 350 MB):

```powershell
python -c "import urllib.request as u; b='https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/'; u.urlretrieve(b+'kokoro-v0_19.onnx','kokoro-v0_19.onnx'); u.urlretrieve(b+'voices.bin','voices.bin'); print('done')"
```

On first use the pipeline creates `models/kokoro-v0_19.timed.onnx`. It's a copy of the model that also reports
word timings, and it makes captions and word-timed clicks line up exactly. It is built automatically and needs no
download.

ffmpeg is fetched automatically by `static-ffmpeg` the first time it is needed. If your network blocks GitHub
downloads, get the model files and ffmpeg from someone who has them.

### 4. Configuration

```powershell
copy .env.example .env
```

Open `.env` and fill in the Azure OpenAI section:

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>
AZURE_OPENAI_API_VERSION=2024-08-01-preview
```

`.env` is git-ignored. Never commit keys.

### 5. Build the web UI

```powershell
cd studio
npm install
npm run build
cd ..
```

### 6. Start Zen Studio

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8010
```

Open **http://127.0.0.1:8010**. The Settings page shows whether Azure OpenAI is connected and whether word timing
is "Exact".

Background music is optional: put `.mp3` files in `music/` and they appear in the New video form.

---

## Making a video

1. **New video**: paste the app URL and the transcript, then submit.
   - Any URL this computer can open works, including `http://localhost:3000`. A local app must stay running
     until the recording finishes.
   - In the transcript, write the narration plus stage directions such as `Click "Approve"`,
     `Then, in the chat box, enter: "..."` or `Send the message.` Separate segments with `---`. See
     `demo/examples/p2p_transcript.txt` for a full example.
2. **Review**: check the drafted steps, or edit the script in the *Script (YAML)* tab, then click
   **Start recording**.
3. Wait for narration → recording → render → sync check. The job page shows live progress and a log.
4. Download `final.mp4` (plus `final.srt` captions) from the job page, or open it from the Library.

**Record again** re-records a finished video, for example after the app changed. **Retry** restarts a failed one.

### Recording modes (Settings → Recording)

- **Background** (default): the app runs in a hidden browser. You can keep using the computer, and nothing plays
  on the speakers.
- **Full screen**: the app runs full screen and the monitor is captured. Don't touch the mouse or keyboard until it
  finishes. It stops safely if another window comes to the front.

Either way the output is 1920×1080 at a constant 30 fps.

---

## Command line (without the UI)

The same pipeline runs from a YAML script:

```powershell
python -m demo validate demo/examples/sample.yaml   # check the script
python -m demo all      demo/examples/sample.yaml   # tts -> record -> render -> check
```

Individual stages are `tts`, `record`, `render` and `check`. Output goes to `build/<script name>/en/`
(`final.mp4`, `final.srt`, `check.json`, plus the working files). `demo/examples/sample.yaml` records the bundled
`sample_app.html` and is the quickest end-to-end test.

Useful script keys (see `demo/examples/p2p.yaml`):

- `capture: background | screen`: the recording mode.
- `pacing.narration_scroll: 0`: stop the page from scrolling on its own while the narration continues.
- Actions: `click`, `fill`, `press`, `hover`, `wait_for`, `scroll`, `scroll_to`.
  - `at_word` makes an action land on a spoken word.
  - `until_word` makes a `scroll_to` last until a later word.
  - `nth: last` targets the newest element, for repeated chat buttons.

Apps behind a login: set `storage_state: auth/<name>.json` in the script, then run
`python -m demo auth <script>` once to sign in and save the session. The `auth/` folder is git-ignored.

---

## Project layout

| Path | What it is |
|---|---|
| `api/main.py` | FastAPI app; serves the Zen Studio UI from `studio/dist` |
| `api/studio.py` | Zen Studio API: jobs, drafting, review, production, settings |
| `studio/` | Zen Studio web UI (React + Vite) |
| `demo/` | The pipeline: `draft` (Azure script), `tts`, `record`, `capture`, `retime`, `render`, `effects`, `check` |
| `demo/examples/` | Example scripts, transcripts and a sample app |
| `build/studio/<job id>/` | Each Zen Studio job: `job.json`, `job.log`, `demo.yaml`, `en/final.mp4` … (git-ignored) |
| `music/` | Background music tracks (`.mp3`) |
| `models/` | Generated timed voice model, optional Whisper model (git-ignored) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named static_ffmpeg` (or another module) | Activate `.venv` and run `pip install -r requirements.txt` again. |
| Settings says Azure OpenAI "Not configured" | Fill the four `AZURE_OPENAI_*` values in `.env` and restart the server. |
| Settings says word timing "Estimated" | `pip install onnx`, then restart the server. |
| `ERR_NAME_NOT_RESOLVED` when recording | The app URL is not reachable from this computer. Check that it opens in a browser here. |
| A step fails with "no visible element for …" | The drafted label doesn't match the app. Fix the name in the Review step's YAML, or redraft. |
| Full-screen take stops with "lost focus" | Another window came to the front. Use Background mode or leave the computer alone. |
| Changes to Python code have no effect | Restart the uvicorn server; running jobs keep the old code. |

---

## Legacy tools

These scripts come from before Zen Studio and still work on their own:

- `python format_transcript.py`: formats `raw_transcript.txt` into `transcript.txt`.
- `python kokoro.py`: turns `transcript.txt` into `final_audio.mp3`.
- `streamlit run app.py`: the older step-by-step Streamlit UI (WebM→MP4, format, TTS, sync & merge).
