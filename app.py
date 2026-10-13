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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
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
    read_any_table,
    validate_data,
    vocabulary_hint,
)
from browser_tools import copy_button, device_storage
from charts import (
    MODEBAR,
    share_donut,
    weekday_chart,
    figure_data_text,
    table_charts,
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
    document_glance,
    explain_chart,
    summarise_period,
    ask_iraaya,
    generate_insights,
    generate_whatsapp_summary,
)
from languages import LANGUAGES
from metrics import (
    BUSINESS_PERIODS, FILTER_COLUMNS, apply_filters, breakdown, by_weekday, card_numbers, day_snapshot,
    fair_previous, growth_by, home_insights, more_cards, period_range, previous_period, previous_range,
    target_progress,
)
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
# iRaaya Ocean: 60% calm background, 30% deep navy, 10% aqua. The colour
# names below switch between day and night with the visitor's device.
OCEAN_LIGHT = """--ink:#0B2545; --muted:#5A6B85; --card:#FFFFFF; --line:#E3E9F1; --page:#F4F7FB;
  --navy:#0B2545; --navy2:#13315C; --ontop:#A9BCD6; --acc:#12C2B0; --acc-text:#0A8F82;
  --acc-soft:#DDF8F4; --on-acc:#062A26; --up:#16A34A; --down:#E5484D; --shadow:rgba(11,37,69,.08);"""
OCEAN_DARK = """--ink:#EEF3F9; --muted:#93A4BD; --card:#111C2F; --line:#1E2B42; --page:#08111F;
  --navy:#13315C; --navy2:#1A3D70; --ontop:#B9CBE3; --acc:#2EE0CC; --acc-text:#2EE0CC;
  --acc-soft:rgba(46,224,204,.13); --on-acc:#062A26; --up:#4ADE80; --down:#FF6B6B; --shadow:rgba(0,0,0,.35);"""
st.markdown(f"""
<style>
:root {{ {OCEAN_LIGHT} }}
@media (prefers-color-scheme: dark) {{ :root {{ {OCEAN_DARK} }} }}
""" + """
/* Number cards */
div[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 2px 10px var(--shadow);
}
div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 800; }
/* Chat: you on the right in navy, iRaaya on the left on a card */
div[data-testid="stChatMessage"] { width: 88% !important; border-radius: 16px; }
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
  flex-direction: row-reverse; background: var(--navy); margin-left: auto !important;
  border-radius: 16px 16px 4px 16px;
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) p { text-align: right; color: #fff; }
div[data-testid="stChatMessage"]:not(:has(div[data-testid="stChatMessageAvatarUser"])) {
  background: var(--card); border: 1px solid var(--line); margin-right: auto !important;
  border-radius: 16px 16px 16px 4px;
}
.msg-time { font-size: .72rem; color: var(--muted); }
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) .msg-time { color: var(--ontop); }
.tag { display: inline-block; background: var(--acc-soft); color: var(--acc-text); border-radius: 999px;
       padding: 2px 10px; margin: 2px 4px 2px 0; font-size: .8rem; font-weight: 600; }
/* A calm page with one soft aqua glow at the top */
[data-testid="stApp"] {
  background: radial-gradient(900px 420px at 50% -12%, color-mix(in srgb, var(--acc) 14%, transparent), transparent 70%), var(--page);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbarActions"] { display: none; }     /* "Fork" / GitHub links */
[data-testid="stFileUploaderDropzone"] { border: 1.5px dashed color-mix(in srgb, var(--acc) 60%, var(--line)); border-radius: 14px; }

/* ----- Tabs: a navy bar on every page except Home ----- */
.st-key-main_tab [role="tablist"] {
  background: var(--navy); border-radius: 14px; padding: 6px; gap: 4px; overflow-x: auto;
}
.st-key-main_tab [role="tab"] { border-radius: 10px; padding: 6px 12px; color: var(--ontop); }
.st-key-main_tab [role="tab"] p { color: inherit; font-weight: 600; }
.st-key-main_tab [role="tab"][aria-selected="true"] { background: var(--acc); color: var(--on-acc); }
.st-key-main_tab [role="tab"][aria-selected="true"] p { font-weight: 800; }
.st-key-main_tab .react-aria-SelectionIndicator, .st-key-main_tab [data-baseweb="tab-highlight"],
.st-key-main_tab [data-baseweb="tab-border"] { display: none !important; }

/* ----- Home ----- */
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 1.25rem; color: var(--ink); }
.brand svg { width: 34px; height: 34px; }
.welcome { text-align: center; padding: 18px 0 6px; }
.welcome svg { width: 92px; height: 92px; }
.welcome h1 { font-size: clamp(2.6rem, 7vw, 4rem); font-weight: 800; margin: 4px 0 0; padding: 0; letter-spacing: -.02em; color: var(--ink); }
.welcome h1 [data-testid="stHeaderActionElements"] { display: none; }
.welcome .tagline { font-size: 1.25rem; font-weight: 700; color: var(--acc-text); margin: 0; }
.welcome .lede { font-size: 1.02rem; color: var(--muted); max-width: 46ch; margin: 12px auto 0; line-height: 1.55; }
.tryask { position: relative; margin: 20px auto 6px; max-width: 560px; background: var(--navy); color: #fff;
  border-radius: 999px; padding: 12px 12px 12px 24px; display: flex; align-items: center; gap: 14px; text-align: left; }
.tryask .lbl { font-size: .7rem; letter-spacing: .08em; color: var(--ontop); font-weight: 700; }
.tryask .qs { position: relative; height: 1.5em; flex: 1; }
.tryask .qs span { position: absolute; inset: 0; font-weight: 600; opacity: 0; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; animation: cycle 15s infinite; }
.tryask .qs span:nth-child(2) { animation-delay: 3s; } .tryask .qs span:nth-child(3) { animation-delay: 6s; }
.tryask .qs span:nth-child(4) { animation-delay: 9s; } .tryask .qs span:nth-child(5) { animation-delay: 12s; }
@keyframes cycle { 0% { opacity: 0; } 3% { opacity: 1; } 18% { opacity: 1; } 21% { opacity: 0; } 100% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .tryask .qs span { animation: none; } .tryask .qs span:first-child { opacity: 1; } }
.bubble { width: 44px; height: 44px; flex: none; border-radius: 50%; background: var(--acc); color: var(--on-acc);
  display: flex; align-items: center; justify-content: center; font-size: 1.3rem; }
.snap { padding: 6px 0 4px; }
.snap .who { font-size: .9rem; font-weight: 700; color: var(--muted); }
.snap .big { font-size: clamp(1.9rem, 4.5vw, 2.6rem); font-weight: 800; color: var(--ink); line-height: 1.2; margin-top: 2px; }
.snap .delta { font-size: 1rem; font-weight: 800; margin-left: 8px; white-space: nowrap; }
.snap .file { font-size: .8rem; color: var(--muted); margin-top: 4px; }
.up { color: var(--up); } .down { color: var(--down); }
/* Big clickable cards: the picture is HTML, a see-through button on top does the click */
.st-key-hero_ask, .st-key-card_business, .st-key-card_summary { position: relative; }
.st-key-go_ask, .st-key-go_business, .st-key-go_summary { position: absolute; inset: 0; z-index: 3; margin: 0 !important;
  width: 100% !important; height: 100% !important; }
.st-key-go_ask div, .st-key-go_business div, .st-key-go_summary div { width: 100% !important; height: 100% !important; }
.st-key-go_ask button, .st-key-go_business button, .st-key-go_summary button {
  width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.hero-card { background: var(--navy); color: #fff; border-radius: 20px; padding: 22px 22px 22px 26px; display: flex;
  align-items: center; justify-content: space-between; gap: 14px; position: relative; overflow: hidden;
  transition: transform .12s ease; }
.hero-card::before { content: ""; position: absolute; right: -50px; top: -70px; width: 220px; height: 220px;
  border-radius: 50%; background: var(--navy2); }
.hero-card > * { position: relative; }
.hero-card .h { font-size: 1.45rem; font-weight: 800; }
.hero-card .s { font-size: .9rem; color: var(--ontop); margin-top: 4px; }
.mic { width: 64px; height: 64px; flex: none; border-radius: 50%; background: var(--acc); color: var(--on-acc);
  display: flex; align-items: center; justify-content: center; font-size: 1.8rem;
  box-shadow: 0 0 0 9px color-mix(in srgb, var(--acc) 24%, transparent); }
.st-key-hero_ask:hover .hero-card, .st-key-card_business:hover .tile, .st-key-card_summary:hover .tile { transform: translateY(-2px); }
.tile { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 18px; display: flex;
  align-items: center; gap: 14px; box-shadow: 0 2px 10px var(--shadow); transition: transform .12s ease; }
.ico { width: 46px; height: 46px; flex: none; border-radius: 13px; background: var(--acc-soft); color: var(--acc-text);
  display: flex; align-items: center; justify-content: center; font-size: 1.4rem; }
.tile .t { font-size: 1.1rem; font-weight: 800; color: var(--ink); }
.tile .d { font-size: .85rem; color: var(--muted); }
.st-key-slim button { background: var(--card); border: 1px solid var(--line); border-radius: 12px; min-height: 48px;
  color: var(--ink); font-weight: 700; justify-content: flex-start; }
.st-key-slim button span[role="img"] { color: var(--acc-text); }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 16px 18px; height: 100%; }
.panel h4 { margin: 0 0 10px; padding: 0; font-size: 1rem; font-weight: 800; color: var(--ink); }
.panel ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.panel li { display: flex; gap: 10px; align-items: flex-start; font-size: .93rem; color: var(--ink); line-height: 1.45; }
.panel li b { flex: none; width: 26px; height: 26px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: .85rem; }
.panel li b.up { background: color-mix(in srgb, var(--up) 15%, transparent); }
.panel li b.down { background: color-mix(in srgb, var(--down) 15%, transparent); }
.panel li b.tip { background: var(--acc-soft); }
.bar { height: 12px; border-radius: 999px; background: color-mix(in srgb, var(--muted) 18%, transparent); overflow: hidden; margin: 8px 0; }
.bar i { display: block; height: 100%; border-radius: 999px; background: var(--acc); }
.panel .big { font-size: 1.5rem; font-weight: 800; color: var(--ink); }
.panel .note { font-size: .85rem; color: var(--muted); }
/* The three ways to start */
.st-key-opt_sales, .st-key-opt_sample, .st-key-opt_any {
  background: var(--card); border-radius: 18px !important; min-height: 100%; box-shadow: 0 2px 10px var(--shadow);
}
/* Phones */
@media (max-width: 640px) {
  div.stButton > button, div.stDownloadButton > button { width: 100%; }
  .st-key-topbar div.stButton > button { width: auto; }
  div[data-testid="stChatMessage"] { width: 96% !important; }
  div[data-testid="stMetricValue"] { font-size: 1.35rem; }
  .hero-card .h { font-size: 1.2rem; }
  .mic { width: 54px; height: 54px; font-size: 1.5rem; }
  /* Tabs become an icon bar at the bottom of the screen, mic in the middle */
  .st-key-main_tab [role="tablist"] {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; border-radius: 0; justify-content: space-around;
    background: var(--card); border-top: 1px solid var(--line); padding: 6px 4px calc(8px + env(safe-area-inset-bottom, 0px));
    overflow: visible;
  }
  .st-key-main_tab [role="tab"] { flex: 1; justify-content: center; padding: 6px 2px; color: var(--muted); background: transparent !important; }
  .st-key-main_tab [role="tab"] p { font-size: 10px !important; line-height: 1.15; text-align: center;
    white-space: normal; font-weight: 700; }
  .st-key-main_tab [role="tab"] p span[role="img"] { display: block !important; margin: 0 auto 2px;
    font-size: 24px !important; line-height: 1; vertical-align: top !important; }
  .st-key-main_tab [role="tab"][aria-selected="true"] { color: var(--acc-text); }
  .st-key-main_tab [role="tab"]:nth-child(3) p span[role="img"] {
    background: var(--acc); color: var(--on-acc); border-radius: 50%; width: 46px; height: 46px; display: flex !important;
    align-items: center; justify-content: center; margin: -24px auto 2px; box-shadow: 0 0 0 5px var(--card); }
  [data-testid="stMainBlockContainer"] { padding-bottom: 96px; }
}
</style>
""", unsafe_allow_html=True)
_theme = getattr(st.context.theme, "type", None)
if _theme in ("light", "dark"):     # the theme chosen in the app wins over the device setting
    st.markdown(f"<style>:root {{ {OCEAN_DARK if _theme == 'dark' else OCEAN_LIGHT} }}</style>",
                unsafe_allow_html=True)

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
    "doc_tables": [],        # tables found in the document: [{"page": n, "rows": [...]}]
    "doc_kind": None,        # "document" or "table" (a spreadsheet that isn't sales data)
    "doc_glance": None,      # AI summary + checked key numbers
    "period_summaries": {},  # written summaries per period
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
    "target": 0.0,           # monthly sales target (0 = none)
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
        for key in [f"f_{c}" for c in FILTER_COLUMNS] + ["f_dates", "biz_dates", "biz_view", "sales_search"]:
            st.session_state.pop(key, None)
    return True


def set_document(text: str, name: str, pages, data_key: str, page_source, source: dict,
                 keep_history: bool = False, tables: list = None, kind: str = "document"):
    """Keep a document (or a spreadsheet that isn't sales data) to show and
    answer questions about."""
    st.session_state.doc_tables = tables or []
    st.session_state.doc_kind = kind
    if not keep_history:
        st.session_state.doc_glance = None
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
        st.session_state.period_summaries = {}


def table_as_document(data: bytes, name: str, data_key: str, source: dict, keep_history: bool):
    """A spreadsheet without a date + amount: show it as a table, chart it,
    and let people ask about it."""
    f = io.BytesIO(data)
    f.name = name
    raw = read_any_table(f)
    rows = [list(map(str, raw.columns))] + raw.head(500).astype(str).values.tolist()
    text = raw.head(400).to_csv(index=False)
    set_document(text, name, None, data_key, "table", source, keep_history,
                 tables=[{"page": None, "rows": rows}], kind="table")
    return True


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
                     source, keep_history, tables=doc.get("tables"))
        return True
    df, report = parse_table_file(data, name, order)
    if progress:
        progress.progress(75, text="Analysing…")
    if not validate_data(_with_report(df, report))["is_valid"]:
        # Not sales data (no date + amount): still useful as a table
        return table_as_document(data, name, data_key, source, keep_history)
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
                         src, keep_history=True, tables=d.get("tables"), kind=d.get("kind") or "document")
            st.session_state.doc_glance = d.get("glance")
    except Exception:
        pass    # a file that can't be read again is simply not restored
    history = []
    for m in rec.get("chat") or []:
        m = dict(m)
        m["audio"] = base64.b64decode(m.pop("audio_b64")) if m.get("audio_b64") else None
        history.append(m)
    st.session_state.chat_history = history
    extras = rec.get("extras") or {}
    for key in ("insights", "whatsapp", "cloned_voice_id", "cloned_voice_name", "period_summaries"):
        if key in extras:
            st.session_state[key] = extras[key]
    for key, value in (extras.get("filters") or {}).items():
        if key in ("f_dates", "biz_dates") and value:
            value = tuple(pd.Timestamp(v).date() for v in value)
        if key == "f_dates":
            continue
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
               "key": st.session_state.data_key, "tables": st.session_state.doc_tables,
               "kind": st.session_state.doc_kind, "glance": st.session_state.doc_glance}
        src = {"kind": "document"}
    chat = [{**{k: v for k, v in m.items() if k != "audio"}, "audio_b64": _audio_b64(m)}
            for m in st.session_state.chat_history[-20:]]
    filters = {k: (list(map(str, st.session_state[k])) if k == "biz_dates" else st.session_state[k])
               for k in ["biz_period", "biz_view", "biz_dates"] + [f"f_{c}" for c in FILTER_COLUMNS]
               if st.session_state.get(k)}
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
            "period_summaries": st.session_state.period_summaries,
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


def user_now() -> datetime:
    """The time where the visitor is (the server runs on UTC)."""
    try:
        if st.context.timezone:
            return datetime.now(ZoneInfo(st.context.timezone))
    except Exception:
        pass
    try:
        offset = st.context.timezone_offset       # minutes, as the browser reports it
        if offset is not None:
            return datetime.now(timezone(timedelta(minutes=-offset)))
    except Exception:
        pass
    return datetime.now()


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


SCORE_HELP = ("The iRaaya Score (0–100) starts at 50. It goes up when sales are growing (comparing your "
              "first and last 3 months, up to +25) and steady from month to month (up to +15), and when "
              "you sell 4 or more products (+10). It goes down when sales are falling (−15) or very "
              "uneven (−10). 80+ is Excellent, 60+ Good, 40+ Average, below 40 Needs attention.")


# ---------- Navigation ----------
TAB_LABELS = [":material/home: Home", ":material/bar_chart: My business", ":material/mic: Ask iRaaya",
              ":material/calendar_month: Summary", ":material/lightbulb: Tips & reports",
              ":material/settings: Settings"]
HOME, BUSINESS, ASK, SUMMARY, TIPS, SETTINGS = TAB_LABELS


def go(label: str):
    """Button callback: open a tab (runs before the page is drawn)."""
    st.session_state.main_tab = label


if "_goto" in st.session_state:           # e.g. after a file is loaded
    st.session_state.main_tab = st.session_state.pop("_goto")


# ---------- Sidebar: data ----------
st.sidebar.caption("Your Business Voice · by Riverrax")
if st.session_state.data_key is None:
    st.sidebar.info("👋 Start on the **🏠 Home** screen: add your file, or try the sample.")
else:
    st.sidebar.button("📂 Add a different file", width="stretch", on_click=go, args=(HOME,))

if is_document():
    pages = st.session_state.doc_pages
    st.sidebar.success(
        f"Loaded: {st.session_state.doc_name}"
        + (f" ({pages} page{'s' if pages != 1 else ''})" if pages else "")
    )

# ---------- Data ----------
# Ask iRaaya, Summary and Tips always use the whole file; the period and
# filters on the My business page only change that page.
FULL_DF = st.session_state.df
df = FULL_DF
filter_tags, choices = [], {}
date_start = date_end = None
if FULL_DF is not None:
    st.sidebar.success(f"Loaded: {st.session_state.data_name} ({len(FULL_DF):,} rows)")
    for w in st.session_state.warnings:
        st.sidebar.warning(w)
    date_start, date_end = FULL_DF.Date.min().date(), FULL_DF.Date.max().date()
FILTERED = False


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
                      delta_color=health["color"], delta_arrow="off", help=SCORE_HELP)

st.sidebar.divider()

# ---------- Language, style and voice (set on the Settings page) ----------
SPEAK_MODES = {
    "Match my question": "Spoken answer when you ask by voice, text when you type",
    "Always": "Every answer is spoken",
    "Never": "Text answers only (voice off)",
}
speak_mode = st.session_state.speak if st.session_state.speak in SPEAK_MODES else "Match my question"
speed = st.session_state.speed if st.session_state.speed in SPEEDS else "Normal"
use_elevenlabs = bool(st.session_state.premium and EL_KEY)

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


def premium_voices() -> dict:
    voices = cached_voices(EL_KEY) if use_elevenlabs else {}
    if voices and st.session_state.cloned_voice_id:
        # Only the person who made the clone sees it (this device only)
        voices = {f"{st.session_state.cloned_voice_name} (your voice)": st.session_state.cloned_voice_id, **voices}
    return voices


premium_voice_id, voice_name_shown = DEFAULT_VOICE_ID, "Standard voice (free)"
if use_elevenlabs:
    _voices = premium_voices()
    if _voices:
        _choice = st.session_state.get("voice_choice")
        if _choice not in _voices:
            _choice = next((n for n, v in _voices.items()
                            if v == (st.session_state.cloned_voice_id or DEFAULT_VOICE_ID)), next(iter(_voices)))
        premium_voice_id, voice_name_shown = _voices[_choice], _choice.split(" - ")[0]


def speak(text: str):
    """Spoken answer in the chosen language, voice and speed (or None)."""
    audio = None
    if use_elevenlabs:
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


def voice_settings():
    """Language, answer style and voice — drawn on the Settings page."""
    c1, c2 = st.columns(2)
    c1.selectbox(
        "🌍 Language", options=list(LANGUAGES.keys()), key="lang", persist_state="session",
        format_func=lambda n: n if LANGUAGES[n]["display"] == n else f"{n} · {LANGUAGES[n]['display']}",
        help="iRaaya listens, answers and speaks in this language.")
    c2.radio("💬 How should iRaaya talk?", ["Professional", "Simple", "Friendly"], horizontal=True,
             key="style", persist_state="session")
    c1, c2 = st.columns(2)
    c1.radio("Spoken answers", list(SPEAK_MODES), captions=list(SPEAK_MODES.values()), key="speak",
             persist_state="session")
    with c2:
        st.select_slider("Speed", options=SPEEDS, key="speed", persist_state="session")
        st.toggle("🎙️ Premium voice", disabled=not EL_KEY, key="premium", persist_state="session",
                  help=("Uses ElevenLabs for more natural voice output."
                        if EL_KEY else "Add ELEVENLABS_API_KEY to enable premium voice."))
        if st.session_state.speed == "Fast" and not (st.session_state.premium and EL_KEY):
            st.caption("⚡ Fast needs Premium voice — the free voice speaks at normal speed.")
        voices = premium_voices() if (st.session_state.premium and EL_KEY) else {}
        if voices:
            names = list(voices)
            if st.session_state.get("voice_choice") not in names:
                st.session_state.voice_choice = next(
                    (n for n, v in voices.items() if v == (st.session_state.cloned_voice_id or DEFAULT_VOICE_ID)),
                    names[0])
            st.selectbox("🗣️ Voice", names, key="voice_choice", persist_state="session")
    st.caption(f"Active: **{selected_language}** · {voice_name_shown} · {speed} speed")
    if st.button("▶ Preview voice"):
        audio = preview_audio(selected_language, use_elevenlabs, premium_voice_id, speed)
        if audio:
            st.audio(audio, format="audio/mp3", autoplay=True)
        else:
            st.warning("Voice isn't available right now.")

    with st.expander("🔬 Clone a voice"):
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


st.sidebar.caption(f"🗣️ {selected_language} · {voice_name_shown} · {speed} speed")
st.sidebar.button("Change language or voice", icon=":material/tune:", width="stretch",
                  on_click=go, args=(SETTINGS,), key="sb_settings")

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
        st.caption(f"You're looking at part of your data — {where} only use this part. "
                   "Change it in the sidebar (🔎 Narrow down).")


def escape_html(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------- Main area ----------
if st.session_state.get("main_tab") not in TAB_LABELS:
    st.session_state.pop("main_tab", None)
# on_change="rerun": only the open tab's content runs (faster), and the open
# tab is remembered
if st.session_state.get("main_tab", HOME) == HOME:
    # Home has its own big buttons, so the tab bar is hidden there
    st.markdown('<style>.st-key-main_tab [role="tablist"] { display: none; }</style>', unsafe_allow_html=True)
home_tab, tab1, tab2, sum_tab, tab3, tab4 = st.tabs(TAB_LABELS, key="main_tab", on_change="rerun")


ANY_TYPES = ["csv", "xlsx", "xls", "pdf", "docx", "txt"]


def handle_upload(uploaded):
    """Load a file chosen on the Home screen, then open the results."""
    if uploaded is None:
        return
    data = uploaded.getvalue()
    key = hashlib.md5(data).hexdigest()
    if key == st.session_state.data_key:
        return
    progress = st.progress(10, text="Getting your file…")
    try:
        loaded = load_upload(data, uploaded.name, key, progress=progress)
        progress.progress(100, text="Done!")
    except ValueError as e:
        progress.empty()
        st.error(f"😕 {e}")
        return
    except Exception as e:
        progress.empty()
        st.error("😕 iRaaya couldn't open this file. Please check it opens normally on your device, "
                 "or try saving it again as Excel. Files iRaaya can open: Excel (.xlsx, .xls), CSV, "
                 f"PDF, Word (.docx) and text (.txt). (Details: {e})")
        return
    progress.empty()
    if loaded:
        st.session_state._goto = BUSINESS
        st.rerun()


def start_options():
    """The three ways to begin — in plain words, no technical knowledge needed."""
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True, key="opt_sales"):
        st.markdown("#### :material/table_chart: My sales file")
        st.caption("Your sales from Excel, your billing machine, shop software or accountant. "
                   "It just needs a **date** and an **amount**.")
        handle_upload(st.file_uploader("Choose your sales file", type=["csv", "xlsx", "xls"],
                                       key="up_sales"))
    with c2.container(border=True, key="opt_sample"):
        st.markdown("#### :material/auto_awesome: Just looking?")
        st.caption("See iRaaya work with a sample shop's sales — nothing to upload.")
        if st.button("Try with sample data", type="primary", width="stretch", icon=":material/play_arrow:"):
            load_sample()
            st.session_state._goto = BUSINESS
            st.rerun()
        st.download_button("Download the sample file", SAMPLE_FILE.read_bytes(), "sample_data.csv",
                           "text/csv", width="stretch", icon=":material/download:")
    with c3.container(border=True, key="opt_any"):
        st.markdown("#### :material/description: Any other file")
        st.caption("A PDF or Word document, a price list, stock sheet, report or notes. "
                   "iRaaya shows it visually and answers questions about it.")
        handle_upload(st.file_uploader("Choose any file", type=ANY_TYPES, key="up_any"))
    with st.expander("❓ Where do I find my file?"):
        st.markdown(
            "- **On WhatsApp:** open the chat with the file → tap the file → **Share** → "
            "**Save to Files** (iPhone/iPad) or find it in **Downloads** (Android). Then come back "
            "here and tap **Browse files**.\n"
            "- **In your email:** open the email → tap the attachment → **Save to Files / Download**.\n"
            "- **From Excel or Google Sheets:** **File → Download / Save as → Excel (.xlsx)**.\n"
            "- **From shop or accounting software** (Tally, Petpooja, Square, Shopify, QuickBooks, Xero…): "
            "look for **Reports → Sales → Export → Excel**.\n"
            "- **No file yet?** Tap **✨ Try with sample data** to see how iRaaya works."
        )
        st.caption("What happens next: iRaaya reads your file, shows your business in simple cards "
                   "and charts, and you can ask questions by voice — in your language.")


TRY_ASKING = [
    "Which product sold most last month?",
    "How were sales this week?",
    "बिक्री पिछले महीने से कम क्यों है?",
    "Which branch is growing fastest?",
    "¿Cuál fue mi mejor día?",
]
def set_target():
    """Popover callback: save the monthly target typed on Home."""
    st.session_state.target = float(st.session_state.get("target_entry") or 0)


def top_bar():
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute",
                      key="topbar"):
        st.markdown(f'<div class="brand">{LOGO_SVG}iRaaya</div>', unsafe_allow_html=True, width="content")
        st.button("Settings", icon=":material/settings:", key="home_settings", on_click=go, args=(SETTINGS,),
                  type="tertiary")


def big_card(key: str, target: str, label: str, html: str):
    """A whole card that opens a page when tapped."""
    with st.container(key=key):
        st.markdown(html, unsafe_allow_html=True)
        st.button(label, key=key.replace("card_", "go_").replace("hero_", "go_"), on_click=go, args=(target,))


def snapshot():
    """Top of Home: the most useful number first, instead of a greeting."""
    who = COMPANY or "Your business"
    today = user_now().date()
    name = escape_html(st.session_state.data_name or "")
    if FULL_DF is None:
        kind = "table" if st.session_state.doc_kind == "table" else "document"
        pages = st.session_state.doc_pages
        st.markdown(
            f'<div class="snap"><div class="who">{escape_html(who)} · {today:%A %d %b}</div>'
            f'<div class="big">📄 {escape_html(st.session_state.doc_name or "")}</div>'
            f'<div class="file">Your {kind}{f" · {pages} pages" if pages else ""}</div></div>',
            unsafe_allow_html=True)
        return
    snap = day_snapshot(FULL_DF, today)
    if snap["is_today"]:
        when, head = f"{today:%A %d %b}", f"Today {money(snap['total'])}"
    else:
        when = f"{today:%A %d %b} · no sales in your file today"
        head = f"{snap['day']:%a %d %b %Y}: {money(snap['total'])}"
    delta = ""
    if snap["pct"] is not None:
        up = snap["pct"] >= 0
        delta = (f'<span class="delta {"up" if up else "down"}">{"▲" if up else "▼"} {abs(snap["pct"]):.0f}% '
                 f'vs a usual {snap["day"]:%A}</span>')
    latest = "" if snap["is_today"] else " (the latest day in your file)"
    st.markdown(
        f'<div class="snap"><div class="who">{escape_html(who)} · {when}</div>'
        f'<div class="big">{escape_html(head)}{delta}</div>'
        f'<div class="file">📂 {name} · {len(FULL_DF):,} sales{latest}</div></div>',
        unsafe_allow_html=True)


def things_to_know():
    facts = home_insights(FULL_DF, money, ALL)
    icon = {"up": ("▲", "up"), "down": ("▼", "down"), "tip": ("💡", "tip")}
    if facts:
        items = "".join(f'<li><b class="{icon[f["kind"]][1]}">{icon[f["kind"]][0]}</b>{escape_html(f["text"])}</li>'
                        for f in facts)
    else:
        items = "<li><b class=\"tip\">💡</b>Add a file with at least 2 weeks of daily sales to see what's changing.</li>"
    st.markdown(f'<div class="panel"><h4>Things to know</h4><ul>{items}</ul></div>', unsafe_allow_html=True)


def target_panel():
    target = float(st.session_state.target or 0)
    prog = target_progress(FULL_DF, target, user_now().date()) if target else None
    if prog:
        pct = prog["pct"]
        if prog["current"]:
            note = (f"{prog['days_left']} day{'s' if prog['days_left'] != 1 else ''} left · about "
                    f"{money(prog['per_day'])} a day needed" if prog["per_day"] else
                    "Target reached — well done! 🎉" if pct >= 100 else "Last day of the month")
        else:
            note = f"{prog['month'].strftime('%B %Y')} is the latest month in your file"
        st.markdown(
            f'<div class="panel"><h4>Monthly target · {prog["month"].strftime("%B %Y")}</h4>'
            f'<div class="big">{money(prog["sold"])} <span class="note">of {money(target)}</span></div>'
            f'<div class="bar"><i style="width:{min(pct, 100):.0f}%"></i></div>'
            f'<div class="note"><b>{pct:.0f}% there</b> · {note}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="panel"><h4>Monthly target</h4><div class="note">Set a sales goal for the '
                    'month and iRaaya shows how close you are, and how much you need each day.</div></div>',
                    unsafe_allow_html=True)
    with st.popover("Change target" if target else "Set a monthly target", icon=":material/flag:", width="stretch"):
        st.number_input(f"Monthly sales target{f' ({SYM})' if SYM else ''}", min_value=0.0, step=1000.0,
                        value=target, key="target_entry")
        st.button("Save target", type="primary", on_click=set_target, width="stretch")


def new_file_box():
    if st.session_state.get("show_new_file"):
        with st.container(border=True, key="new_file"):
            st.markdown("#### 📂 Look at a different file")
            st.caption("Your current work stays saved until the new file opens.")
            handle_upload(st.file_uploader("Choose a file", type=ANY_TYPES, key="up_new"))
            if st.button("Cancel"):
                st.session_state.show_new_file = False
                st.rerun()


def home():
    top_bar()
    if st.session_state.data_key is None:
        questions = "".join(f"<span>“{escape_html(q)}”</span>" for q in TRY_ASKING)
        st.markdown(
            f'<div class="welcome">{LOGO_SVG}<h1>iRaaya</h1><p class="tagline">Your business voice</p>'
            '<p class="lede">Add your sales file, then ask anything by voice or text, in any language. '
            'iRaaya answers with numbers, charts and plain words.</p>'
            f'<div class="tryask"><div style="flex:1;min-width:0"><div class="lbl">TRY ASKING</div>'
            f'<div class="qs">{questions}</div></div><div class="bubble">💬</div></div></div>',
            unsafe_allow_html=True)
        st.write("")
        start_options()
        return
    snapshot()
    doc = FULL_DF is None
    big_card("hero_ask", ASK, "Ask iRaaya",
             '<div class="hero-card"><div><div class="h">What would you like to know'
             f'{" about it" if doc else ""}?</div><div class="s">Tap here and ask by voice or text, '
             'in any language</div></div><div class="mic">🎤</div></div>')
    c1, c2 = st.columns(2)
    with c1:
        big_card("card_business", BUSINESS, "My business",
                 '<div class="tile"><div class="ico">📊</div><div><div class="t">'
                 f'{"Your file" if doc else "My business"}</div><div class="d">'
                 f'{"Summary, key numbers and charts" if doc else "Cards and charts"}</div></div></div>')
    with c2:
        big_card("card_summary", SUMMARY, "Summary",
                 '<div class="tile"><div class="ico">📅</div><div><div class="t">Summary</div>'
                 '<div class="d">Today, this week, this month</div></div></div>')
    with st.container(key="slim"):
        s1, s2, s3 = st.columns(3)
        s1.button("Tips & reports", icon=":material/lightbulb:", width="stretch", on_click=go, args=(TIPS,), key="slim_tips")
        s2.button("Settings", icon=":material/settings:", width="stretch", on_click=go, args=(SETTINGS,), key="slim_settings")
        if s3.button("New file", icon=":material/upload_file:", width="stretch", key="slim_new"):
            st.session_state.show_new_file = True
    new_file_box()
    if not doc:
        p1, p2 = st.columns(2)
        with p1:
            things_to_know()
        with p2:
            target_panel()


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


def document_view():
    """A document or non-sales table, shown visually."""
    kind = st.session_state.doc_kind or "document"
    name = st.session_state.doc_name
    st.subheader(f"{'📋' if kind == 'table' else '📄'} {name} — at a glance")
    if kind == "table":
        st.caption("This file doesn't look like sales (no date + amount), so iRaaya shows it as a "
                   "table and charts. You can still ask questions about it in 💬 Ask iRaaya.")

    glance = st.session_state.doc_glance
    if glance is None and GROQ_KEY:
        try:
            with st.spinner("iRaaya is reading it for you…"):
                glance = document_glance(document_context(st.session_state.doc_text), name,
                                         GROQ_KEY, selected_language)
            st.session_state.doc_glance = glance
        except Exception as e:
            show_error(e)
    if glance:
        with st.container(border=True):
            st.markdown("**✍️ In short**")
            st.markdown(glance["summary"])
            c1, c2 = st.columns([1, 1])
            if c1.button("🔊 Read it to me", key="read_glance"):
                audio = speak(glance["summary"])
                if audio:
                    st.audio(audio, format="audio/mp3", autoplay=True)
            with c2:
                copy_button(glance["summary"], key="copy_glance")
        numbers = glance.get("key_numbers") or []
        if numbers:
            st.markdown("**🔢 Key numbers**")
            for row in range(0, len(numbers), 3):
                cols = st.columns(3)
                for col, k in zip(cols, numbers[row:row + 3]):
                    col.metric(k["label"], k["value"],
                               f"Page {k['page']}" if k.get("page") else None,
                               delta_color="off", delta_arrow="off", help=f"“{k['quote']}”")
            st.caption("Every number above was checked: it appears word-for-word in your file "
                       "(hover or tap ⓘ to see the sentence).")

    tables = st.session_state.doc_tables or []
    charted = 0
    for n, t in enumerate(tables, 1):
        figs = table_charts(t["rows"])
        where = f" (page {t['page']})" if t.get("page") else ""
        if figs:
            st.markdown(f"**📊 Table {n}{where} as charts**")
            cols = st.columns(min(len(figs), 2))
            for i, fig in enumerate(figs):
                with cols[i % len(cols)]:
                    show_chart(fig, f"tbl_{n}_{i}")
            charted += 1
        with st.expander(f"See table {n}{where}"):
            head, body = t["rows"][0], t["rows"][1:]
            st.dataframe(pd.DataFrame([r[:len(head)] + [""] * (len(head) - len(r)) for r in body],
                                      columns=[str(h) or f"Column {i + 1}" for i, h in enumerate(head)]),
                         hide_index=True, width="stretch")
    if not tables and kind == "document":
        st.caption("No tables found in this document — the summary and key numbers above show "
                   "what matters. Ask anything in 💬 Ask iRaaya.")
    st.button("💬 Ask a question about it", type="primary", on_click=go, args=(ASK,))


def metric_delta(value, text="vs before"):
    return None if value is None else f"{value:+.1f}% {text}"


SHARE_TIP = ("📷 To share a chart as a picture: hover over it (or tap it on a phone), then tap the "
             "camera icon at its top right. Send the saved picture on WhatsApp or email.")


def show_chart(fig, key: str):
    """A chart with an "Explain this chart" button under it."""
    st.plotly_chart(fig, width="stretch", key=key, config=MODEBAR)
    title = re.sub(r"^\W+", "", str(fig.layout.title.text or "this chart")).strip()
    data_text = figure_data_text(fig)
    if not data_text:
        return
    ekey = hashlib.md5(f"{title}|{data_text}|{selected_language}|{selected_mode}".encode()).hexdigest()
    store = st.session_state.setdefault("chart_explain", {})
    text = store.get(ekey)
    if text is None and st.button("Explain this chart", key=f"ex_{key}", icon=":material/forum:",
                                  type="tertiary"):
        note = (f"All money values are in {currency[1]}." if currency
                else "No currency is set: don't use a currency symbol.")
        try:
            with st.spinner("iRaaya is reading the chart…"):
                text = explain_chart(title, data_text, note, GROQ_KEY, selected_language, selected_mode)
            store[ekey] = text
        except Exception as e:
            show_error(e)
    if text:
        with st.container(border=True):
            st.markdown(f"**{title}:** {text}")
            c1, c2 = st.columns(2)
            if c1.button("🔊 Read it to me", key=f"read_ex_{key}", width="stretch"):
                audio = speak(text)
                if audio:
                    st.audio(audio, format="audio/mp3", autoplay=True)
            with c2:
                copy_button(text, key=f"copy_ex_{key}", label="📋 Copy")


# ---------- Home ----------
if home_tab.open:
    with home_tab:
        home()

# ---------- Tab 1: My business ----------
def clear_biz_filters():
    for col in FILTER_COLUMNS:
        st.session_state.pop(f"f_{col}", None)


def biz_controls():
    """Period buttons and filter chips at the top of My business.
    Returns (start, end, choices, label)."""
    min_d, max_d = FULL_DF.Date.min().date(), FULL_DF.Date.max().date()
    if st.session_state.get("biz_period") not in BUSINESS_PERIODS:
        st.session_state.biz_period = "Last 30 days"
    period = st.segmented_control("Time period", BUSINESS_PERIODS, key="biz_period", persist_state="session",
                                  width="stretch", label_visibility="collapsed") or "Last 30 days"
    chosen = None
    if period == "Choose dates":
        saved = st.session_state.get("biz_dates")
        if not (isinstance(saved, (list, tuple)) and len(saved) == 2 and min_d <= saved[0] <= saved[1] <= max_d):
            st.session_state.biz_dates = (max(min_d, max_d - timedelta(days=29)), max_d)
        picked = st.date_input("From – to", key="biz_dates", min_value=min_d, max_value=max_d,
                               persist_state="session")
        chosen = (picked if isinstance(picked, (list, tuple)) and len(picked) == 2
                  else (picked[0], picked[0]) if isinstance(picked, (list, tuple)) else (picked, picked))
    start, end = period_range(FULL_DF, period, chosen)

    picks = {}
    with st.container(horizontal=True, key="biz_filters"):
        for col, label in FILTER_COLUMNS.items():
            values = sorted(FULL_DF[col].dropna().astype(str).unique()) if col in FULL_DF.columns else []
            if len(values) < 2 or set(values) == {ALL}:
                continue
            current = [v for v in st.session_state.get(f"f_{col}", []) if v in values]
            shown = "All" if not current else current[0] if len(current) == 1 else f"{len(current)} chosen"
            with st.popover(f"{label}: {shown}", icon=":material/filter_list:"):
                picks[col] = st.multiselect(label, values, key=f"f_{col}", persist_state="session",
                                            placeholder=f"All {label.lower()}")
            picks.setdefault(col, current)
        if any(picks.values()):
            st.button("Clear filters", icon=":material/close:", on_click=clear_biz_filters, type="tertiary")
    days = (end - start).days + 1
    if period == "All time":
        label = f"All your sales: {start:%d %b %Y} – {end:%d %b %Y}"
    elif period == "Choose dates":
        label = f"{start:%d %b %Y} – {end:%d %b %Y}"
    else:
        label = f"{start:%d %b} – {end:%d %b %Y} (the latest {period.split(' ', 1)[1]} in your file)"
    return start, end, picks, label


def money_table(table: pd.DataFrame, key: str, name_col: str, title: str):
    """A sortable table of products or places; tapping a row opens it."""
    cfg = {
        name_col: st.column_config.TextColumn(title),
        "Sales": st.column_config.NumberColumn(f"Sales{f' ({SYM})' if SYM else ''}", format="localized"),
        "Share": st.column_config.ProgressColumn("Share of sales", format="%.0f%%", min_value=0, max_value=100),
        "Units": st.column_config.NumberColumn("Units sold", format="localized"),
        "Transactions": st.column_config.NumberColumn("Sales count", format="localized"),
        "Change": st.column_config.NumberColumn("Change vs before", format="%+.1f%%"),
    }
    event = st.dataframe(table, hide_index=True, width="stretch", column_config=cfg, key=key,
                         on_select="rerun", selection_mode="single-row")
    rows = event.selection.rows if event and event.selection else []
    return table.iloc[rows[0]][name_col] if rows else None


def detail_view(col: str, name: str, now: pd.DataFrame, prev: pd.DataFrame, label: str):
    """Everything about one product or one place."""
    word = "product" if col == "Product" else "place"
    sub, sub_prev = now[now[col] == name], prev[prev[col] == name] if not prev.empty else prev
    st.markdown(f"### {'📦' if col == 'Product' else '📍'} {escape_html(name)}")
    st.caption(label)
    c = card_numbers(sub, sub_prev)
    more = more_cards(sub, sub_prev)
    total = now.Total_Revenue.sum() or 1
    m = st.columns(4)
    m[0].metric("💰 Sales", money(c["total"]), metric_delta(c["total_change"]))
    m[1].metric("📊 Share of all sales", f"{c['total'] / total * 100:.0f}%")
    m[2].metric("🧾 Sales count", f"{c['transactions']:,}", metric_delta(c["transactions_change"]))
    if more["units"] is not None:
        m[3].metric("📦 Units sold", f"{more['units']:,.0f}", metric_delta(more["units_change"]))
    else:
        m[3].metric("🧮 Average sale", money(more["avg_sale"]), metric_delta(more["avg_sale_change"]))
    span = (sub.Date.max() - sub.Date.min()).days if len(sub) else 0
    show_chart(revenue_by_month(sub, [], SYM, NSTYLE) if span > 62 else revenue_trend(sub, SYM, NSTYLE),
               f"d_trend_{word}")
    other, other_word = ("Region", "places") if col == "Product" else ("Product", "products")
    c1, c2 = st.columns(2)
    if sub[other].nunique() > 1:
        with c1:
            show_chart(regional_performance(sub, SYM, NSTYLE, growth_by(sub, sub_prev, other))
                       if other == "Region" else top_products(sub, SYM, NSTYLE), f"d_other_{word}")
    with c2:
        show_chart(weekday_chart(by_weekday(sub), SYM, NSTYLE), f"d_week_{word}")


def business_page():
    if COMPANY:
        st.subheader(f"🏢 {COMPANY}")
    data_preview()
    has_places = FULL_DF.Region.nunique() > 1 and set(FULL_DF.Region.unique()) != {ALL}
    has_products = FULL_DF.Product.nunique() > 1 and set(FULL_DF.Product.unique()) != {ALL}
    views = ["Overview"] + (["Products"] if has_products else []) + (["Places"] if has_places else []) + ["All my sales"]
    if st.session_state.get("biz_view") not in views:
        st.session_state.biz_view = "Overview"
    view = st.segmented_control("Show", views, key="biz_view", persist_state="session",
                                label_visibility="collapsed") or "Overview"
    start, end, picks, label = biz_controls()
    now = apply_filters(FULL_DF, start, end, picks)
    prev = fair_previous(FULL_DF, start, end, picks)
    ps, pe = previous_range(start, end)
    compare = (f"Compared with {ps:%d %b} – {pe:%d %b %Y}." if not prev.empty
               else "No ▲▼ changes: your file doesn't go back far enough to compare with the time before.")
    st.caption(f"📅 {label} · {compare}")
    if now.empty:
        st.warning("No sales match this period and these filters. Try a longer period or clear the filters.")
        return

    if view == "Products":
        table = breakdown(now, prev, "Product")
        name = money_table(table, "prod_table", "Product", "Product")
        st.caption("👆 Tap a row, or choose below, to look closer at a product. Tap a column name to sort.")
        name = name or st.selectbox("Look closer at", list(table["Product"]), index=None,
                                    placeholder="Choose a product…", key="focus_product")
        if name:
            detail_view("Product", name, now, prev, label)
        return
    if view == "Places":
        table = breakdown(now, prev, "Region")
        name = money_table(table, "place_table", "Region", "Place")
        st.caption("👆 Tap a row, or choose below, to look closer at a place. Tap a column name to sort.")
        name = name or st.selectbox("Look closer at", list(table["Region"]), index=None,
                                    placeholder="Choose a place…", key="focus_place")
        if name:
            detail_view("Region", name, now, prev, label)
        return
    if view == "All my sales":
        query = st.text_input("Search", placeholder="Search a product, place, payment… (e.g. UPI)",
                              key="sales_search", icon=":material/search:")
        rows = now.sort_values("Date", ascending=False)
        if query.strip():
            text = rows.drop(columns="Date").astype(str).apply(lambda c: c.str.contains(query.strip(), case=False, regex=False))
            rows = rows[text.any(axis=1)]
        st.caption(f"**{len(rows):,}** sales · total **{money(rows.Total_Revenue.sum())}** · newest first. "
                   "Tap a column name to sort.")
        shown = rows.assign(Date=rows.Date.dt.strftime("%d %b %Y"))
        st.dataframe(shown, hide_index=True, width="stretch", height=480,
                     column_config={"Total_Revenue": st.column_config.NumberColumn(
                         f"Sales{f' ({SYM})' if SYM else ''}", format="localized")})
        st.download_button("⬇️ Download these sales (CSV)",
                           rows.assign(Date=rows.Date.dt.strftime("%Y-%m-%d")).to_csv(index=False).encode("utf-8-sig"),
                           "iraaya_sales.csv", "text/csv")
        return

    # ----- Overview -----
    c = card_numbers(now, prev)
    more = more_cards(now, prev)
    r1 = st.columns(4)
    r1[0].metric("💰 Total sales", money(c["total"]), metric_delta(c["total_change"]))
    r1[1].metric("🧾 Sales count", f"{c['transactions']:,}", metric_delta(c["transactions_change"]))
    r1[2].metric("🧮 Average sale", money(more["avg_sale"]), metric_delta(more["avg_sale_change"]),
                 help="Total sales ÷ number of sales.")
    if more["units"] is not None:
        r1[3].metric("📦 Units sold", f"{more['units']:,.0f}", metric_delta(more["units_change"]))
    else:
        r1[3].metric("📈 Average month", money(c["avg_monthly"]))
    r2 = st.columns(4)
    if c["best_product"] not in (None, ALL):
        r2[0].metric("🏆 Best product", c["best_product"], f"{c['best_product_share']:.0f}% of sales",
                     delta_color="off", delta_arrow="off", help=str(c["best_product"]))
    if more.get("place"):
        r2[1].metric("📍 Best place", more["place"][0], f"{more['place'][1]:.0f}% of sales",
                     delta_color="off", delta_arrow="off")
    if more.get("best_day"):
        r2[2].metric("⭐ Best day", f"{more['best_day'][0]:%d %b %Y}", money(more["best_day"][1]),
                     delta_color="off", delta_arrow="off")
    if more.get("payment"):
        r2[3].metric("💳 Most used payment", more["payment"][0], f"{more['payment'][1]:.0f}% of sales",
                     delta_color="off", delta_arrow="off")
    elif more.get("customer"):
        r2[3].metric("👥 Main customers", more["customer"][0], f"{more['customer'][1]:.0f}% of sales",
                     delta_color="off", delta_arrow="off")

    span = (end - start).days
    anomalies = analyse(now)["anomalies"] if span > 62 else []
    if span > 62:
        show_chart(revenue_by_month(now, [a["month"] for a in anomalies], SYM, NSTYLE), "ch_month")
    show_chart(revenue_trend(now, SYM, NSTYLE), "ch_trend")
    has_p, has_r = now.Product.nunique() > 1, now.Region.nunique() > 1
    cols = st.columns(2) if has_p and has_r else [st.container()]
    if has_p:
        with cols[0]:
            show_chart(top_products(now, SYM, NSTYLE), "ch_products")
    if has_r:
        with cols[-1]:
            show_chart(regional_performance(now, SYM, NSTYLE, growth_by(now, prev, "Region")), "ch_regions")
    if now.Date.dt.normalize().nunique() >= 7:
        show_chart(weekday_chart(by_weekday(now), SYM, NSTYLE), "ch_weekday")
    donuts = [(col, title) for col, title in (("Payment_Method", "💳 How customers pay"),
                                              ("Customer_Type", "👥 Who buys"))
              if col in now.columns and now[col].nunique() > 1]
    if donuts:
        cols = st.columns(len(donuts))
        for col_box, (col, title) in zip(cols, donuts):
            with col_box:
                show_chart(share_donut(now, col, title, SYM, NSTYLE), f"ch_{col}")
    if has_p and span > 62:
        show_chart(product_comparison(now, SYM, NSTYLE), "ch_compare")
    st.caption(SHARE_TIP)

    if anomalies:
        st.subheader("⚠️ Unusual months")
        for a in anomalies:
            text = (f"**{pd.Period(a['month']).strftime('%B %Y')}**: sales were "
                    f"{abs(a['difference_pct'])}% {'below' if a['type'] == 'low' else 'above'} "
                    f"what the trend expected ({money(a['revenue'])} vs {money(a['expected'])})")
            if a["type"] == "low":
                st.error("📉 " + text)
            else:
                st.success("🎉 " + text)


if tab1.open:
    with tab1:
        if is_document():
            document_view()
        elif FULL_DF is None:
            st.markdown("#### 👋 Let's look at your business. How would you like to start?")
            start_options()
        else:
            business_page()

# ---------- Tab 2: Ask iRaaya ----------
DOC_QUICK_QUESTIONS = {
    "Summary?": "Summarise this document in a few sentences.",
    "Key points?": "What are the key points?",
    "Dates?": "What important dates or deadlines are mentioned?",
    "Amounts?": "What amounts, prices or totals are mentioned?",
    "Actions?": "What actions or next steps does it ask for?",
}


def personal_questions(data: pd.DataFrame) -> dict:
    """Quick questions that use the owner's own products, places and months."""
    qs = {}
    latest = data.Date.max()
    products = data.groupby("Product").Total_Revenue.sum().sort_values(ascending=False)
    if len(products) > 1 and products.index[0] != ALL:
        top = products.index[0]
        qs[f"How did {top} do in {latest:%B}?"] = f"How did {top} do in {latest:%B %Y}?"
    places = data.groupby("Region").Total_Revenue.sum().sort_values(ascending=False)
    if len(places) > 1 and places.index[0] != ALL:
        qs[f"Is {places.index[0]} growing?"] = f"Is {places.index[0]} growing?"
    if len(products) > 2 and products.index[-1] != ALL:
        qs[f"Why is {products.index[-1]} selling least?"] = f"Why is {products.index[-1]} selling least?"
    qs["What was my best month?"] = "What was my best month?"
    qs["What should I focus on next?"] = "What should I focus on next?"
    return dict(list(qs.items())[:5])


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

    now = user_now()
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
        if msg.get("date") and msg["date"] != user_now().strftime("%d %b %Y"):
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

            quick = DOC_QUICK_QUESTIONS if is_document() else personal_questions(df)
            st.caption("Or tap a question, or type below:")
            with st.container(horizontal=True, key="quick_qs"):
                for n, (label, q) in enumerate(quick.items()):
                    if st.button(label, key=f"qq_{n}"):
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
                t = conversation_text(history, COMPANY, user_now())
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    copy_button(t, key="copy_all", label="📋 Copy conversation")
                last_answer = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
                with c2:
                    copy_button(last_answer, key="copy_last", label="📋 Copy last answer")
                c3.download_button("⬇️ Save as text", t.encode("utf-8"), "iraaya_conversation.txt",
                                   "text/plain", width="stretch")
                try:
                    pdf, skipped = generate_conversation_pdf(history, COMPANY, user_now())
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

# ---------- Summary ----------
PERIODS = ["Today", "Latest day", "This week", "This month", "Choose dates"]


def show_latest(start, end):
    """Button callback: summary of the latest day/week/month that has sales."""
    st.session_state.sum_period = "Choose dates"
    st.session_state.sum_dates = (start, end)


def period_context(frame: pd.DataFrame, label: str) -> str:
    lines = [f"PERIOD: {label}"]
    if COMPANY:
        lines.append(f"BUSINESS NAME: {COMPANY}")
    lines.append(f"CURRENCY: all revenue figures are in {currency[1]}." if currency
                 else "CURRENCY: not specified. Do not use any currency symbol.")
    for col, word in (("Region", "places/regions"), ("Product", "products")):
        if set(frame[col].unique()) == {ALL}:
            lines.append(f"NOTE: this file has no {word} column. Do not mention {word}.")
    return "\n".join(lines) + "\n" + analyse(frame)["context"]


def summary_actions(text: str, key: str):
    c1, c2, c3 = st.columns(3)
    if c1.button("🔊 Read it to me", key=f"read_{key}", width="stretch"):
        audio = speak(text)
        if audio:
            st.audio(audio, format="audio/mp3", autoplay=True)
    with c2:
        copy_button(text, key=f"copy_{key}", label="📋 Copy")
    c3.link_button("💬 Send on WhatsApp", "https://wa.me/?text=" + quote(text), width="stretch")


if sum_tab.open:
    with sum_tab:
        if is_document():
            glance = st.session_state.doc_glance
            st.subheader(f"📅 Summary of {st.session_state.doc_name}")
            if glance:
                st.markdown(glance["summary"])
                summary_actions(glance["summary"], "doc_summary")
            else:
                st.info("Open 📊 My business first — iRaaya reads the document there.")
        elif FULL_DF is None:
            st.info("👋 Add your sales file first, then come back here for a summary of any day, week or month.")
            st.button("🏠 Go to Home", on_click=go, args=(HOME,))
        else:
            st.subheader("📅 Summary")
            today = user_now().date()
            min_d, max_d = FULL_DF.Date.min().date(), FULL_DF.Date.max().date()
            if st.session_state.get("sum_period") not in PERIODS:
                # Open on a day that has sales: today if it has any, otherwise the latest day
                has_today = (FULL_DF.Date.dt.date == today).any()
                st.session_state.sum_period = "Today" if has_today else "Latest day"
            period = st.segmented_control("Which period?", PERIODS, key="sum_period",
                                          width="stretch") or "Latest day"
            if period == "Today":
                start, end, label = today, today, f"today, {today:%d %B %Y}"
            elif period == "Latest day":
                start, end, label = max_d, max_d, f"{max_d:%A %d %B %Y} (the latest day in your file)"
            elif period == "This week":
                start, end = today - timedelta(days=today.weekday()), today
                label = f"this week, {start:%d %b} – {end:%d %b %Y}"
            elif period == "This month":
                start, end, label = today.replace(day=1), today, f"this month, {today:%B %Y}"
            else:
                saved = st.session_state.get("sum_dates")
                if not (isinstance(saved, (list, tuple)) and len(saved) == 2 and min_d <= saved[0] <= saved[1] <= max_d):
                    st.session_state.sum_dates = (max(min_d, max_d - timedelta(days=29)), max_d)
                picked = st.date_input("From – to", key="sum_dates", min_value=min_d, max_value=max_d)
                start, end = (picked if isinstance(picked, (list, tuple)) and len(picked) == 2
                              else (picked[0], picked[0]) if isinstance(picked, (list, tuple)) else (picked, picked))
                label = (f"{start:%d %B %Y}" if start == end else f"{start:%d %b %Y} – {end:%d %b %Y}")
            if any(choices.values()):
                st.caption("Only the products/places chosen in 🔎 Narrow down are included.")

            period_df = apply_filters(FULL_DF, start, end, choices)
            if period_df.empty:
                st.info(f"No sales found for **{label}**. Your file has sales from "
                        f"**{min_d:%d %b %Y}** to **{max_d:%d %b %Y}**.")
                if period == "This week":
                    s0 = max(min_d, max_d - timedelta(days=max_d.weekday()))
                    what = f"the week of {s0:%d %b %Y} (the last week in my file)"
                elif period == "This month":
                    s0 = max(min_d, max_d.replace(day=1))
                    what = f"{max_d:%B %Y} (the last month in my file)"
                else:
                    s0, what = max_d, f"{max_d:%d %b %Y} (the last day in my file)"
                st.button(f"📌 Show {what}", on_click=show_latest, args=(s0, max_d), type="primary")
            else:
                prev = previous_period(FULL_DF, start, end, choices)
                c = card_numbers(period_df, prev)
                st.markdown(f"#### {label[0].upper() + label[1:]}")
                m = st.columns(4)
                m[0].metric("💰 Sales", money(c["total"]), metric_delta(c["total_change"], "vs the period before"))
                m[1].metric("🧾 Transactions", f"{c['transactions']:,}", metric_delta(c["transactions_change"], "vs the period before"))
                if c["best_product"] not in (None, ALL):
                    m[2].metric("🏆 Best product", c["best_product"], f"{c['best_product_share']:.0f}% of sales",
                                delta_color="off", delta_arrow="off")
                by_region = period_df.groupby("Region").Total_Revenue.sum()
                if len(by_region) > 1:
                    m[3].metric("🌍 Best place", by_region.idxmax(), money(by_region.max()),
                                delta_color="off", delta_arrow="off")
                else:
                    days = period_df.Date.dt.date.nunique()
                    m[3].metric("📆 Average per sales day", money(c["total"] / max(days, 1)),
                                f"{days} day(s) with sales", delta_color="off", delta_arrow="off")
                if period_df.Date.dt.date.nunique() > 1:
                    show_chart(revenue_by_month(period_df, [], SYM, NSTYLE) if (end - start).days > 62
                               else revenue_trend(period_df, SYM, NSTYLE), "sum_chart")
                elif period_df.Product.nunique() > 1:
                    show_chart(top_products(period_df, SYM, NSTYLE), "sum_chart")

                skey = f"{start}_{end}_{selected_language}_{selected_mode}_{sorted((k, tuple(v)) for k, v in choices.items() if v)}"
                written = st.session_state.period_summaries.get(skey)
                if written is None:
                    if st.button("✍️ Write my summary", type="primary"):
                        try:
                            with st.spinner("iRaaya is writing your summary…"):
                                written = summarise_period(period_context(period_df, label), label,
                                                           GROQ_KEY, selected_language, selected_mode)
                            st.session_state.period_summaries = {**st.session_state.period_summaries, skey: written}
                        except Exception as e:
                            show_error(e)
                if written:
                    with st.container(border=True):
                        st.markdown(written)
                        summary_actions(written, "period")

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
            auto = (GROQ_KEY and not st.session_state.insights
                    and st.session_state.get("insights_for") != (st.session_state.data_key, selected_language))
            if auto or st.button("🔄 Refresh insights" if st.session_state.insights else "✨ Generate iRaaya Insights",
                                 type="secondary" if st.session_state.insights else "primary"):
                st.session_state.insights_for = (st.session_state.data_key, selected_language)
                try:
                    with st.spinner("iRaaya is looking at your business…"):
                        st.session_state.insights = generate_insights(data_context(), GROQ_KEY, selected_language)
                    if not st.session_state.insights:
                        st.warning("iRaaya couldn't produce insights this time. Please try again.")
                except Exception as e:
                    show_error(e)
                if auto and st.session_state.insights:
                    st.rerun()      # show them with the Refresh button

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
                show_chart(forecast_chart(forecast_data["historical"], forecast_data["forecast"],
                                          SYM, NSTYLE), "ch_forecast")
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
                      delta_color=health["color"], delta_arrow="off", help=SCORE_HELP)
            st.caption("ⓘ " + SCORE_HELP)
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
                        now=user_now(),
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
        voice_settings()
        st.caption("Everything you choose here is remembered on this device and used next time.")
        if st.button("↺ Reset settings to defaults"):
            for key, value in SETTING_DEFAULTS.items():
                st.session_state[key] = value
            st.rerun()

        st.subheader("🎯 Monthly target")
        st.number_input(f"Monthly sales target{f' ({SYM})' if SYM else ''}", min_value=0.0, step=1000.0,
                        key="target", persist_state="session",
                        help="Shown on the Home screen with how much you still need each day. 0 = no target.")

        st.subheader("📱 iRaaya on your phone")
        with st.expander("Put iRaaya on your home screen, like an app"):
            st.markdown(
                "- **iPhone / iPad (Safari):** open iRaaya, tap **Share** (the square with an arrow) → "
                "**Add to Home Screen** → **Add**.\n"
                "- **Android (Chrome):** open iRaaya, tap **⋮** (top right) → **Add to Home screen** "
                "or **Install app**.\n"
                "- Then open iRaaya from the water-drop icon on your home screen, like any other app.")

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
