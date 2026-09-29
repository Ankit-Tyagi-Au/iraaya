"""Small browser helpers: copy-to-clipboard buttons and on-device storage.

Device storage keeps the user's work (data, conversation, spoken answers,
settings) in the browser's own storage (IndexedDB) on their device, so a
page refresh, a server restart or an app update doesn't lose it. Nothing
is kept on the server.
"""

import streamlit as st

# ---------- copy button ----------

COPY_HTML = '<button class="copy" type="button"></button>'
COPY_CSS = """
.copy { background: transparent; color: #94a3b8; border: 1px solid #334155;
        border-radius: 8px; padding: 3px 10px; font-size: 13px; cursor: pointer; }
.copy:hover { color: #e2e8f0; border-color: #0ea5e9; }
"""
COPY_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const btn = parentElement.querySelector('.copy');
  const label = (data && data.label) || '📋 Copy';
  btn.textContent = label;
  btn.onclick = async () => {
    const text = (data && data.text) || '';
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {}
    if (!ok) {             // older browsers
      const t = document.createElement('textarea');
      t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select();
      try { ok = document.execCommand('copy'); } catch (e) {}
      t.remove();
    }
    btn.textContent = ok ? '✅ Copied' : '⚠️ Copy failed';
    setTimeout(() => { btn.textContent = label; }, 1800);
  };
}
"""


# ---------- device storage ----------

STORE_JS = """
const DB = 'iraaya', STORE = 'state', KEY = 'main';
const open = () => new Promise((resolve, reject) => {
  const req = indexedDB.open(DB, 1);
  req.onupgradeneeded = () => req.result.createObjectStore(STORE);
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});
const read = async () => {
  const db = await open();
  return new Promise((resolve) => {
    const r = db.transaction(STORE).objectStore(STORE).get(KEY);
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => resolve(null);
  });
};
const write = async (value) => {
  const db = await open();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE, 'readwrite');
    if (value === null) tx.objectStore(STORE).delete(KEY);
    else tx.objectStore(STORE).put(value, KEY);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => resolve(false);
  });
};

export default function (component) {
  const { data, setTriggerValue } = component;
  const W = window.__iraayaStore || (window.__iraayaStore = { restored: false, rev: null, queue: Promise.resolve() });

  // Once per page load: send back whatever this device saved last time
  if (!W.restored) {
    W.restored = true;
    read().then((rec) => setTriggerValue('restore', rec || {}))
          .catch(() => setTriggerValue('restore', {}));
  }
  if (!data || data.rev === W.rev) return;
  W.rev = data.rev;
  // Saves run one after another, merging the changed parts
  W.queue = W.queue.then(async () => {
    try {
      if (data.clear) { await write(null); return; }
      if (data.save) {
        const current = (await read()) || {};
        await write(Object.assign(current, data.save));
      }
    } catch (e) { /* storage unavailable (e.g. private browsing) */ }
  });
}
"""


_SPECS = {
    "iraaya_copy_button": {"html": COPY_HTML, "css": COPY_CSS, "js": COPY_JS},
    "iraaya_device_storage": {"js": STORE_JS},
}
_renderers = {name: st.components.v2.component(name, **spec) for name, spec in _SPECS.items()}


def _mount(name: str, **kwargs):
    """Mount a component, registering it again if Streamlit lost it
    (registration normally happens once, when this file is first loaded)."""
    try:
        return _renderers[name](**kwargs)
    except Exception as e:
        if "not registered" not in str(e):
            raise
        _renderers[name] = st.components.v2.component(name, **_SPECS[name])
        return _renderers[name](**kwargs)


def copy_button(text: str, key: str, label: str = "📋 Copy"):
    """A small button that copies text to the clipboard."""
    _mount("iraaya_copy_button", key=key, data={"text": text, "label": label}, width="content")


def device_storage(save: dict = None, clear: bool = False, rev: str = None,
                   key: str = "device_storage"):
    """Save changed parts to this device, or clear them. Returns what the
    device had saved (once per page load, as a dict; {} if nothing), else None.
    rev must change whenever save/clear changes."""
    data = {"rev": rev, "save": save, "clear": clear} if (save or clear) else {"rev": rev}
    result = _mount("iraaya_device_storage", key=key, data=data,
                    on_restore_change=lambda: None)
    value = result.get("restore") if hasattr(result, "get") else getattr(result, "restore", None)
    return value
