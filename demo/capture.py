"""Constant-frame-rate capture: the whole screen (ffmpeg ddagrab) or one hidden browser page (Chrome screencast)."""

import base64
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from demo import media


class CaptureError(RuntimeError):
    pass


class ScreenCapture:
    def __init__(self, out: Path, fps: int, monitor: int = 0):
        self.out = out
        self.fps = fps
        self.monitor = monitor
        self.progress = out.with_suffix(".progress")
        self.logfile = out.with_suffix(".ffmpeg.log")
        self.proc: subprocess.Popen | None = None

    def start(self, ready_timeout: float = 15.0) -> None:
        for p in (self.out, self.progress):
            p.unlink(missing_ok=True)
        src = f"ddagrab=output_idx={self.monitor}:framerate={self.fps}:draw_mouse=0,hwdownload,format=bgra"
        cmd = [
            media.FFMPEG, "-hide_banner", "-y",
            "-f", "lavfi", "-i", src,
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p",
            "-g", str(self.fps), "-fps_mode", "cfr", "-r", str(self.fps),
            "-video_track_timescale", str(self.fps * 1000),
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof", "-f", "mp4",
            "-progress", str(self.progress), "-stats_period", "0.25",
            str(self.out),
        ]
        self._log = open(self.logfile, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._log)

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise CaptureError(f"ffmpeg capture exited immediately; see {self.logfile}:\n{self._tail()}")
            if self._frames() >= 5:
                return
            time.sleep(0.1)
        self.stop()
        raise CaptureError(f"screen capture produced no frames within {ready_timeout:.0f}s; see {self.logfile}")

    def _frames(self) -> int:
        try:
            found = re.findall(r"^frame=(\d+)", self.progress.read_text(encoding="utf-8", errors="replace"), re.M)
        except OSError:
            return 0
        return int(found[-1]) if found else 0

    def _tail(self) -> str:
        try:
            return self.logfile.read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            return ""

    def stop(self, timeout: float = 30.0) -> dict:
        if self.proc is None:
            return {}
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
            except OSError:
                pass
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(10)
        self._log.close()
        self.proc = None
        text = self._tail()
        dup = re.findall(r"dup=(\d+)", text)
        drop = re.findall(r"drop=(\d+)", text)
        return {"dup": int(dup[-1]) if dup else None, "drop": int(drop[-1]) if drop else None}

    def remux_mp4(self, out_mp4: Path) -> None:
        media.run_ffmpeg(["-i", self.out, "-map", "0:v:0", "-c", "copy", "-movflags", "+faststart", out_mp4])


class BrowserCapture:
    """Constant-frame-rate capture of one (hidden, headless) browser page via Chrome's own screencast.

    Chrome sends a JPEG only when the page repaints, stamped with its paint time (wall clock). Frames are laid onto a
    fixed 1/fps grid as they arrive - each grid slot shows the latest frame painted at or before it - and piped to the
    same lossless encoder the screen capture uses, so raw.mp4 is constant frame rate and nothing appears on screen."""

    def __init__(self, out: Path, fps: int, size: tuple[int, int], quality: int = 95):
        self.out = out
        self.fps = fps
        self.size = size
        self.quality = quality
        self.progress = out.with_suffix(".progress")
        self.logfile = out.with_suffix(".ffmpeg.log")
        self.proc: subprocess.Popen | None = None
        self.cdp = None
        self._queue: queue.Queue = queue.Queue()
        self._writer: threading.Thread | None = None
        self._error: BaseException | None = None
        self.t0: float | None = None       # paint time of the first frame (video time 0)
        self.frames = 0
        self.slots = 0
        self.max_gap = 0.0

    def start(self, page, ready_timeout: float = 10.0) -> None:
        for p in (self.out, self.progress):
            p.unlink(missing_ok=True)
        w, h = self.size
        cmd = [
            media.FFMPEG, "-hide_banner", "-y",
            "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(self.fps), "-i", "pipe:0",
            "-vf", f"scale={w}:{h}:flags=lanczos",
            "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p",
            "-g", str(self.fps), "-fps_mode", "cfr", "-r", str(self.fps),
            "-video_track_timescale", str(self.fps * 1000),
            "-movflags", "+frag_keyframe+empty_moov+default_base_moof", "-f", "mp4",
            str(self.out),
        ]
        self._log = open(self.logfile, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._log)
        self._writer = threading.Thread(target=self._write_loop, daemon=True)
        self._writer.start()

        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": self.quality,
                                               "maxWidth": w, "maxHeight": h, "everyNthFrame": 1})
        deadline = time.monotonic() + ready_timeout
        while self.t0 is None:
            if self.proc.poll() is not None:
                raise CaptureError(f"ffmpeg exited immediately; see {self.logfile}:\n{self._tail()}")
            if time.monotonic() > deadline:
                self.stop()
                raise CaptureError(f"the hidden browser sent no frames within {ready_timeout:.0f}s")
            page.wait_for_timeout(50)

    def _on_frame(self, f: dict) -> None:
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]})
        except Exception:  # noqa: BLE001 - the session closes while the last frames are in flight
            pass
        ts = float(f["metadata"]["timestamp"])
        if self.t0 is None:
            self.t0 = ts
        self._queue.put((ts, base64.b64decode(f["data"])))

    def _write_loop(self) -> None:
        prev_ts, prev = None, None
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    return
                ts, jpeg = item
                if prev is not None:
                    ts = max(ts, prev_ts)
                    self.max_gap = max(self.max_gap, ts - prev_ts)
                    self._fill_until(ts - self.t0, prev)
                prev_ts, prev = ts, jpeg
                self.frames += 1
                self._last = jpeg
        except BaseException as e:  # noqa: BLE001 - reported by stop()
            self._error = e

    def _fill_until(self, t: float, jpeg: bytes, inclusive: bool = False) -> None:
        """Write `jpeg` into every grid slot before video time t (up to and including t when inclusive)."""
        while (self.slots / self.fps <= t) if inclusive else (self.slots / self.fps < t - 1e-9):
            self.proc.stdin.write(jpeg)
            self.slots += 1

    def stop(self, timeout: float = 120.0) -> dict:
        if self.proc is None:
            return {}
        if self.cdp is not None:
            try:
                self.cdp.send("Page.stopScreencast")
            except Exception:  # noqa: BLE001
                pass
        end = time.time()
        self._queue.put(None)
        self._writer.join(timeout)
        try:
            if self.t0 is not None and self._error is None and getattr(self, "_last", None):
                self._fill_until(end - self.t0, self._last, inclusive=True)   # hold the last picture to the end
            self.proc.stdin.close()
        except OSError as e:
            self._error = self._error or e
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(10)
        self._log.close()
        code, self.proc = self.proc.returncode, None
        if self._error is not None or code != 0:
            raise CaptureError(f"background capture failed ({self._error or f'ffmpeg exit {code}'}); "
                               f"see {self.logfile}:\n{self._tail()}")
        return {"mode": "background", "frames": self.frames, "dup": max(0, self.slots - self.frames), "drop": 0,
                "max_gap_ms": round(self.max_gap * 1000, 1)}

    def _tail(self) -> str:
        try:
            return self.logfile.read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            return ""

    def remux_mp4(self, out_mp4: Path) -> None:
        media.run_ffmpeg(["-i", self.out, "-map", "0:v:0", "-c", "copy", "-movflags", "+faststart", out_mp4])
