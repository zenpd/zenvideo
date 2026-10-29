# ZenVideo — Zen Studio

Zen Studio has three independent skills:

- **Video**: a web app URL and a narration transcript become a finished demo video (MP4).
- **PPT**: a narration, call transcript or notes become a pitch deck (PPTX) in one of six designs. It works on its own,
  or from a finished video's narration.
- **Animated video**: a narration becomes an animated video (MP4) - motion graphics that show each point as it is
  said, or two colleagues talking it through in an office.

For a video, Zen Studio drafts the on-screen steps with Azure OpenAI, you review them, and it then:

1. generates the voice-over with Kokoro TTS (offline),
2. records the app in a hidden browser while performing the steps in sync with the narration,
3. renders the final video with auto-zoom, click effects, word-highlighted captions and optional background music,
4. runs an automatic audio/video sync check.

Everything runs on your own machine. The only cloud calls are to Azure OpenAI: drafting the video script, writing a
deck's story, and planning an animated video's scenes.

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
5. Optional: **Create pitch deck** on the finished video's page opens the PPT skill with the video's narration filled
   in. See [Making a pitch deck](#making-a-pitch-deck).

**Record again** re-records a finished video, for example after the app changed. **Retry** restarts a failed one.

### How narration and actions fit together

The video should feel like a person presenting the product, not a voice reading out clicks. The draft follows this
pattern, and hand-written scripts should too:

```
natural narration  →  the word that names the step  →  the action happens  →  the narration describes the result
```

- **Your narration is kept word for word.** Stage directions (`Click "Approve"`, `Send the message.`) are never spoken;
  they become actions.
- **A part with only directions gets a short bridge sentence** that says the purpose, and its actions are anchored to
  a word in it with `at_word`:

  | Transcript says | Spoken | Action lands on |
  |---|---|---|
  | `click Agents` | "Let's look at the specialist agents behind the workflow." | "agents" |
  | filling a form | "I'll enter the policyholder and incident details." | while it is spoken |
  | `search for the claim` | "I'll find the claim we just submitted." | "find" |
  | send a prompt, wait for the AI | "Let's ask the assistant to raise a purchase requisition." | "ask" |
  | a slow step | "The document is being analyzed." | then waits for the result |

- **Typed values are not read aloud.** Say what is being entered ("the incident details"), not the values.
- **Uploads:** write the file's full path in the transcript, for example
  `[Upload C:/Users/me/claim-evidence.pdf in Supporting Documents]`. Only an explicit path produces an upload, and the
  file must exist on the computer running Zen Studio.

See `demo/examples/p2p.yaml` (segment `raise-pr-type`) for a worked example.

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
- Actions: `click`, `fill`, `press`, `hover`, `wait_for`, `scroll`, `scroll_to`, `select`, `upload`.
  - `at_word` makes an action land on a spoken word.
  - `until_word` makes a `scroll_to` last until a later word.
  - `nth: last` targets the newest element, for repeated chat buttons.
  - `select: { role: combobox, name: Claim type, option: "Motor / Vehicle" }` picks an option in a dropdown.
  - `upload: { text: "Click to upload", path: C:/files/claim.pdf }` attaches a file; the target (the visible upload
    area) is optional.
  - Native date fields: `fill: { label: Incident date, value: "2026-09-25" }`. The date is filled directly, so no
    calendar clicks are needed.

Apps behind a login: set `storage_state: auth/<name>.json` in the script, then run
`python -m demo auth <script>` once to sign in and save the session. The `auth/` folder is git-ignored.

---

## Making a pitch deck

Open **Pitch decks** → **New deck** (or **Create pitch deck** on a finished video). At the top give the product name and
the app's link; below, the narration - either one is enough, both make the strongest deck. Pick a design and click
**Generate deck**. A deck from text takes about 15 seconds; with a link, about 1-2 minutes (the app is explored once).

- **Input:** a video narration, a call or meeting transcript (speaker names, timestamps, SRT/VTT subtitles and filler
  words are cleaned out), or notes. Stage directions such as `Click "Approve"` are ignored.
- **Deck brief:** choose who it's for (Auto, Executives, Investors, Customers, Technical team, Internal team), the length
  (Short 5–7, Standard 8–11, Detailed 12–15 slides) and an optional focus such as "compliance and audit". The audience
  decides what leads and what's left out. Changing the brief on a deck's page rewrites its story (one AI call).
- **Custom:** pick **Custom** under "Who is it for?" and write your own instructions, for example "Slide 1: a pie chart
  of … with these numbers; slide 2: a bar chart …; keep it to 6 slides". The AI follows them (slide 1 is the first slide
  after the title slide), and the deck page lists each request as done, not done or not possible. Code checks the
  AI's claims: a chart must actually be on the slide named, chart values must appear in your text or instructions,
  and requests the deck can't carry out (logos, images, animations, fonts, colours) are always reported as not
  possible.
- **Charts:** pie, doughnut, bar, column and line charts are native PowerPoint charts (right-click → Edit Data), in
  the design's colours. The AI also adds them on its own when the text gives three or more comparable numbers.
- **The story:** one Azure OpenAI call plans the deck. It picks the slide types that suit the content (statement, stats,
  problem, before/after, process, feature grid, feature focus, quote, benefits) and writes them, and longer decks get an
  agenda. The AI only uses facts from the text. Code then removes any figure the text doesn't state, including
  percentages the model worked out itself.
- **Designs:** Zen Studio plus five designs based on the sample decks in `ppt/assets/samples/` (Consulting, Startup
  Pitch Dark, Editorial Report, QBR Dashboard, Project Kickoff). Icons come from Windows' Segoe Fluent Icons font and are
  embedded as images.
- **Cost:** about 2–3k input and 1.5k output tokens per story (about $0.003 with gpt-4.1-mini). Switching design reuses
  the story, so it's free. **Write a new story** asks the AI again. Each deck page shows its calls, tokens and estimated
  cost. Set `AZURE_OPENAI_PRICE_INPUT` / `AZURE_OPENAI_PRICE_OUTPUT` (USD per 1M tokens) for your rates, and
  `AZURE_OPENAI_PPT_DEPLOYMENT` to use a different deployment for decks.
- **From the app's link:** give the link (with or without a narration). A hidden browser goes through the app once,
  like a person: page by page through its navigation (clicked inside the app, so single-page apps without deep links
  work), and on each page its tabs and option buttons, accordions and the first item of a list (its detail view). It
  waits for static and dynamic pages to settle - network, "Loading…", spinners and skeletons, changing text, lazy
  content - with extra patience for an app whose server is waking up. Each distinct screen is kept with its text and
  how it was reached; the AI writes the story from that tour, the best screens (results first) become screenshot
  slides, and each screenshot slide's notes say where to show it in the app. Numbers on the app's screens are treated
  as demo data: they stay in the screenshots, never in the slide text. With a narration too, the narration leads.
- **Try the app's forms (off by default, demo/test apps only):** also clicks the main button of forms that are already
  filled in, once, to capture the result (e.g. a payment's AI routing). Nothing is typed. Buttons that could change or
  share data or end the session (delete, save, pay, send, regenerate, log out, …) are never clicked in either mode.
  Apps behind a sign-in: only what is visible without signing in is explored.

From the command line:

```powershell
python -m ppt narration.txt --template consulting          # -> narration.pptx
python -m ppt call.vtt --template pitch-dark --title "ShiftBoard"
python -m ppt --url https://your-app.example.com --try-forms --out app.pptx    # from the app alone
```

---

## Making an animated video

**Animated videos → New animated video**: write or paste a narration (about 300 words make two minutes), pick a style,
a theme and voices, and click **Make video**. A 2-minute video takes about 4-6 minutes and one AI call (well under a
cent). There are two styles:

- **Explainer** - motion graphics, described below.
- **Hi-tech** - the explainer's scenes as glowing kinetic motion graphics (dark scenes with drifting glows, a moving
  perspective grid, kinetic headlines, counters, steps lighting up) with WebGL shader transitions between scenes
  (domain warp, cinematic zoom, light leak, whip pan, glitch, ...), rendered by [HyperFrames](https://github.com/heygen-com/hyperframes)
  (HeyGen's open-source HTML-to-video engine, Apache 2.0 - free, runs locally). One-time setup: `npm install` in
  `explainer/hyperframes` (versions pinned there). Telemetry and update checks are switched off, GSAP and the shaders
  are copied into each project (no CDN), and it uses the FFmpeg and headless Chrome the pipeline already has. Slower to
  render than the other styles: about 6-8x the video's length (a 90-second video takes about 10 minutes).
- **Conversation** - two colleagues talk the narration through at a desk in an office: one asks the questions a viewer
  would ask, the other explains. One AI call writes the dialogue from the narration (every line fact-checked like the
  explainer's scenes: figures and names only from the narration and the two people's own names). Pick the two people
  from six presets (each with their own look and voice; any Kokoro voice can be chosen instead) and the length.
  - **Lip-sync** from the voice model itself: Kokoro's exact phoneme timings become mouth shapes (closed, open, wide,
    round, teeth, lip under teeth), so no extra lip-sync tool is needed.
  - **Acting**: gestures fitted to each line (explaining, listing, open hands for questions, thinking, pointing at the
    wall screen, a wave hello), head movement and nods on the speech's beats, the listener tilting towards the speaker
    and nodding, blinks, both glancing at the screen when it changes.
  - **The wall screen** between them shows the key points (a title, up to three points, or a figure), each appearing
    as it is said; the camera opens on the office with the video's title, cuts between the speakers and pulls back to
    take in the screen, and name tags introduce the two people. The office follows the theme (night, day, sunset).

The explainer style:

- **Scenes:** one Azure OpenAI call splits the narration into scenes and decides what each shows: a title, a
  statement, key points, numbers, steps, before/after, a chart, an icon grid, a quote and a closing. Everything on
  screen is checked in code: figures and names only from the narration (no chart from numbers nobody said), a call
  to action only when the narration makes it, short scenes merged so nothing flashes by.
- **In sync with the voice:** Kokoro voices each scene with exact word timings, and every point, step or number
  animates in just as its words are said (each item has a "cue" from the voice-over).
- **Voice-over:** *Word for word* speaks your narration exactly; *AI tightens it* rewrites it to a target length,
  keeping its facts.
- **Look:** four themes (Midnight, Daylight, Sunrise, Forest), any Kokoro voice and speed, captions switchable,
  always on or off, background music on or off. Changing any of these and clicking **Remake video** reuses the scene
  plan: no AI call. **New scene plan** asks the AI again.
- **How it is drawn:** the scenes are an HTML page (`player.html`) whose animations all run from one clock, so every
  frame is taken exactly (no screen recording) in a few hidden browsers in parallel. **Open the animation in a
  browser** plays it live with its voice-over.

From the command line:

```powershell
python -m explainer narration.txt --title "Zen Studio" --theme midnight --voice af_sky
python -m explainer notes.txt --tighten --seconds 90 --captions burned --out build/explainers/short
python -m explainer narration.txt --style conversation --cast maya daniel --seconds 120 --theme daylight
python -m explainer script.txt --style hitech --tighten --seconds 85 --voice bf_emma --logo logo.png --brand "Cynergy Bank"
```

---

## Project layout

| Path | What it is |
|---|---|
| `api/main.py` | FastAPI app; serves the Zen Studio UI from `studio/dist` |
| `api/studio.py` | Video skill API (`/api/studio`): jobs, drafting, review, production, settings, a video's narration |
| `studio/` | Zen Studio web UI (React + Vite) |
| `demo/` | Video skill pipeline: `draft` (Azure script), `tts`, `record`, `capture`, `retime`, `render`, `effects`, `check` |
| `ppt/` | PPT skill: `source` (text cleaning), `writer` (story), `designs/`, `capture` (explores an app's link), `service`, `api` (`/api/ppt`) |
| `explainer/` | Animated video skill: `planner` (explainer scenes), `dialogue` (conversation and cast), `voice` (voice-over, lip-sync and timeline), `web/` (the players: `player.*` scenes, `office.*` conversation), `render` (frames → MP4), `service`, `api` (`/api/explainer`) |
| `demo/examples/` | Example scripts, transcripts and a sample app |
| `build/studio/<job id>/` | Each video job: `job.json`, `job.log`, `demo.yaml`, `en/final.mp4` … (git-ignored) |
| `build/decks/<deck id>/` | Each pitch deck: `job.json`, `narration.txt`, `pages/` + `pages.json` (the explored app), `deck.json` (the story), `deck*.pptx` (git-ignored) |
| `build/explainers/<id>/` | Each animated video: `job.json`, `narration.txt`, `plan.json` (the scenes or dialogue), `timeline.json`, `audio/`, `player.html`, `final.mp4`, `final.srt` (git-ignored) |
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
