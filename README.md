SETUP GUIDE — Text to Audio 
=====================================

TOOL Functions
-------------------
kokoro-onnx     : Converts text to speech (TTS engine)
static-ffmpeg   : Handles audio/video processing 
pydub           : Audio manipulation — silence, concat, MP3 export
soundfile       : Writes WAV audio files
num2words       : Converts numbers to words (e.g. 3.5% -> three point five percent)



INSTALL STEPS
-------------

Step 1 — Install packages (run in terminal)
  pip install kokoro-onnx static-ffmpeg pydub soundfile num2words audioop-lts

Step 2 — Download model files (run in terminal inside project folder)
  python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx', 'kokoro-v0_19.onnx'); print('onnx done'); urllib.request.urlretrieve('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin', 'voices.bin'); print('voices done')"


HOW TO USE
----------
Step 1 — Add your raw text in raw_transcript.txt
         Use --- to separate segments
         First line after --- is heading (will be skipped in audio)

Step 2 — Run format script
         python format_transcript.py
         This will: split segments, convert numbers, add timestamps
         Output: transcript_.txt

Step 3 — Run audio script
         python kokoro.py
         Output: final_audio.mp3 + segments_/ folder


FILES IN THIS FOLDER
--------------------
format_transcript.py  : Converts raw_transcript.txt -> transcript_.txt
kokoro.py        : Generates audio from transcript_.txt
raw_transcript.txt    : Your input (create this manually)
kokoro-v0_19.onnx     : TTS model file (downloaded in Step 3)
voices.bin            : Voice data file (downloaded in Step 3)
