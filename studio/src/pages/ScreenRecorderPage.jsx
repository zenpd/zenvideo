import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Field, PageHead, PanelHead, Spinner } from "../ui.jsx";

export default function ScreenRecorderPage() {
  const [devices, setDevices] = useState(null);
  const [recording, setRecording] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [outputPath, setOutputPath] = useState("recording.webm");
  const [videoIdx, setVideoIdx] = useState("1");
  const [audioIdx, setAudioIdx] = useState("0");
  const [framerate, setFramerate] = useState("30");
  const [audioBitrate, setAudioBitrate] = useState("192k");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [deviceList, status] = await Promise.all([
        api.screenRecorderDevices(),
        api.screenRecorderStatus(),
      ]);
      setDevices(deviceList);
      setRecording(Boolean(status.active));
      if (deviceList.video?.length) {
        setVideoIdx((current) => deviceList.video.some((device) => String(device.idx) === current)
          ? current
          : String(deviceList.video[0].idx));
      }
      if (deviceList.audio?.length) {
        setAudioIdx((current) => deviceList.audio.some((device) => String(device.idx) === current)
          ? current
          : String(deviceList.audio[0].idx));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!recording) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const status = await api.screenRecorderStatus();
        setRecording(Boolean(status.active));
      } catch {
        setError("Could not refresh recording status. Check the server connection.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [recording]);

  const start = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNote("");
    try {
      await api.startScreenRecorder({
        output_path: outputPath,
        video_idx: videoIdx,
        audio_idx: audioIdx,
        framerate: Number(framerate),
        audio_bitrate: audioBitrate,
      });
      setRecording(true);
      setNote(`Recording to ${outputPath}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.stopScreenRecorder();
      setRecording(false);
      setNote(result.note || `Recording saved to ${outputPath}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const supported = devices?.supported !== false;
  const ready = supported && devices?.video?.length > 0 && devices?.audio?.length > 0;

  return (
    <>
      <PageHead title="Screen Recorder" subtitle="Capture this computer's screen and microphone to a local video file." />
      {error && <Alert intent="error" title="Recorder request failed">{error}</Alert>}
      {devices?.supported === false && (
        <Alert intent="warn" title="Screen capture is unavailable on this server">
          {devices.message || "The current screen_recorder.py backend requires macOS and FFmpeg avfoundation."}
          <span> The scripted browser recorder remains available for app demos.</span>
        </Alert>
      )}
      {loading ? <Spinner label="Checking capture devices…" /> : devices?.supported !== false && (
        <div className="grid-2" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 340px)", alignItems: "start" }}>
          <section className="panel" aria-labelledby="capture-settings-title">
            <PanelHead icon="video" tone="turq" title={<span id="capture-settings-title">Capture settings</span>}
              subtitle={recording ? "A recording is in progress" : "Choose devices and output format"} />
            <form className="stack" style={{ gap: 14 }} onSubmit={start}>
              <Field label="Output file" htmlFor="screen-output" hint="Saved relative to the ZenVideo project folder.">
                <input id="screen-output" className="input" value={outputPath} onChange={(event) => setOutputPath(event.target.value)} disabled={recording || busy} />
              </Field>
              <div className="features" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14 }}>
                <Field label="Screen" htmlFor="screen-video-device">
                  <select id="screen-video-device" className="select" value={videoIdx} onChange={(event) => setVideoIdx(event.target.value)} disabled={!ready || recording || busy}>
                    {(devices.video || []).map((device) => <option key={device.idx} value={device.idx}>{device.name}</option>)}
                  </select>
                </Field>
                <Field label="Microphone" htmlFor="screen-audio-device">
                  <select id="screen-audio-device" className="select" value={audioIdx} onChange={(event) => setAudioIdx(event.target.value)} disabled={!ready || recording || busy}>
                    {(devices.audio || []).map((device) => <option key={device.idx} value={device.idx}>{device.name}</option>)}
                  </select>
                </Field>
                <Field label="Frame rate" htmlFor="screen-framerate">
                  <select id="screen-framerate" className="select" value={framerate} onChange={(event) => setFramerate(event.target.value)} disabled={recording || busy}>
                    {[24, 30, 60].map((rate) => <option key={rate} value={rate}>{rate} fps</option>)}
                  </select>
                </Field>
                <Field label="Audio bitrate" htmlFor="screen-bitrate">
                  <select id="screen-bitrate" className="select" value={audioBitrate} onChange={(event) => setAudioBitrate(event.target.value)} disabled={recording || busy}>
                    {["128k", "192k", "256k"].map((rate) => <option key={rate} value={rate}>{rate}</option>)}
                  </select>
                </Field>
              </div>
              {!ready && <Alert intent="warn" title="Capture devices not found">Refresh the device list or check FFmpeg permissions and device availability.</Alert>}
              <div className="row" style={{ flexWrap: "wrap" }}>
                {!recording ? (
                  <button type="submit" className="btn btn-primary" disabled={!ready || busy || !outputPath.trim()}>
                    {busy ? "Starting…" : "Start recording"}
                  </button>
                ) : (
                  <button type="button" className="btn btn-danger" onClick={stop} disabled={busy}>
                    {busy ? "Stopping…" : "Stop recording"}
                  </button>
                )}
                <button type="button" className="btn btn-ghost" onClick={refresh} disabled={loading || busy || recording}>Refresh devices</button>
              </div>
            </form>
          </section>

          <aside className="panel" aria-labelledby="capture-status-title">
            <PanelHead icon="activity" tone={recording ? "yellow" : "blue"} title={<span id="capture-status-title">Recorder status</span>} />
            <div className="row" role="status" aria-live="polite" style={{ marginBottom: 14 }}>
              <span className={`badge ${recording ? "b-red" : "b-green"}`}>{recording ? "Recording" : "Ready"}</span>
            </div>
            <p className="meta">{recording ? `Writing to ${outputPath}` : "No active recording."}</p>
            {note && <p className="meta" role="status" style={{ marginTop: 12 }}>{note}</p>}
            <p className="meta" style={{ marginTop: 18 }}>Manual screen capture is separate from the scripted browser recordings in Zen Studio.</p>
          </aside>
        </div>
      )}
    </>
  );
}