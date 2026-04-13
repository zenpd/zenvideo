"""
Stage 0 (optional) — Convert WebM screen recording to MP4
Useful when input video comes from a browser/screen recorder as .webm.
 
CLI usage:
  python convert_webm_to_mp4.py input.webm [output.mp4]
 
Imported usage:
  from convert_webm_to_mp4 import convert_webm
  convert_webm("recording.webm", log=my_log_fn)
"""
 
import os
import sys
import subprocess
import static_ffmpeg
static_ffmpeg.add_paths()
 
from config import VIDEO_PRESET, VIDEO_CRF
 
 
def convert_webm(
    webm_path: str,
    output_path: str = None,
    preset: str = None,
    crf: str = None,
    start: str = None,   # e.g. "00:02:30"
    end: str = None,     # e.g. "00:10:00"
    log=print,
) -> str | None:
    """
    Convert a WebM file to MP4 (H.264 + AAC).
 
    Returns:
        output_path on success, None on failure.
    """
    preset      = preset      or VIDEO_PRESET
    crf         = str(crf)    if crf is not None else VIDEO_CRF
    output_path = output_path or os.path.splitext(webm_path)[0] + ".mp4"
 
    if not os.path.exists(webm_path):
        log(f"ERROR: File not found: {webm_path}")
        return None
 
    log(f"Converting {webm_path} → {output_path}  (preset={preset}, crf={crf})")
 
    cmd = ["ffmpeg"]
    if start:
        cmd += ["-ss", start]
    cmd += ["-i", webm_path]
    if end:
        cmd += ["-to", end]
    cmd += [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", crf,
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path,
    ]
 
    result = subprocess.run(cmd, text=True, capture_output=True)
 
    if result.returncode == 0:
        log(f"Done! Created: {output_path}")
        return output_path
    else:
        log(f"ERROR (ffmpeg exited {result.returncode}):\n{result.stderr[-800:]}")
        return None
 
 
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_webm_to_mp4.py <input.webm> [output.mp4]")
        sys.exit(1)
    webm  = sys.argv[1]
    out   = sys.argv[2] if len(sys.argv) > 2 else None
    convert_webm(webm, out)