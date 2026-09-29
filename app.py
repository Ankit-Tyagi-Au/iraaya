"""iRaaya — your business, explained simply, in any language.

Run: streamlit run app.py
"""

import base64
import difflib
import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from analyser import (
    calculate_health_score,
    clean_dataframe,
    detect_anomalies,
    find_relevant_rows,
    get_data_context,
    get_summary,
    load_data,
    validate_data,
    vocabulary_hint,
)
from browser_tools import copy_button, device_storage
from charts import (
    product_comparison,
    regional_performance,
    revenue_by_month,
    revenue_trend,
    top_products,
)
from documents import (
    DOCUMENT_TYPES,
    PAGE_SOURCES,
    document_context,
    page_overview,
    read_document,
)
from forecaster import forecast_chart, forecast_revenue
from formatting import CURRENCIES, NUMBER_STYLES, fmt_compact, fmt_money, symbol_for
from importer import ALL
from insights import (
    IRaayaError,
    ask_document,
    ask_iraaya,
    generate_insights,
    generate_whatsapp_summary,
)
from languages import LANGUAGES
from metrics import FILTER_COLUMNS, apply_filters, card_numbers, growth_by, previous_period, previous_range
from pdf_report import conversation_text, generate_conversation_pdf, generate_pdf
from recorder import voice_recorder
from voice import (
    DEFAULT_VOICE_ID,
    SPEEDS,
    VoiceCloneError,
    cleanup_old_clones,
    clone_voice,
    delete_voice,
    get_plan,
    list_voices,
    speak_elevenlabs,
    speak_gtts,
    transcribe_audio_file,
)

VERSION = "1.0"
APP_DIR = Path(__file__).resolve().parent
LOGO = APP_DIR / "assets" / "logo.png"
LOGO_SVG = (APP_DIR / "assets" / "logo.svg").read_text()
SAMPLE_FILE = APP_DIR / "sample_data.csv"
MAX_DEVICE_FILE_MB = 15          # bigger files aren't kept on the device

# Explicit path: Streamlit runs the script in a way that stops
# load_dotenv() from finding .env on its own.
# override=True: a blank GROQ_API_KEY inherited from the shell must not
# hide the real key in .env (on Streamlit Cloud there is no .env file).
load_dotenv(APP_DIR / ".env", override=True)


def get_secret(name: str):
    """Read a key from .env (local) or Streamlit secrets (cloud)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        return st.secrets.get(name)
    except Exception:
        return None


GROQ_KEY = get_secret("GROQ_API_KEY")
EL_KEY = get_secret("ELEVENLABS_API_KEY")
if get_secret("GROQ_MODEL"):
    os.environ["GROQ_MODEL"] = get_secret("GROQ_MODEL")

st.set_page_config(
    page_title="iRaaya",
    page_icon=str(LOGO),
    layout="wide",
    initial_sidebar_state="auto",     # folds away on phones
)
st.logo(str(LOGO), size="large")

# ---------- Look and feel ----------
st.markdown("""
<style>
/* Cards: subtle border and shadow */
div[data-testid="stMetric"] {
  background: #1e293b; border: 1px solid #334155; border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 4px 14px rgba(0,0,0,.25);
}
div[data-testid="stMetricValue"] { font-size: 1.7rem; }
/* Chat: you on the right in blue, iRaaya on the left in green */
div[data-testid="stChatMessage"] { width: 88% !important; border-radius: 16px; }
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
  flex-direction: row-reverse; background: #1e3a8a; margin-left: auto !important;
  border-radius: 16px 16px 4px 16px;
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) p { text-align: right; }
div[data-testid="stChatMessage"]:not(:has(div[data-testid="stChatMessageAvatarUser"])) {
  background: #064e3b; margin-right: auto !important; border-radius: 16px 16px 16px 4px;
}
.msg-time { font-size: .72rem; color: #94a3b8; }
.tag { display: inline-block; background: #0c4a6e; color: #e0f2fe; border-radius: 999px;
       padding: 2px 10px; margin: 2px 4px 2px 0; font-size: .8rem; }
.hero { text-align: center; padding: 10px 0 0 0; }
.hero svg { width: 110px; height: 110px; }
.hero h1 { font-size: 2.6rem; margin: 6px 0 0 0; }
.step { background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 16px; height: 100%; }
.step b { color: #38bdf8; font-size: 1.05rem; }
/* Phones: full-width buttons, readable text, less side space */
@media (max-width: 640px) {
  div.stButton > button, div.stDownloadButton > button { width: 100%; }
  div[data-testid="stChatMessage"] { width: 96% !important; }
  div[data-testid="stMetricValue"] { font-size: 1.4rem; }
  .hero h1 { font-size: 2rem; }
}
</style>
""", unsafe_allow_html=True)

# ---------- Session state ----------
DEFAULTS = {
    "df": None,
    "data_key": None,
    "data_name": None,
    "source": None,          # {"kind": "sample"|"file"|"document", ...} — what to reload after a refresh
    "import_report": None,
    "warnings": [],
    "just_loaded": False,
    "chat_history": [],
    "play": None,            # {"id": message id, "via_recorder": bool} for the answer to play now
    "cloned_voice_id": None,
    "cloned_voice_name": None,
    "insights": [],
    "whatsapp": None,
    "voice_q_n": 0,
    "pending_question": None,
    # PDF / Word documents without a sales table
    "doc_text": None,
    "doc_name": None,
    "doc_pages": None,
    "doc_page_source": None,
}
# Settings (widget keys) — remembered on this device
SETTING_DEFAULTS = {
    "lang": "English",
    "style": "Simple",
    "speak": "Match my question",
    "premium": False,
    "speed": "Normal",
    "currency": "Not specified",
    "number_style": "1,234,567.89 (International)",
    "date_order": "Day/Month (most of the world)",
    "company": "",
}
DATE_ORDERS = {"Day/Month (most of the world)": "day-first", "Month/Day (USA)": "month-first"}

for key, value in {**DEFAULTS, **SETTING_DEFAULTS}.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------- Loading data ----------

@st.cache_data(show_spinner=False, max_entries=20)
def parse_table_file(data: bytes, name: str, date_order: str):
    f = io.BytesIO(data)
    f.name = name
    df = load_data(f, date_order)
    return df, df.attrs.get("import_report", {})


@st.cache_data(show_spinner=False, max_entries=20)
def parse_document_file(data: bytes, name: str, date_order: str):
    f = io.BytesIO(data)
    f.name = name
    doc = read_document(f)
    if doc["kind"] == "table":
        df = clean_dataframe(doc["df"], date_order)
        return {"kind": "table", "df": df, "report": df.attrs.get("import_report", {})}
    return doc


def _with_report(df, report):
    df = df.copy()
    df.attrs["import_report"] = report
    df.attrs["dropped_rows"] = report.get("dropped_rows", 0)
    return df


def set_data(df, name: str, data_key: str, source: dict, keep_history: bool = False):
    """Keep a newly loaded table. Returns False (and explains) if unusable."""
    validation = validate_data(df)
    if not validation["is_valid"]:
        missing = validation["missing_columns"]
        report = df.attrs.get("import_report", {})
        if missing:
            names = {"Date": "a date column", "Total_Revenue": "a revenue/amount column (or Quantity + Price)"}
            found = list(report.get("mapping", {})) + list(report.get("unused_columns", []))
            st.sidebar.error(
                "iRaaya couldn't find " + " and ".join(names.get(m, m) for m in missing) + ". "
                + (f"Columns in your file: {', '.join(map(str, found))}. " if found else "")
                + "Tip: name them e.g. 'Date' and 'Amount' (other languages work too)."
            )
        else:
            st.sidebar.error("No usable rows found in this file — every row was missing a date or amount.")
        return False
    st.session_state.df = df
    st.session_state.data_key = data_key
    st.session_state.data_name = name
    st.session_state.source = source
    st.session_state.import_report = df.attrs.get("import_report", {})
    st.session_state.warnings = validation["warnings"]
    for key in ("doc_text", "doc_name", "doc_pages", "doc_page_source"):
        st.session_state[key] = None
    if not keep_history:
        st.session_state.chat_history = []
        st.session_state.insights = []
        st.session_state.whatsapp = None
        st.session_state.play = None
        st.session_state.just_loaded = True
        for col in FILTER_COLUMNS:
            st.session_state.pop(f"f_{col}", None)
        st.session_state.pop("f_dates", None)
    return True


def set_document(text: str, name: str, pages, data_key: str, page_source, source: dict,
                 keep_history: bool = False):
    """Keep a PDF/Word document (no sales table) to answer questions about."""
    st.session_state.df = None
    st.session_state.import_report = None
    st.session_state.warnings = []
    st.session_state.doc_text = text
    st.session_state.doc_name = name
    st.session_state.doc_pages = pages
    st.session_state.doc_page_source = page_source
    st.session_state.data_key = data_key
    st.session_state.data_name = name
    st.session_state.source = source
    if not keep_history:
        st.session_state.chat_history = []
        st.session_state.insights = []
        st.session_state.whatsapp = None
        st.session_state.play = None


def load_upload(data: bytes, name: str, data_key: str, keep_history: bool = False, progress=None):
    """Read an uploaded file (table or document). Returns True if loaded."""
    order = DATE_ORDERS[st.session_state.date_order]
    st.session_state._loaded_date_order = st.session_state.date_order
    ext = os.path.splitext(name)[1].lower()
    b64 = base64.b64encode(data).decode() if len(data) <= MAX_DEVICE_FILE_MB * 1024 * 1024 else None
    source = {"kind": "file", "name": name, "b64": b64}
    if progress:
        progress.progress(35, text="Reading your file…")
    if ext in DOCUMENT_TYPES:
        doc = parse_document_file(data, name, order)
        if progress:
            progress.progress(75, text="Analysing…")
        if doc["kind"] == "table":
            return set_data(_with_report(doc["df"], doc["report"]), name, data_key, source, keep_history)
        set_document(doc["text"], name, doc["pages"], data_key, doc.get("page_source"),
                     source, keep_history)
        return True
    df, report = parse_table_file(data, name, order)
    if progress:
        progress.progress(75, text="Analysing…")
    return set_data(_with_report(df, report), name, data_key, source, keep_history)


def load_sample(keep_history: bool = False):
    df, report = parse_table_file(SAMPLE_FILE.read_bytes(), "sample_data.csv", "day-first")
    return set_data(_with_report(df, report), "Sample data", "sample", {"kind": "sample"}, keep_history)


def is_document() -> bool:
    return st.session_state.df is None and bool(st.session_state.doc_text)


# ---------- Remember work on this device ----------
# The device storage component (bottom of the page) hands back what this
# device saved last time; it is applied here, before any widget is drawn.

def _audio_b64(msg):
    return base64.b64encode(msg["audio"]).decode() if msg.get("audio") else None


def apply_restore(rec: dict):
    if not rec:
        return
    for key, value in (rec.get("settings") or {}).items():
        if key in SETTING_DEFAULTS and value is not None:
            st.session_state[key] = value
    src = rec.get("source") or {}
    try:
        if src.get("kind") == "sample":
            load_sample(keep_history=True)
        elif src.get("kind") == "file" and src.get("b64"):
            data = base64.b64decode(src["b64"])
            load_upload(data, src["name"], hashlib.md5(data).hexdigest(), keep_history=True)
        elif src.get("kind") == "document" and rec.get("doc"):
            d = rec["doc"]
            set_document(d["text"], d["name"], d.get("pages"), d.get("key"), d.get("page_source"),
                         src, keep_history=True)
    except Exception:
        pass    # a file that can't be read again is simply not restored
    history = []
    for m in rec.get("chat") or []:
        m = dict(m)
        m["audio"] = base64.b64decode(m.pop("audio_b64")) if m.get("audio_b64") else None
        history.append(m)
    st.session_state.chat_history = history
    extras = rec.get("extras") or {}
    for key in ("insights", "whatsapp", "cloned_voice_id", "cloned_voice_name"):
        if key in extras:
            st.session_state[key] = extras[key]
    for key, value in (extras.get("filters") or {}).items():
        if key == "f_dates" and value:
            value = tuple(pd.Timestamp(v).date() for v in value)
        st.session_state[key] = value
    if extras.get("main_tab"):
        st.session_state.main_tab = extras["main_tab"]
    st.session_state._saved = {}        # save everything again under the new session


def snapshot_parts() -> dict:
    """What to keep on the device, split into parts saved separately."""
    src = st.session_state.source
    doc = None
    if is_document():
        doc = {"text": st.session_state.doc_text, "name": st.session_state.doc_name,
               "pages": st.session_state.doc_pages, "page_source": st.session_state.doc_page_source,
               "key": st.session_state.data_key}
        src = {"kind": "document"}
    chat = [{**{k: v for k, v in m.items() if k != "audio"}, "audio_b64": _audio_b64(m)}
            for m in st.session_state.chat_history[-20:]]
    filters = {k: (list(map(str, st.session_state[k])) if k == "f_dates" else st.session_state[k])
               for k in ["f_dates"] + [f"f_{c}" for c in FILTER_COLUMNS] if st.session_state.get(k)}
    return {
        "settings": {k: st.session_state.get(k) for k in SETTING_DEFAULTS},
        "source": src,
        "doc": doc,
        "chat": chat,
        "extras": {
            "insights": st.session_state.insights, "whatsapp": st.session_state.whatsapp,
            "cloned_voice_id": st.session_state.cloned_voice_id,
            "cloned_voice_name": st.session_state.cloned_voice_name,
            "filters": filters, "main_tab": st.session_state.get("main_tab"),
        },
    }


if "_restore" in st.session_state:
    apply_restore(st.session_state.pop("_restore"))

if st.session_state.pop("_reset_filters", False):
    for key in [k for k in list(st.session_state) if k.startswith("f_")]:
        del st.session_state[key]

if st.session_state.pop("forget_pending", False):
    for key, value in {**DEFAULTS, **SETTING_DEFAULTS}.items():
        st.session_state[key] = value
    for key in [k for k in st.session_state if k.startswith("f_")] + ["main_tab"]:
        st.session_state.pop(key, None)
    st.session_state._clear_device = True


def show_error(e: Exception):
    st.error(str(e) if isinstance(e, IRaayaError) else f"Something went wrong: {e}")


# ---------- Settings used everywhere ----------
selected_language = st.session_state.lang
selected_mode = st.session_state.style
currency = CURRENCIES.get(st.session_state.currency)
SYM = symbol_for(st.session_state.currency)
NSTYLE = NUMBER_STYLES.get(st.session_state.number_style, "intl")
money = lambda v: fmt_money(v, SYM, NSTYLE)
compact = lambda v: fmt_compact(v, SYM, NSTYLE)
COMPANY = st.session_state.company.strip()


# ---------- Sidebar: data ----------
st.sidebar.caption("Your Business Voice · by Riverrax")

uploaded_file = st.sidebar.file_uploader(
    "Upload your business data or a document",
    type=["csv", "xlsx", "xls", "pdf", "docx"],
    help=(
        "Sales data: CSV or Excel (or a PDF/Word file with a sales table). It needs a date "
        "and an amount column — names in any of iRaaya's languages work, e.g. Date / Amount, "
        "Datum / Umsatz, 日期 / 销售额. Any other PDF or Word document: ask questions about it."
    ),
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    data_key = hashlib.md5(file_bytes).hexdigest()
    if data_key != st.session_state.data_key:
        progress = st.sidebar.progress(10, text="Uploading…")
        try:
            load_upload(file_bytes, uploaded_file.name, data_key, progress=progress)
            progress.progress(100, text="Done")
        except ValueError as e:
            st.sidebar.error(str(e))
        except Exception as e:
            st.sidebar.error(f"iRaaya couldn't read this file. Please check it opens normally. ({e})")
        progress.empty()
elif st.session_state.data_key is None:
    if st.sidebar.button("✨ Try with sample data", width="stretch"):
        load_sample()
        st.rerun()

if is_document():
    pages = st.session_state.doc_pages
    st.sidebar.success(
        f"Loaded document: {st.session_state.doc_name}"
        + (f" ({pages} page{'s' if pages != 1 else ''})" if pages else "")
    )
    st.sidebar.caption(
        "Ask anything about it in 💬 Ask iRaaya. Charts, forecasts and "
        "insights need sales data (CSV, Excel, or a PDF/Word sales table)."
    )

# ---------- Sidebar: filters ----------
FULL_DF = st.session_state.df
df = FULL_DF
filter_tags, date_start, date_end, choices = [], None, None, {}
if FULL_DF is not None:
    st.sidebar.success(f"Loaded: {st.session_state.data_name} ({len(FULL_DF):,} rows)")
    for w in st.session_state.warnings:
        st.sidebar.warning(w)
    min_d, max_d = FULL_DF.Date.min().date(), FULL_DF.Date.max().date()
    with st.sidebar.expander("🔎 Filters", expanded=False):
        saved_dates = st.session_state.get("f_dates")
        if saved_dates and not (isinstance(saved_dates, (list, tuple)) and len(saved_dates) == 2
                                and min_d <= saved_dates[0] <= saved_dates[1] <= max_d):
            del st.session_state["f_dates"]           # from other data: start again
        date_kwargs = {} if "f_dates" in st.session_state else {"value": (min_d, max_d)}
        dates = st.date_input("Date range", min_value=min_d, max_value=max_d, key="f_dates",
                              persist_state="session", **date_kwargs)
        for col, label in FILTER_COLUMNS.items():
            values = sorted(FULL_DF[col].dropna().astype(str).unique()) if col in FULL_DF.columns else []
            if len(values) > 1:
                choices[col] = st.multiselect(label, values, key=f"f_{col}", persist_state="session",
                                              placeholder=f"All {label.lower()}")
        if st.button("↺ Reset filters", width="stretch"):
            st.session_state._reset_filters = True
            st.rerun()
    if isinstance(dates, (list, tuple)) and len(dates) == 2:
        date_start, date_end = dates
    else:
        date_start, date_end = min_d, max_d
    df = apply_filters(FULL_DF, date_start, date_end, choices)
    if (date_start, date_end) != (min_d, max_d):
        filter_tags.append(f"📅 {date_start:%d %b %Y} – {date_end:%d %b %Y}")
    for col, values in choices.items():
        if values:
            filter_tags.append(f"{FILTER_COLUMNS[col]}: {', '.join(values)}")
FILTERED = bool(filter_tags)


@st.cache_data(show_spinner=False, max_entries=30)
def analyse(data: pd.DataFrame):
    """Summary, AI context, health and unusual months for (filtered) data."""
    return {
        "summary": get_summary(data),
        "context": get_data_context(data),
        "health": calculate_health_score(data),
        "anomalies": detect_anomalies(data),
    }


A = analyse(df) if df is not None and not df.empty else None

if A:
    health = A["health"]
    st.sidebar.metric("iRaaya Score", f"{health['score']}/100", health["label"],
                      delta_color=health["color"], delta_arrow="off")
elif df is not None and df.empty:
    st.sidebar.warning("No sales match these filters. Try a wider date range or reset the filters.")

st.sidebar.divider()

# ---------- Sidebar: language, style, voice ----------
st.sidebar.selectbox(
    "🌍 Language", options=list(LANGUAGES.keys()), key="lang",
    format_func=lambda n: n if LANGUAGES[n]["display"] == n else f"{n} · {LANGUAGES[n]['display']}",
)
st.sidebar.radio("💬 Response style", ["Professional", "Simple", "Friendly"], horizontal=True, key="style")

st.sidebar.subheader("🔊 Voice")
SPEAK_MODES = {
    "Match my question": "Spoken answer when you ask by voice, text when you type",
    "Always": "Every answer is spoken",
    "Never": "Text answers only (voice off)",
}
speak_mode = st.sidebar.radio("Spoken answers", list(SPEAK_MODES),
                              captions=list(SPEAK_MODES.values()), key="speak")
speed = st.sidebar.select_slider("Speed", options=SPEEDS, key="speed")
use_elevenlabs = st.sidebar.toggle(
    "🎙️ Premium voice", disabled=not EL_KEY, key="premium",
    help=("Uses ElevenLabs for more natural voice output."
          if EL_KEY else "Add ELEVENLABS_API_KEY to enable premium voice."),
)
if speed == "Fast" and not (use_elevenlabs and EL_KEY):
    st.sidebar.caption("⚡ Fast needs Premium voice — the free voice speaks at normal speed.")

VOICE_PRIVACY = (
    "🔒 **Your voice stays private.** Your cloned voice is only used "
    "to speak your own answers. It is never shown to, or shared with, "
    "other iRaaya users. Your recording is sent to our voice partner "
    "ElevenLabs only to create the voice, and iRaaya does not keep a copy. "
    "You can delete your voice at any time with one click, and it is "
    "removed automatically after 7 days."
)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_voices(api_key: str) -> dict:
    return list_voices(api_key)


@st.cache_data(ttl=600, show_spinner=False)
def cached_plan(api_key: str) -> dict:
    return get_plan(api_key)


@st.cache_data(ttl=86400, show_spinner=False)
def daily_clone_cleanup(api_key: str) -> int:
    """Runs at most once a day: removes iRaaya voice clones older than 7 days."""
    return cleanup_old_clones(api_key)


if EL_KEY:
    daily_clone_cleanup(EL_KEY)

premium_voice_id, voice_name_shown = DEFAULT_VOICE_ID, "Standard voice (free)"
if use_elevenlabs and EL_KEY:
    voices = cached_voices(EL_KEY)
    if st.session_state.cloned_voice_id:
        # Only the person who made the clone sees it (this device only)
        voices = {f"{st.session_state.cloned_voice_name} (your voice)": st.session_state.cloned_voice_id, **voices}
    if voices:
        names = list(voices)
        default_name = next(
            (n for n, v in voices.items() if v == (st.session_state.cloned_voice_id or DEFAULT_VOICE_ID)),
            names[0],
        )
        chosen = st.sidebar.selectbox("🗣️ Voice", names, index=names.index(default_name))
        premium_voice_id, voice_name_shown = voices[chosen], chosen.split(" - ")[0]


def speak(text: str):
    """Spoken answer in the chosen language, voice and speed (or None)."""
    audio = None
    if use_elevenlabs and EL_KEY:
        audio = speak_elevenlabs(text, EL_KEY, premium_voice_id,
                                 LANGUAGES[selected_language]["el_code"], speed)
        if audio is None:
            st.toast("Premium voice didn't work this time — using the standard voice.")
    if audio is None:
        audio = speak_gtts(text, LANGUAGES[selected_language]["gtts_code"], speed)
    if audio is None:
        st.toast("Voice isn't available right now — here's the answer as text.")
    return audio


@st.cache_data(show_spinner=False, max_entries=60)
def preview_audio(lang: str, premium: bool, voice_id: str, spd: str):
    text = LANGUAGES[lang]["greeting"]
    if premium and EL_KEY:
        audio = speak_elevenlabs(text, EL_KEY, voice_id, LANGUAGES[lang]["el_code"], spd)
        if audio:
            return audio
    return speak_gtts(text, LANGUAGES[lang]["gtts_code"], spd)


st.sidebar.caption(f"Active: **{selected_language}** · {voice_name_shown} · {speed} speed")
if st.sidebar.button("▶ Preview voice", width="stretch"):
    audio = preview_audio(selected_language, bool(use_elevenlabs and EL_KEY), premium_voice_id, speed)
    if audio:
        st.sidebar.audio(audio, format="audio/mp3", autoplay=True)
    else:
        st.sidebar.warning("Voice isn't available right now.")

with st.sidebar.expander("🔬 Clone a voice"):
    st.caption("Record someone's voice and iRaaya will speak in that voice!")
    st.caption(VOICE_PRIVACY)
    plan = cached_plan(EL_KEY) if EL_KEY else {"tier": "none", "can_clone": False}
    if not EL_KEY:
        st.info("Add ELEVENLABS_API_KEY to use voice cloning.")
    elif not plan["can_clone"]:
        # Say so up front, before anyone uploads a voice recording
        st.info(
            f"Voice cloning needs an ElevenLabs paid plan (Starter or above). "
            f"Your current plan: {plan['tier']}."
        )
    else:
        st.caption("Only clone a voice with that person's permission.")
        voice_name = st.text_input("Voice name", placeholder="e.g. Manisha")
        audio_sample = st.file_uploader(
            "Upload audio sample (1-2 minutes of clear speech)",
            type=["mp3", "wav", "m4a"], key="voice_clone_upload",
        )
        consent = st.checkbox("I have this person's permission to clone their voice")
        if st.button("Clone this voice", key="clone_btn"):
            if not (audio_sample and voice_name):
                st.warning("Please enter a name and upload audio.")
            elif not consent:
                st.warning("Please confirm you have permission first.")
            else:
                try:
                    with st.spinner("Cloning voice..."):
                        voice_id = clone_voice(EL_KEY, voice_name, audio_sample.getvalue(), audio_sample.name)
                    st.session_state.cloned_voice_id = voice_id
                    st.session_state.cloned_voice_name = voice_name
                    st.success(f"Voice '{voice_name}' cloned! Turn on Premium voice to use it.")
                except VoiceCloneError as e:
                    st.error(f"Clone failed: {e}")
    if st.session_state.cloned_voice_id:
        st.caption(f"Your cloned voice: {st.session_state.cloned_voice_name}")
        if st.button("🗑️ Delete my voice", key="delete_voice_btn"):
            if delete_voice(EL_KEY, st.session_state.cloned_voice_id):
                st.session_state.cloned_voice_id = None
                st.session_state.cloned_voice_name = None
                st.success("Your voice has been permanently deleted.")
                st.rerun()
            else:
                st.error("Could not delete the voice. Please try again.")
        st.caption("If you don't delete it, iRaaya removes it automatically after 7 days.")

st.sidebar.divider()
st.sidebar.caption(
    "🔒 To answer questions, a summary of your data (or your document's text) is sent to "
    "Groq (AI). Spoken answers use Google TTS or ElevenLabs. Your work is remembered only "
    "in this browser on this device, so a refresh doesn't lose it — use **Start fresh** "
    "on a shared device. Cloned voices are private to the person who made them."
)
if st.session_state.df is not None or is_document() or st.session_state.chat_history:
    if st.sidebar.button("🧹 Start fresh (forget my data now)", width="stretch"):
        st.session_state.forget_pending = True
        st.rerun()

if not GROQ_KEY:
    st.sidebar.error(
        "The AI key is missing, so questions and insights won't work. "
        "Get a free key at [console.groq.com](https://console.groq.com/keys) and add it as GROQ_API_KEY."
    )


def data_context(question: str = "") -> str:
    """What the AI is told: business, currency, filters, data summary (and
    matching records for the question)."""
    lines = []
    if COMPANY:
        lines.append(f"BUSINESS NAME: {COMPANY}")
    lines.append(f"CURRENCY: all revenue figures are in {currency[1]}." if currency
                 else "CURRENCY: not specified. Do not use any currency symbol.")
    if FILTERED:
        lines.append("FILTERS ACTIVE (the data below covers only): " + "; ".join(filter_tags))
    ctx = "\n".join(lines) + "\n" + A["context"]
    if question:
        rows = find_relevant_rows(df, question)
        if rows:
            ctx += f"\n{rows}\n"
    return ctx


def show_filter_tags(where: str):
    if filter_tags:
        st.markdown("".join(f'<span class="tag">{escape_html(t)}</span>' for t in filter_tags),
                    unsafe_allow_html=True)
        st.caption(f"Filters are on — {where} use only the filtered data. Change them in the sidebar (🔎 Filters).")


def escape_html(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------- Main area ----------
TAB_LABELS = ["📊 Dashboard", "💬 Ask iRaaya", "🔍 Insights", "⚙️ Settings"]
if st.session_state.get("main_tab") not in TAB_LABELS:
    st.session_state.pop("main_tab", None)
# on_change="rerun": only the open tab's content runs (faster), and the open
# tab is remembered
tab1, tab2, tab3, tab4 = st.tabs(TAB_LABELS, key="main_tab", on_change="rerun")


def onboarding():
    st.markdown(
        f'<div class="hero">{LOGO_SVG}<h1>Welcome to iRaaya</h1>'
        '<p>Your business, explained simply — in any language. Upload your sales, '
        'ask questions by voice or text, and hear the answers in your language.</p></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.markdown('<div class="step"><b>Step 1 — Upload</b><br>Your sales as CSV or Excel '
                '(or a PDF/Word file). Just a date and an amount column is enough.</div>',
                unsafe_allow_html=True)
    c2.markdown('<div class="step"><b>Step 2 — Choose your language</b><br>13 languages, 3 '
                'answer styles, free or premium voice — in the sidebar.</div>', unsafe_allow_html=True)
    c3.markdown('<div class="step"><b>Step 3 — Ask iRaaya anything!</b><br>"What was my best '
                'month?" "Which product is falling?" Tap the mic and just ask.</div>',
                unsafe_allow_html=True)
    st.write("")
    b1, b2 = st.columns(2)
    if b1.button("✨ Try it with sample data", type="primary", width="stretch"):
        load_sample()
        st.rerun()
    b2.download_button("⬇️ Download sample data (CSV)", SAMPLE_FILE.read_bytes(),
                       "sample_data.csv", "text/csv", width="stretch")
    st.caption(
        "What you'll see: six key numbers (revenue, best month, best product, growth…), "
        "interactive charts, unusual-month alerts, a 3-month forecast, a health score, "
        "and a PDF report — all from your own data. No data? Use 👈 the sample."
    )


def data_preview():
    report = st.session_state.import_report or {}
    with st.expander("✅ Your data at a glance", expanded=st.session_state.just_loaded):
        c = st.columns(4)
        c[0].metric("Rows", f"{len(FULL_DF):,}")
        c[1].metric("Date range", f"{FULL_DF.Date.min():%d %b %Y} – {FULL_DF.Date.max():%d %b %Y}")
        products = FULL_DF.Product.nunique() if "Product" not in report.get("filled", []) else 0
        regions = FULL_DF.Region.nunique() if "Region" not in report.get("filled", []) else 0
        c[2].metric("Products found", products or "—")
        c[3].metric("Regions found", regions or "—")
        mapping = report.get("mapping", {})
        if mapping:
            st.markdown("**How iRaaya read your columns:** " + " · ".join(
                f"`{src}` → {dst.replace('_', ' ')}" for src, dst in mapping.items()))
        notes = []
        if report.get("filled"):
            notes.append("No " + " or ".join(report["filled"]).lower() + " column — that's fine, "
                         "those charts are simply left out.")
        if report.get("computed"):
            notes.append("Revenue worked out as quantity × price.")
        if report.get("date_order"):
            notes.append(f"Dates read as {report['date_order']}.")
        if report.get("number_style"):
            notes.append(f"Numbers written like {report['number_style']}.")
        if report.get("unused_columns"):
            notes.append("Not used: " + ", ".join(map(str, report["unused_columns"])) + ".")
        for n in notes:
            st.caption("• " + n)
        missing = report.get("missing_values", {})
        if missing:
            st.warning("Missing values: " + ", ".join(f"{k} ({v})" for k, v in missing.items())
                       + (f". {report.get('dropped_rows', 0)} rows without a date or amount were skipped."
                          if report.get("dropped_rows") else "."))
        st.markdown("**First 5 rows**")
        preview = FULL_DF.head(5).copy()
        preview["Date"] = preview.Date.dt.strftime("%d %b %Y")
        st.dataframe(preview, hide_index=True, width="stretch")
    if st.session_state.just_loaded:
        st.balloons()
        st.session_state.just_loaded = False


def metric_delta(value, text="vs previous period"):
    return None if value is None else f"{value:+.1f}% {text}"


# ---------- Tab 1: Dashboard ----------
if tab1.open:
    with tab1:
        if is_document():
            st.info(
                f"📄 **{st.session_state.doc_name}** is a document, not sales data, so there are "
                "no charts for it. Go to **💬 Ask iRaaya** and ask anything about it."
            )
        elif FULL_DF is None:
            onboarding()
        else:
            if COMPANY:
                st.subheader(f"🏢 {COMPANY}")
            data_preview()
            show_filter_tags("the cards and charts")
            if df.empty:
                st.warning("No sales match these filters. Try a wider date range or reset the filters.")
            else:
                prev = previous_period(FULL_DF, date_start, date_end, choices)
                c = card_numbers(df, prev)
                ps, pe = previous_range(date_start, date_end)
                prev_note = (f"Arrows compare with {ps:%d %b %Y} – {pe:%d %b %Y}."
                             if not prev.empty else "No earlier data to compare with, so no arrows.")

                r1 = st.columns(3)
                r1[0].metric("💰 Total revenue", money(c["total"]), metric_delta(c["total_change"]),
                             help=f"{money(c['total'])} · {prev_note}")
                r1[1].metric("📅 Best month", c["best_month"].strftime("%b %Y") if c["best_month"] else "—",
                             money(c["best_month_revenue"]), delta_color="off", delta_arrow="off")
                r1[2].metric("🏆 Best product", c["best_product"] if c["best_product"] != ALL else "—",
                             f"{c['best_product_share']:.0f}% of revenue" if c["best_product"] != ALL else None,
                             delta_color="off", delta_arrow="off", help=str(c["best_product"]))
                r2 = st.columns(3)
                r2[0].metric("🧾 Transactions", f"{c['transactions']:,}", metric_delta(c["transactions_change"]))
                r2[1].metric("📈 Average monthly revenue", money(c["avg_monthly"]),
                             metric_delta(c["avg_monthly_change"]),
                             help=f"Average over {c['months']} month(s) in the selected period.")
                mom = c["mom"]
                r2[2].metric("🔁 Month over month",
                             f"{mom['pct']:+.1f}%" if mom and mom["pct"] is not None else "—",
                             mom["label"] if mom else "Needs 2+ months",
                             delta_color=("green" if mom and (mom["pct"] or 0) >= 0 else "red") if mom else "off",
                             delta_arrow=("up" if mom and (mom["pct"] or 0) >= 0 else "down") if mom else "off",
                             help=("The latest month looked incomplete, so the last full month is used."
                                   if mom and mom["skipped_partial_month"] else None))
                st.caption(prev_note)

                anomalies = A["anomalies"]
                st.plotly_chart(revenue_by_month(df, [a["month"] for a in anomalies], SYM, NSTYLE),
                                width="stretch")
                has_products = df.Product.nunique() > 1
                has_regions = df.Region.nunique() > 1
                cols = st.columns(2) if has_products and has_regions else [st.container()]
                if has_products:
                    with cols[0]:
                        st.plotly_chart(top_products(df, SYM, NSTYLE), width="stretch")
                if has_regions:
                    with cols[-1]:
                        st.plotly_chart(regional_performance(df, SYM, NSTYLE, growth_by(df, prev, "Region")),
                                        width="stretch")
                st.plotly_chart(revenue_trend(df, SYM, NSTYLE), width="stretch")
                if has_products:
                    st.plotly_chart(product_comparison(df, SYM, NSTYLE), width="stretch")

                if anomalies:
                    st.subheader("⚠️ Unusual months")
                    for a in anomalies:
                        text = (f"**{pd.Period(a['month']).strftime('%B %Y')}**: revenue was "
                                f"{abs(a['difference_pct'])}% {'below' if a['type'] == 'low' else 'above'} "
                                f"what the trend expected ({money(a['revenue'])} vs {money(a['expected'])})")
                        if a["type"] == "low":
                            st.error("📉 " + text)
                        else:
                            st.success("🎉 " + text)

                st.download_button(
                    "⬇️ Download this data (clean CSV)",
                    df.assign(Date=df.Date.dt.strftime("%Y-%m-%d")).to_csv(index=False).encode("utf-8-sig"),
                    f"iraaya_data{'_filtered' if FILTERED else ''}.csv", "text/csv",
                )

# ---------- Tab 2: Ask iRaaya ----------
QUICK_QUESTIONS = {
    "Best month?": "What was my best month?",
    "Top product?": "Which product sells most?",
    "Growth trend?": "What is my growth trend?",
    "Any anomalies?": "Were there any unusual months?",
    "What to focus on?": "What should I focus on next?",
}
DOC_QUICK_QUESTIONS = {
    "Summary?": "Summarise this document in a few sentences.",
    "Key points?": "What are the key points?",
    "Dates?": "What important dates or deadlines are mentioned?",
    "Amounts?": "What amounts, prices or totals are mentioned?",
    "Actions?": "What actions or next steps does it ask for?",
}


def is_own_echo(heard: str) -> bool:
    """True if a 'question' is really iRaaya's last answer picked up by the mic."""
    answers = [m["content"] for m in st.session_state.chat_history if m["role"] == "assistant"]
    if not answers:
        return False
    last = re.sub(r"[^\w ]", "", answers[-1].lower())
    words = re.sub(r"[^\w ]", "", heard.lower()).split()
    if len(words) < 3:
        return False
    in_answer = sum(w in last.split() for w in words) / len(words)
    similar = difflib.SequenceMatcher(None, " ".join(words), last).ratio()
    return in_answer >= 0.8 or similar >= 0.6


def answer_question(question: str, asked_by_voice: bool = False) -> bool:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history]
    try:
        if is_document():
            answer = ask_document(
                question=question,
                document_text=document_context(st.session_state.doc_text, question),
                document_name=st.session_state.doc_name,
                language=selected_language, mode=selected_mode,
                api_key=GROQ_KEY, chat_history=history,
            )
        else:
            answer = ask_iraaya(
                question=question, data_context=data_context(question),
                language=selected_language, mode=selected_mode,
                api_key=GROQ_KEY, chat_history=history,
            )
    except Exception as e:
        show_error(e)
        return False

    now = datetime.now()
    wants_voice = speak_mode == "Always" or (speak_mode == "Match my question" and asked_by_voice)
    audio = speak(answer) if wants_voice else None
    answer_id = uuid.uuid4().hex
    st.session_state.chat_history += [
        {"id": uuid.uuid4().hex, "role": "user", "content": question,
         "time": now.strftime("%H:%M"), "date": now.strftime("%d %b %Y"), "voice": asked_by_voice},
        {"id": answer_id, "role": "assistant", "content": answer, "audio": audio,
         "time": now.strftime("%H:%M"), "date": now.strftime("%d %b %Y"), "lang": selected_language},
    ]
    st.session_state.play = {"id": answer_id, "via_recorder": asked_by_voice} if audio else None
    return True


def message_bubble(msg: dict, autoplay: bool = False):
    avatar = str(LOGO) if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        stamp = msg.get("time", "")
        if msg.get("date") and msg["date"] != datetime.now().strftime("%d %b %Y"):
            stamp = f"{msg['date']} {stamp}"
        extra = " · 🎤 asked by voice" if msg.get("voice") else ""
        if msg["role"] == "assistant" and msg.get("lang"):
            extra = f" · {msg['lang']}"
        st.markdown(f'<span class="msg-time">{stamp}{extra}</span>', unsafe_allow_html=True)
        if msg["role"] == "assistant":
            if msg.get("audio"):
                st.audio(msg["audio"], format="audio/mp3", autoplay=autoplay)
            copy_button(msg["content"], key=f"copy_{msg.get('id', id(msg))}")


if tab2.open:
    with tab2:
        if st.session_state.df is None and not is_document():
            st.info("Upload data or a document first to ask iRaaya questions! "
                    "Or try the sample data from the 📊 Dashboard tab.")
        elif A is None and not is_document():
            st.warning("No sales match the current filters, so there's nothing to ask about. "
                       "Reset the filters in the sidebar.")
        else:
            st.subheader(f"Ask iRaaya in {selected_language}")
            st.caption(f"🔊 {SPEAK_MODES[speak_mode]} · {voice_name_shown} · {speed} speed")
            if is_document():
                with st.expander("📄 How iRaaya sees your pages"):
                    st.caption(PAGE_SOURCES.get(st.session_state.doc_page_source, PAGE_SOURCES[None]))
                    for n, start in page_overview(st.session_state.doc_text):
                        st.markdown(f"**Page {n}** — {start}")
            else:
                show_filter_tags("answers")

            by_id = {m.get("id"): m for m in st.session_state.chat_history}
            play = st.session_state.play
            play_msg = by_id.get(play["id"]) if play else None
            # Voice answers play through the recorder's tap-unlocked channel
            # (so they start by themselves on iPhone/iPad too)
            spoken = voice_recorder(
                key="voice_recorder", turn=st.session_state.voice_q_n,
                play=({"id": play_msg["id"], "audio": play_msg["audio"]}
                      if play_msg and play.get("via_recorder") and play_msg.get("audio") else None),
            )
            if st.session_state.pop("voice_warning", None):
                st.warning("I didn't catch a question. Tap the mic and try again, or type it below.")
            with st.expander("Mic not working? Use the basic recorder"):
                basic = st.audio_input("Tap the mic, speak, then tap stop",
                                       key=f"voice_q_{st.session_state.voice_q_n}")
            recording = spoken or ((basic.getvalue(), "question.wav") if basic else None)

            quick = DOC_QUICK_QUESTIONS if is_document() else QUICK_QUESTIONS
            st.caption("Or tap a quick question, or type below:")
            cols = st.columns(len(quick))
            for col, (label, q) in zip(cols, quick.items()):
                if col.button(label, width="stretch"):
                    st.session_state.pending_question = (q, False)
            typed = st.chat_input("Type your question...", key="ask_input")
            if typed and typed.strip():
                st.session_state.pending_question = (typed.strip(), False)

            if recording is not None:
                st.session_state.voice_q_n += 1
                with st.spinner("Listening..."):
                    audio_bytes, audio_name = recording
                    heard = transcribe_audio_file(
                        audio_bytes, GROQ_KEY,
                        language=LANGUAGES[selected_language]["gtts_code"].split("-")[0],
                        filename=audio_name,
                        vocabulary=None if is_document() else vocabulary_hint(df),
                    ) if GROQ_KEY else ""
                if heard and is_own_echo(heard):
                    heard = ""   # the mic picked up iRaaya's own spoken answer
                if heard:
                    st.session_state.pending_question = (heard, True)
                else:
                    st.session_state.voice_warning = True
                st.rerun()      # reset the recorders, then answer

            pending = st.session_state.pending_question
            if pending:
                question, by_voice = pending
                st.session_state.pending_question = None
                with st.chat_message("user"):
                    st.markdown(question)
                with st.chat_message("assistant", avatar=str(LOGO)):
                    with st.spinner("iRaaya is typing…"):
                        ok = answer_question(question, by_voice)
                if ok:
                    st.rerun()

            history = st.session_state.chat_history
            if history:
                # Newest first: each question with its answer under it
                pairs, i = [], 0
                while i < len(history):
                    if history[i]["role"] == "user" and i + 1 < len(history):
                        pairs.append(history[i:i + 2]); i += 2
                    else:
                        pairs.append(history[i:i + 1]); i += 1
                for pair in reversed(pairs[-10:]):
                    for msg in pair:
                        fresh = bool(play and msg.get("id") == play["id"] and not play.get("via_recorder"))
                        message_bubble(msg, autoplay=fresh)
                if play:
                    st.session_state.play = None     # play each answer only once
                    st.caption("Didn't hear it? Tap ▶. Safari, iPhone and iPad sometimes block "
                               "sound that starts by itself.")

                st.divider()
                t = conversation_text(history, COMPANY)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    copy_button(t, key="copy_all", label="📋 Copy conversation")
                last_answer = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
                with c2:
                    copy_button(last_answer, key="copy_last", label="📋 Copy last answer")
                c3.download_button("⬇️ Save as text", t.encode("utf-8"), "iraaya_conversation.txt",
                                   "text/plain", width="stretch")
                try:
                    pdf, skipped = generate_conversation_pdf(history, COMPANY)
                    c4.download_button("⬇️ Save as PDF", pdf, "iraaya_conversation.pdf",
                                       "application/pdf", width="stretch")
                    if skipped:
                        st.caption(f"{skipped} message(s) are in a script the PDF can't show "
                                   "(e.g. Hindi, Arabic) — the text file has everything.")
                except Exception as e:
                    c4.caption(f"PDF not available right now ({e}). The text file works.")
                if st.button("🗑️ Clear chat"):
                    st.session_state.chat_history = []
                    st.session_state.play = None
                    st.rerun()

# ---------- Tab 3: Insights ----------
if tab3.open:
    with tab3:
        if is_document():
            st.info("Insights, forecasts and the health score work with sales data. For your "
                    "document, ask questions in **💬 Ask iRaaya** — try \"Summary?\" or \"Key points?\".")
        elif FULL_DF is None:
            st.info("Upload data first! Or try the sample data from the 📊 Dashboard tab.")
        elif A is None:
            st.warning("No sales match the current filters. Reset the filters in the sidebar.")
        else:
            show_filter_tags("insights, forecast and reports")
            if st.button("✨ Generate iRaaya Insights", type="primary"):
                try:
                    with st.spinner("Analysing your business..."):
                        st.session_state.insights = generate_insights(data_context(), GROQ_KEY, selected_language)
                    if not st.session_state.insights:
                        st.warning("iRaaya couldn't produce insights this time. Please try again.")
                except Exception as e:
                    show_error(e)

            if st.session_state.insights:
                st.subheader("iRaaya Insights")
                for insight in st.session_state.insights:
                    body = f"**{insight['title']}**\n\n{insight['detail']}"
                    if insight["type"] == "positive":
                        st.success(body, icon="✅")
                    elif insight["type"] == "warning":
                        st.error(body, icon="⚠️")
                    else:
                        st.info(body, icon="💡")
                insights_text = "iRaaya Insights\n\n" + "\n\n".join(
                    f"{n}. [{i['type']}] {i['title']}\n{i['detail']}"
                    for n, i in enumerate(st.session_state.insights, 1))
                c1, c2 = st.columns(2)
                with c1:
                    copy_button(insights_text, key="copy_insights", label="📋 Copy insights")
                c2.download_button("⬇️ Download insights (text)", insights_text.encode("utf-8"),
                                   "iraaya_insights.txt", "text/plain")

            st.divider()
            st.subheader("📈 Revenue Forecast")
            forecast_data = forecast_revenue(df)
            if forecast_data is None:
                st.info("At least 3 months of data are needed for a forecast.")
            else:
                st.plotly_chart(forecast_chart(forecast_data["historical"], forecast_data["forecast"],
                                               SYM, NSTYLE), width="stretch")
                cols = st.columns(4)
                for col, f in zip(cols, forecast_data["forecast"]):
                    col.metric(pd.Period(f["date"]).strftime("%b %Y"), money(f["predicted_revenue"]),
                               f"Likely {compact(f['low'])} – {compact(f['high'])}",
                               delta_color="off", delta_arrow="off")
                cols[3].metric("Trend fit", f"{forecast_data['fit_pct']:.0f}%",
                               forecast_data["trend"].capitalize(), delta_color="off", delta_arrow="off",
                               help="How closely past months follow a straight line (100% = perfectly). "
                                    "Higher means the trend is steadier — it is not a guarantee.")
                note = (f"Trend: **{forecast_data['trend']}** ({forecast_data['monthly_change_pct']:+}% per "
                        "month). The forecast follows the overall trend and does not include seasonal peaks.")
                if forecast_data["excluded_months"]:
                    note += " Unusual months left out: " + ", ".join(
                        pd.Period(m).strftime("%b %Y") for m in forecast_data["excluded_months"]) + "."
                st.caption(note)

            health = A["health"]
            st.divider()
            st.subheader("💊 Business Health Score")
            st.metric("iRaaya Score", f"{health['score']}/100", health["label"],
                      delta_color=health["color"], delta_arrow="off")
            for factor in health["factors"]:
                st.write(f"• {factor}")

            st.divider()
            st.subheader("📤 Export")
            col1, col2 = st.columns(2)
            with col1:
                st.caption(f"Report for **{COMPANY or 'My Business'}** — change the name in ⚙️ Settings.")
                try:
                    prev = previous_period(FULL_DF, date_start, date_end, choices)
                    summary = A["summary"]
                    pdf_bytes = generate_pdf(
                        summary, st.session_state.insights, forecast_data, COMPANY or "My Business",
                        health, A["anomalies"], SYM, NSTYLE, card_numbers(df, prev),
                        "; ".join(filter_tags), summary["monthly_revenue"],
                        summary["top_products"] if df.Product.nunique() > 1 else None,
                    )
                    st.download_button("📄 Download PDF Report", pdf_bytes, "iraaya_report.pdf",
                                       "application/pdf")
                    if not st.session_state.insights:
                        st.caption("Tip: generate insights first to include them in the PDF.")
                except Exception as e:
                    st.error(f"The PDF report couldn't be made this time ({e}). "
                             "Everything else still works — please try again.")
                st.download_button(
                    "⬇️ Download data (clean CSV)",
                    df.assign(Date=df.Date.dt.strftime("%Y-%m-%d")).to_csv(index=False).encode("utf-8-sig"),
                    "iraaya_data.csv", "text/csv",
                )
            with col2:
                if st.button("💬 Create WhatsApp Summary"):
                    try:
                        with st.spinner("Creating summary..."):
                            st.session_state.whatsapp = generate_whatsapp_summary(
                                data_context(), GROQ_KEY, selected_language)
                    except Exception as e:
                        show_error(e)
                if st.session_state.whatsapp:
                    st.code(st.session_state.whatsapp, language=None, wrap_lines=True)
                    copy_button(st.session_state.whatsapp, key="copy_whatsapp", label="📋 Copy summary")
                    st.link_button("Open in WhatsApp",
                                   "https://wa.me/?text=" + quote(st.session_state.whatsapp))

# ---------- Tab 4: Settings ----------
if tab4.open:
    with tab4:
        st.subheader("🏢 Your business")
        st.text_input("Company name", placeholder="My Business Name", key="company",
                      persist_state="session", help="Shown on the dashboard and in PDF reports.")
        c1, c2 = st.columns(2)
        c1.selectbox("Currency", list(CURRENCIES), key="currency", persist_state="session",
                     help="Shown on every card, chart and report, and told to the AI.")
        c2.selectbox("Number format", list(NUMBER_STYLES), key="number_style", persist_state="session")
        st.radio("Dates in my files are written", list(DATE_ORDERS), key="date_order",
                 persist_state="session", horizontal=True,
                 help="Only used when a file could be read either way (like 03/04/2025). "
                      "iRaaya works it out by itself whenever it can.")
        st.caption(f"Preview: {fmt_money(1234567.891, SYM, NSTYLE, 2)} · short form "
                   f"{fmt_compact(3977970, SYM, NSTYLE)}")

        st.subheader("🗣️ Language, style and voice")
        st.caption("Change these in the sidebar. Everything you choose — language, style, voice, "
                   "speed, currency, company — is remembered on this device and used next time.")
        if st.button("↺ Reset settings to defaults"):
            for key, value in SETTING_DEFAULTS.items():
                st.session_state[key] = value
            st.rerun()

        st.subheader("🔒 Your data")
        st.caption("iRaaya keeps your data, conversation and settings only in this browser on this "
                   "device (so a refresh or an app update doesn't lose them). To answer questions, "
                   "a summary is sent to Groq (AI); spoken answers use Google TTS or ElevenLabs.")
        if st.button("🧹 Clear all my data", type="secondary"):
            st.session_state.forget_pending = True
            st.rerun()

        st.subheader("ℹ️ About iRaaya")
        st.markdown(
            f"**iRaaya** version {VERSION} — your business, explained simply, in any language.  \n"
            "Built by **Riverrax** · [riverrax.com](https://riverrax.com) — launching 23 October 2026.  \n"
            "Named after Iraaya 🌸 — because every business deserves to be understood clearly, "
            "in any language."
        )
        # Re-read the data if the date setting changed since it was loaded
        loaded_with = st.session_state.get("_loaded_date_order")
        if (loaded_with and st.session_state.date_order != loaded_with
                and (st.session_state.source or {}).get("b64")):
            src = st.session_state.source
            data = base64.b64decode(src["b64"])
            load_upload(data, src["name"], hashlib.md5(data).hexdigest(), keep_history=True)
            st.rerun()

# ---------- Remember on this device ----------
parts = snapshot_parts()
hashes = {k: hashlib.md5(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()
          for k, v in parts.items()}
saved = st.session_state.setdefault("_saved", {})
clear = st.session_state.pop("_clear_device", False)
changed = {k: parts[k] for k in parts if hashes[k] != saved.get(k)}
ready = st.session_state.get("_restore_checked", False)
if clear:
    rev = uuid.uuid4().hex
    st.session_state._saved = {}
elif ready and changed:
    rev = uuid.uuid4().hex
    st.session_state._saved = hashes
else:
    rev = st.session_state.get("_store_rev")
st.session_state._store_rev = rev
restored = device_storage(save=changed if (ready and changed and not clear) else None,
                          clear=clear, rev=rev)
if restored is not None and not ready:
    st.session_state._restore_checked = True
    fresh = st.session_state.df is None and not is_document() and not st.session_state.chat_history
    if restored and fresh:
        st.session_state._restore = restored
    st.rerun()

# ---------- Footer ----------
st.divider()
st.caption("🎯 Powered by iRaaya · Built by Riverrax · riverrax.com")
