"""Voice recorder that stops by itself when the speaker pauses.

Streamlit's built-in st.audio_input only stops when the user taps stop.
This small st.components.v2 component records with the browser's
MediaRecorder, watches the volume with the Web Audio API, and stops about
1.5 seconds after the speaker goes quiet. The recording is sent to Python
once, as a trigger value.
"""

import base64

import streamlit as st

HTML = """
<div class="rec">
  <button id="rec-btn" type="button">🎤 Tap and ask your question</button>
  <div id="rec-status">I stop listening when you pause.</div>
</div>
"""

CSS = """
.rec { font-family: inherit; }
#rec-btn {
  width: 100%; padding: 18px 16px; border: none; border-radius: 14px;
  background: #0ea5e9; color: #fff; font-size: 17px; font-weight: 600;
  cursor: pointer;
}
#rec-btn.live { background: #ef4444; animation: pulse 1.2s infinite; }
#rec-btn.busy { background: #334155; cursor: default; }
@keyframes pulse { 50% { opacity: .75; } }
#rec-status { margin-top: 8px; font-size: 13px; color: #94a3b8; text-align: center; }
"""

JS = """
export default function (component) {
  const { setTriggerValue, parentElement } = component;
  const btn = parentElement.querySelector('#rec-btn');
  const status = parentElement.querySelector('#rec-status');
  // State survives re-renders of this component
  const s = parentElement.__rec || (parentElement.__rec = { recording: false });

  const SILENCE_MS = 1500;    // stop this long after the speaker goes quiet
  const NO_SPEECH_MS = 8000;  // give up if nothing is said
  const MAX_MS = 30000;       // longest question

  const idle = (msg) => {
    btn.textContent = '🎤 Tap and ask your question';
    btn.className = '';
    status.textContent = msg || 'I stop listening when you pause.';
  };
  if (!s.recording) idle(s.message);
  s.message = null;

  const toBase64 = (blob) => new Promise((resolve) => {
    const r = new FileReader();
    r.onloadend = () => resolve(String(r.result).split(',')[1]);
    r.readAsDataURL(blob);
  });

  async function start() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(
        { audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      idle('Microphone is blocked. Allow the microphone for this site and try again.');
      return;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    const ctx = new AC();
    if (ctx.resume) await ctx.resume();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);

    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
    const mimeType = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };

    Object.assign(s, { recording: true, rec, spoke: false, manual: false });
    btn.textContent = '🔴 Listening… (tap to stop)';
    btn.className = 'live';
    status.textContent = 'Speak now. I stop when you pause.';

    const t0 = performance.now();
    let lastVoice = t0, noise = 0, n = 0;
    const timer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += v * v;
      const level = Math.sqrt(sum / samples.length);
      const now = performance.now();
      if (now - t0 < 400) { noise += level; n += 1; }        // background noise
      const threshold = Math.max(0.015, (n ? noise / n : 0.01) * 2.5);
      if (level > threshold && now - t0 >= 400) { lastVoice = now; s.spoke = true; }
      const quietAfterSpeech = s.spoke && now - lastVoice > SILENCE_MS;
      const nothingSaid = !s.spoke && now - t0 > NO_SPEECH_MS;
      if (quietAfterSpeech || nothingSaid || now - t0 > MAX_MS) stop();
    }, 100);

    rec.onstop = async () => {
      clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
      if (!s.spoke && !s.manual) {
        idle("I didn't hear anything. Tap and try again.");
        return;
      }
      btn.textContent = '⏳ Thinking…';
      btn.className = 'busy';
      status.textContent = '';
      const blob = new Blob(chunks, { type: rec.mimeType || mimeType || 'audio/webm' });
      setTriggerValue('audio', { b64: await toBase64(blob), mime: blob.type });
    };
    rec.start(250);
  }

  function stop(manual) {
    if (!s.recording) return;
    s.recording = false;
    if (manual) s.manual = true;
    if (s.rec && s.rec.state !== 'inactive') s.rec.stop();
  }

  btn.onclick = () => {
    if (btn.className === 'busy') return;
    if (s.recording) stop(true); else start();
  };
}
"""

EXTENSIONS = {"webm": "webm", "mp4": "m4a", "mpeg": "mp3", "ogg": "ogg", "wav": "wav"}

_component = st.components.v2.component(
    "iraaya_voice_recorder", html=HTML, css=CSS, js=JS
)


def voice_recorder(key: str = "voice_recorder", turn: int = 0):
    """Show the recorder. Returns (audio_bytes, filename) once per question,
    otherwise None.

    turn: change it after each question so the recorder redraws and
    resets from "Thinking..." to ready.
    """
    result = _component(key=key, data={"turn": turn}, on_audio_change=lambda: None)
    audio = result.get("audio") if hasattr(result, "get") else getattr(result, "audio", None)
    if not audio or not audio.get("b64"):
        return None
    mime = audio.get("mime", "audio/webm")
    ext = next((e for k, e in EXTENSIONS.items() if k in mime), "webm")
    return base64.b64decode(audio["b64"]), f"question.{ext}"
