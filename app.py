"""iRaaya — your business, explained simply, in any language.

Run: streamlit run app.py
"""

import difflib
import hashlib
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from analyser import (
    clean_dataframe,
    find_relevant_rows,
    load_data,
    vocabulary_hint,
    validate_data,
    get_summary,
    get_data_context,
    detect_anomalies,
    calculate_health_score
)
from charts import (
    revenue_by_month,
    top_products,
    revenue_trend,
    regional_performance,
    product_comparison
)
from forecaster import (
    forecast_revenue,
    forecast_chart
)
from documents import (
    DOCUMENT_TYPES,
    PAGE_SOURCES,
    document_context,
    page_overview,
    read_document,
)
from insights import (
    IRaayaError,
    ask_document,
    ask_iraaya,
    generate_insights,
    generate_whatsapp_summary
)
from languages import LANGUAGES
from pdf_report import generate_pdf
from recorder import voice_recorder
from voice import (
    DEFAULT_VOICE_ID,
    VoiceCloneError,
    cleanup_old_clones,
    delete_voice,
    get_plan,
    list_voices,
    speak_gtts,
    speak_elevenlabs,
    clone_voice,
    transcribe_audio_file
)

APP_DIR = Path(__file__).resolve().parent
# Explicit path: Streamlit runs the script in a way that stops
# load_dotenv() from finding .env on its own.
# override=True: a blank GROQ_API_KEY inherited from the shell must not
# hide the real key in .env (on Streamlit Cloud there is no .env file).
load_dotenv(APP_DIR / ".env", override=True)

SAMPLE_FILE = APP_DIR / "sample_data.csv"


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
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Session state ----------
DEFAULTS = {
    "df": None,
    "summary": None,
    "context": None,
    "health": None,
    "anomalies": [],
    "data_key": None,
    "data_name": None,
    "warnings": [],
    "chat_history": [],
    "last_audio": None,
    "cloned_voice_id": None,
    "cloned_voice_name": None,
    "insights": [],
    "whatsapp": None,
    "voice_q_n": 0,
    # PDF / Word documents without a sales table
    "doc_text": None,
    "doc_name": None,
    "doc_pages": None,
    "doc_page_source": None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------- Keep work across a page refresh ----------
# A refresh starts a new Streamlit session. To bring the user's work back,
# it is kept in server memory (never on disk) under a random private code
# in the page address (?s=...), for up to SESSION_TTL_HOURS.
SESSION_TTL_HOURS = 24
MAX_STORED_SESSIONS = 200
SAVED_KEYS = [
    "df", "summary", "context", "health", "anomalies", "data_key",
    "data_name", "warnings", "chat_history", "cloned_voice_id",
    "cloned_voice_name", "insights", "whatsapp", "main_tab",
    "doc_text", "doc_name", "doc_pages", "doc_page_source",
    # sidebar settings (widget keys)
    "lang", "style", "currency", "speak", "premium",
]


@st.cache_resource
def session_store() -> dict:
    """Shared in-memory store: {private code: saved work}. Lost on restart."""
    return {}


def session_code() -> str:
    code = st.query_params.get("s", "")
    if not re.fullmatch(r"[0-9a-f]{32}", code):
        code = uuid.uuid4().hex
        st.query_params["s"] = code
    return code


def restore_session():
    saved = session_store().get(SESSION_CODE)
    if saved and time.time() - saved["saved_at"] < SESSION_TTL_HOURS * 3600:
        for key in SAVED_KEYS:
            if key in saved and saved[key] is not None:
                st.session_state[key] = saved[key]


def save_session():
    store = session_store()
    now = time.time()
    store[SESSION_CODE] = {
        **{key: st.session_state.get(key) for key in SAVED_KEYS},
        "saved_at": now,
    }
    # Drop expired entries, and the oldest ones if there are too many
    for code in [c for c, v in store.items() if now - v["saved_at"] > SESSION_TTL_HOURS * 3600]:
        store.pop(code, None)
    for code in sorted(store, key=lambda c: store[c]["saved_at"])[:-MAX_STORED_SESSIONS]:
        store.pop(code, None)


def forget_session():
    """Forget everything now; settings are reset at the top of the next run
    (widgets can't be changed after they are drawn)."""
    session_store().pop(SESSION_CODE, None)
    st.session_state.forget_pending = True


SESSION_CODE = session_code()
if not st.session_state.get("restored"):
    st.session_state.restored = True
    restore_session()

# Sidebar setting defaults live here (not in the widgets), so a restored
# value and a default never compete
SETTING_DEFAULTS = {
    "lang": "English",
    "style": "Simple",
    "currency": "Not specified",
    "speak": "Match my question",
    "premium": False,
}
if st.session_state.pop("forget_pending", False):
    for key, value in {**DEFAULTS, **SETTING_DEFAULTS}.items():
        st.session_state[key] = value
    st.session_state.pop("main_tab", None)
for key, value in SETTING_DEFAULTS.items():
    st.session_state.setdefault(key, value)


def set_data(df, name: str, data_key: str):
    """Analyse a newly loaded file once and keep the results."""
    validation = validate_data(df)
    if not validation["is_valid"]:
        missing = validation["missing_columns"]
        if missing:
            st.sidebar.error(
                f"Missing columns: {', '.join(missing)}. "
                "Your file needs Date, Product, Region and Total_Revenue."
            )
        else:
            st.sidebar.error("No usable rows found in this file.")
        return

    st.session_state.df = df
    st.session_state.summary = get_summary(df)
    st.session_state.context = get_data_context(df)
    st.session_state.health = calculate_health_score(df)
    st.session_state.anomalies = detect_anomalies(df)
    st.session_state.data_key = data_key
    st.session_state.data_name = name
    st.session_state.warnings = validation["warnings"]
    # New data: old answers and insights no longer apply
    st.session_state.chat_history = []
    st.session_state.last_audio = None
    st.session_state.insights = []
    st.session_state.whatsapp = None
    st.session_state.doc_text = None
    st.session_state.doc_name = None
    st.session_state.doc_pages = None
    st.session_state.doc_page_source = None


def set_document(text: str, name: str, pages, data_key: str, page_source=None):
    """Keep a PDF/Word document (no sales table) to answer questions about."""
    for key in ("df", "summary", "context", "health"):
        st.session_state[key] = None
    st.session_state.anomalies = []
    st.session_state.warnings = []
    st.session_state.doc_text = text
    st.session_state.doc_name = name
    st.session_state.doc_pages = pages
    st.session_state.doc_page_source = page_source
    st.session_state.data_key = data_key
    st.session_state.data_name = name
    st.session_state.chat_history = []
    st.session_state.last_audio = None
    st.session_state.insights = []
    st.session_state.whatsapp = None


def is_document() -> bool:
    return st.session_state.df is None and bool(st.session_state.doc_text)


def show_error(e: Exception):
    st.error(str(e) if isinstance(e, IRaayaError) else f"Something went wrong: {e}")


# ---------- Sidebar ----------
st.sidebar.title("🎯 iRaaya")
st.sidebar.caption(
    "Your Business Voice · by Riverrax"
)
st.sidebar.divider()

uploaded_file = st.sidebar.file_uploader(
    "Upload your business data or a document",
    type=["csv", "xlsx", "xls", "pdf", "docx"],
    help=(
        "Sales data: CSV, Excel, or a PDF/Word file with a table that has "
        "Date, Product, Region and Total_Revenue columns. "
        "Any other PDF or Word document: ask questions about it."
    )
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    data_key = hashlib.md5(file_bytes).hexdigest()
    if data_key != st.session_state.data_key:
        try:
            if os.path.splitext(uploaded_file.name)[1].lower() in DOCUMENT_TYPES:
                with st.spinner("Reading your document..."):
                    doc = read_document(uploaded_file)
                if doc["kind"] == "table":
                    set_data(clean_dataframe(doc["df"]), uploaded_file.name, data_key)
                else:
                    set_document(
                        doc["text"], uploaded_file.name, doc["pages"],
                        data_key, doc.get("page_source"),
                    )
            else:
                set_data(load_data(uploaded_file), uploaded_file.name, data_key)
        except ValueError as e:
            st.sidebar.error(str(e))
elif st.session_state.data_key is None:
    if st.sidebar.button("✨ Try with sample data", width="stretch"):
        set_data(load_data(SAMPLE_FILE), "Sample data", "sample")
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

if st.session_state.df is not None:
    health = st.session_state.health
    st.sidebar.success(
        f"Loaded: {st.session_state.data_name} "
        f"({len(st.session_state.df):,} rows)"
    )
    for w in st.session_state.warnings:
        st.sidebar.warning(w)
    st.sidebar.metric(
        "iRaaya Score",
        f"{health['score']}/100",
        health["label"],
        delta_color=health["color"],
        delta_arrow="off",
    )

st.sidebar.divider()

selected_language = st.sidebar.selectbox(
    "🌍 Language",
    options=list(LANGUAGES.keys()),
    format_func=lambda name: (
        name if LANGUAGES[name]["display"] == name
        else f"{name} · {LANGUAGES[name]['display']}"
    ),
    key="lang",
)

selected_mode = st.sidebar.radio(
    "💬 Response style",
    options=[
        "Professional",
        "Simple",
        "Friendly"
    ],
    horizontal=True,
    key="style",
)

CURRENCIES = {
    "Not specified": None,
    "₹ Indian Rupee (INR)": ("₹", "Indian Rupees (INR)"),
    "A$ Australian Dollar (AUD)": ("A$", "Australian Dollars (AUD)"),
    "$ US Dollar (USD)": ("$", "US Dollars (USD)"),
    "€ Euro (EUR)": ("€", "Euros (EUR)"),
    "£ British Pound (GBP)": ("£", "British Pounds (GBP)"),
    "AED UAE Dirham": ("AED ", "UAE Dirhams (AED)"),
}
selected_currency = st.sidebar.selectbox(
    "💱 Currency of your data", list(CURRENCIES),
    key="currency",
)
currency = CURRENCIES[selected_currency]
CUR = currency[0] if currency else ""


def data_context() -> str:
    """The data summary sent to the AI, plus the chosen currency."""
    line = (
        f"CURRENCY: all revenue figures are in {currency[1]}."
        if currency else
        "CURRENCY: not specified. Do not use any currency symbol."
    )
    return f"{line}\n{st.session_state.context}"


SPEAK_MODES = {
    "Match my question": "Spoken answer when you ask by voice, text when you type",
    "Always": "Every answer is spoken",
    "Never": "Text answers only",
}
speak_mode = st.sidebar.radio(
    "🔊 Spoken answers",
    list(SPEAK_MODES),
    captions=list(SPEAK_MODES.values()),
    key="speak",
)

use_elevenlabs = st.sidebar.toggle(
    "🎙️ Premium voice",
    disabled=not EL_KEY,
    key="premium",
    help=(
        "Uses ElevenLabs for more natural voice output."
        if EL_KEY else
        "Add ELEVENLABS_API_KEY to enable premium voice."
    )
)


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


premium_voice_id = DEFAULT_VOICE_ID
if use_elevenlabs and EL_KEY:
    voices = cached_voices(EL_KEY)
    if st.session_state.cloned_voice_id:
        # Only the person who made the clone sees it (this session only)
        voices = {f"{st.session_state.cloned_voice_name} (your voice)": st.session_state.cloned_voice_id, **voices}
    if voices:
        names = list(voices)
        default_name = next(
            (n for n, v in voices.items() if v == (st.session_state.cloned_voice_id or DEFAULT_VOICE_ID)),
            names[0]
        )
        chosen = st.sidebar.selectbox("🗣️ Voice", names, index=names.index(default_name))
        premium_voice_id = voices[chosen]

with st.sidebar.expander(
    "🔬 Clone a voice"
):
    st.caption(
        "Record someone's voice and "
        "iRaaya will speak in that voice!"
    )
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
        voice_name = st.text_input(
            "Voice name",
            placeholder="e.g. Manisha"
        )
        audio_sample = st.file_uploader(
            "Upload audio sample (1-2 minutes of clear speech)",
            type=["mp3", "wav", "m4a"],
            key="voice_clone_upload"
        )
        consent = st.checkbox(
            "I have this person's permission to clone their voice"
        )
        if st.button(
            "Clone this voice",
            key="clone_btn"
        ):
            if not (audio_sample and voice_name):
                st.warning(
                    "Please enter a name "
                    "and upload audio."
                )
            elif not consent:
                st.warning("Please confirm you have permission first.")
            else:
                try:
                    with st.spinner("Cloning voice..."):
                        voice_id = clone_voice(
                            EL_KEY,
                            voice_name,
                            audio_sample.getvalue(),
                            audio_sample.name
                        )
                    st.session_state.cloned_voice_id = voice_id
                    st.session_state.cloned_voice_name = voice_name
                    st.success(
                        f"Voice '{voice_name}' cloned! Turn on Premium voice to use it."
                    )
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
        st.caption(
            "If you don't delete it, iRaaya removes it automatically "
            "after 7 days."
        )

st.sidebar.divider()
st.sidebar.caption(
    "🔒 To answer questions, a summary of your data (or your document's "
    "text) is sent to Groq (AI). "
    "Spoken answers use Google TTS or ElevenLabs. So a page refresh doesn't "
    "lose your work, iRaaya keeps it in memory for up to 24 hours under a "
    "private code in this page's address — it is never saved to disk, and "
    "anyone with your full link could see it, so share only "
    "iraaya.streamlit.app. Cloned voices are private to the person who made them."
)
if st.session_state.df is not None or is_document() or st.session_state.chat_history:
    if st.sidebar.button("🧹 Start fresh (forget my data now)", width="stretch"):
        forget_session()
        st.rerun()

if not GROQ_KEY:
    st.sidebar.error("GROQ_API_KEY is missing — questions and insights won't work.")

# ---------- Main area ----------
st.title("🎯 iRaaya")
st.caption(
    "Your business, explained simply — "
    "in any language"
)

TAB_LABELS = ["📊 Dashboard", "💬 Ask iRaaya", "🔍 Insights"]
if st.session_state.get("main_tab") not in TAB_LABELS:
    st.session_state.pop("main_tab", None)
# key + on_change: the open tab is kept in session state (and restored
# after a refresh by restore_session)
tab1, tab2, tab3 = st.tabs(TAB_LABELS, key="main_tab", on_change="rerun")

# ---------- Tab 1: Dashboard ----------
with tab1:
    if is_document():
        st.info(
            f"📄 **{st.session_state.doc_name}** is a document, not sales "
            "data, so there are no charts for it. Go to **💬 Ask iRaaya** "
            "and ask anything about it."
        )
    elif st.session_state.df is None:
        st.info(
            "👈 Upload your business data in the sidebar, "
            "or click **Try with sample data** to explore."
        )
        with open(SAMPLE_FILE, "rb") as f:
            st.download_button(
                "Download sample data (CSV)",
                f.read(),
                "sample_data.csv",
                "text/csv"
            )
        st.caption(
            "Your file needs these columns: Date, Product, Region, "
            "Total_Revenue. Extra columns like Customer_Type and "
            "Payment_Method give richer answers."
        )
    else:
        df = st.session_state.df
        s = st.session_state.summary
        anomalies = st.session_state.anomalies

        best_month_revenue = s["monthly_revenue"][s["best_month"]]
        best_product_share = (
            s["top_products"][s["best_product"]] / s["total_revenue"] * 100
            if s["total_revenue"] else 0
        )

        # Wider column for the product name so it isn't cut off
        col1, col2, col3, col4 = st.columns([1, 1, 1.5, 1])
        col1.metric(
            "Total Revenue",
            f"{CUR}{s['total_revenue']:,.0f}",
            border=True
        )
        col2.metric(
            "Best Month",
            pd.Period(s["best_month"]).strftime("%b %Y"),
            f"{best_month_revenue:,.0f}",
            delta_color="off",
            delta_arrow="off",
            border=True
        )
        col3.metric(
            "Best Product",
            s["best_product"],
            f"{best_product_share:.0f}% of revenue",
            delta_color="off",
            delta_arrow="off",
            help=s["best_product"],
            border=True
        )
        col4.metric(
            "Transactions",
            f"{s['total_transactions']:,}",
            border=True
        )
        st.caption(f"Data period: {s['date_range']}")

        st.plotly_chart(
            revenue_by_month(df, [a["month"] for a in anomalies]),
            width="stretch"
        )

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                top_products(df),
                width="stretch"
            )
        with col2:
            st.plotly_chart(
                regional_performance(df),
                width="stretch"
            )

        st.plotly_chart(product_comparison(df), width="stretch")

        if anomalies:
            st.subheader(
                "⚠️ Unusual months detected"
            )
            for a in anomalies:
                if a["type"] == "low":
                    st.warning(
                        f"📉 **{a['month']}**: revenue was "
                        f"{abs(a['difference_pct'])}% below what the "
                        f"trend expected ({a['revenue']:,.0f} vs "
                        f"{a['expected']:,.0f})"
                    )
                else:
                    st.success(
                        f"📈 **{a['month']}**: revenue was "
                        f"{a['difference_pct']}% above what the "
                        f"trend expected ({a['revenue']:,.0f} vs "
                        f"{a['expected']:,.0f})"
                    )

        with st.expander("Revenue trend by sales date"):
            st.plotly_chart(revenue_trend(df), width="stretch")

# ---------- Tab 2: Ask iRaaya ----------
# Short button label -> full question sent to iRaaya
QUICK_QUESTIONS = {
    "Best month?": "What was my best month?",
    "Top product?": "Which product sells most?",
    "Growth trend?": "What is my growth trend?",
    "Unusual months?": "Were there any unusual months?",
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


def answer_question(question: str, asked_by_voice: bool = False):
    try:
        with st.spinner("iRaaya is thinking..."):
            if is_document():
                answer = ask_document(
                    question=question,
                    document_text=document_context(st.session_state.doc_text, question),
                    document_name=st.session_state.doc_name,
                    language=selected_language,
                    mode=selected_mode,
                    api_key=GROQ_KEY,
                    chat_history=st.session_state.chat_history
                )
            else:
                rows = find_relevant_rows(st.session_state.df, question)
                answer = ask_iraaya(
                    question=question,
                    data_context=data_context() + (f"\n{rows}\n" if rows else ""),
                    language=selected_language,
                    mode=selected_mode,
                    api_key=GROQ_KEY,
                    chat_history=st.session_state.chat_history
                )
    except Exception as e:
        show_error(e)
        return

    st.session_state.chat_history += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]

    audio = None
    speak = speak_mode == "Always" or (
        speak_mode == "Match my question" and asked_by_voice
    )
    if speak:
        with st.spinner("Preparing voice..."):
            if use_elevenlabs and EL_KEY:
                audio = speak_elevenlabs(
                    answer,
                    EL_KEY,
                    premium_voice_id,
                    LANGUAGES[selected_language]["el_code"]
                )
                if audio is None:
                    st.toast("Premium voice failed — using standard voice.")
            if audio is None:
                audio = speak_gtts(
                    answer,
                    LANGUAGES[selected_language]["gtts_code"]
                )
    st.session_state.last_audio = {
        "bytes": audio,
        "fresh": True,
        # Voice questions: played by the recorder's tap-unlocked channel
        "via_recorder": asked_by_voice,
        "id": uuid.uuid4().hex,
    } if audio else None


with tab2:
    if st.session_state.df is None and not is_document():
        st.info(
            "Upload data or a document first "
            "to ask iRaaya questions!"
        )
    else:
        st.subheader(
            f"Ask iRaaya in "
            f"{selected_language}"
        )
        if is_document():
            with st.expander("📄 How iRaaya sees your pages"):
                st.caption(PAGE_SOURCES.get(st.session_state.doc_page_source, PAGE_SOURCES[None]))
                for n, start in page_overview(st.session_state.doc_text):
                    st.markdown(f"**Page {n}** — {start}")

        # Ask by voice: stops by itself when you pause, then answers
        last = st.session_state.last_audio
        spoken = voice_recorder(
            key="voice_recorder",
            turn=st.session_state.voice_q_n,
            play=(
                {"id": last["id"], "audio": last["bytes"]}
                if last and last["fresh"] and last.get("via_recorder") else None
            ),
        )
        if st.session_state.pop("voice_warning", None):
            st.warning("I didn't catch a question. Tap the mic and try again, or type it below.")
        # Backup: Streamlit's basic recorder (tap stop yourself).
        # A new key after each question resets it.
        with st.expander("Mic not working? Use the basic recorder"):
            basic = st.audio_input(
                "Tap the mic, speak, then tap stop",
                key=f"voice_q_{st.session_state.voice_q_n}",
            )
        recording = spoken or ((basic.getvalue(), "question.wav") if basic else None)

        st.caption("Or tap a quick question, or type below:")
        quick = DOC_QUICK_QUESTIONS if is_document() else QUICK_QUESTIONS
        cols = st.columns(len(quick))
        pending_question = None
        asked_by_voice = False
        for col, (label, q) in zip(cols, quick.items()):
            if col.button(label, width="stretch"):
                pending_question = q

        typed = st.chat_input(
            "Type your question...",
            submit_mode="disable",
            key="ask_input"
        )
        if typed and typed.strip():
            pending_question = typed.strip()

        if recording is not None:
            st.session_state.voice_q_n += 1
            with st.spinner("Listening..."):
                audio_bytes, audio_name = recording
                heard = transcribe_audio_file(
                    audio_bytes,
                    GROQ_KEY,
                    language=LANGUAGES[selected_language]["gtts_code"].split("-")[0],
                    filename=audio_name,
                    vocabulary=(
                        None if is_document()
                        else vocabulary_hint(st.session_state.df)
                    ),
                ) if GROQ_KEY else ""
            if heard and is_own_echo(heard):
                heard = ""   # the mic picked up iRaaya's own spoken answer
            if heard:
                pending_question = heard
                asked_by_voice = True
            else:
                st.session_state.voice_warning = True

        if pending_question:
            answer_question(pending_question, asked_by_voice)
        if recording is not None:
            # Redraw so both recorders reset and are ready for the next question
            st.rerun()

        if st.session_state.chat_history:
            for msg in st.session_state.chat_history[-10:]:
                st.chat_message(
                    msg["role"],
                    avatar="🎯" if msg["role"] == "assistant" else None
                ).write(msg["content"])

            # Voice for the latest answer, right under it
            last = st.session_state.last_audio
            if last:
                st.audio(
                    last["bytes"],
                    format="audio/mp3",
                    # Voice answers already play through the recorder
                    autoplay=last["fresh"] and not last.get("via_recorder")
                )
                # Only autoplay once, not on every rerun
                last["fresh"] = False
                st.caption(
                    "Didn't hear it? Tap ▶. Safari, iPhone and iPad block sound "
                    "that starts by itself. On a Mac you can allow it: Safari → "
                    "Settings for this website → Auto-Play → Allow All Auto-Play."
                )

            if st.button("Clear conversation"):
                st.session_state.chat_history = []
                st.session_state.last_audio = None
                st.rerun()

# ---------- Tab 3: Insights ----------
with tab3:
    if is_document():
        st.info(
            "Insights, forecasts and the health score work with sales data. "
            "For your document, ask questions in **💬 Ask iRaaya** — try "
            "\"Summary?\" or \"Key points?\"."
        )
    elif st.session_state.df is None:
        st.info(
            "Upload data first!"
        )
    else:
        df = st.session_state.df

        if st.button(
            "✨ Generate iRaaya Insights",
            type="primary"
        ):
            try:
                with st.spinner("Analysing your business..."):
                    st.session_state.insights = generate_insights(
                        data_context(),
                        GROQ_KEY,
                        selected_language
                    )
                if not st.session_state.insights:
                    st.warning("iRaaya couldn't produce insights this time. Please try again.")
            except Exception as e:
                show_error(e)

        if st.session_state.insights:
            st.subheader(
                "iRaaya Insights"
            )
            for insight in (
                st.session_state.insights
            ):
                body = f"**{insight['title']}**\n\n{insight['detail']}"
                t = insight["type"]
                if t == "positive":
                    st.success(body, icon="✅")
                elif t == "warning":
                    st.warning(body, icon="⚠️")
                else:
                    st.info(body, icon="💡")

        st.divider()
        st.subheader("📈 Revenue Forecast")

        forecast_data = forecast_revenue(df)

        if forecast_data is None:
            st.info("At least 3 months of data are needed for a forecast.")
        else:
            st.plotly_chart(
                forecast_chart(
                    forecast_data["historical"],
                    forecast_data["forecast"]
                ),
                width="stretch"
            )

            cols = st.columns(3)
            for col, f in zip(cols, forecast_data["forecast"]):
                col.metric(
                    f["date"],
                    f"{f['predicted_revenue']:,.0f}",
                    f"Likely {f['low']:,.0f} – {f['high']:,.0f}",
                    delta_color="off",
                    delta_arrow="off",
                    border=True
                )
            note = (
                f"Trend: **{forecast_data['trend']}** "
                f"({forecast_data['monthly_change_pct']:+}% per month). "
                f"Trend fit: {forecast_data['fit_pct']}%. "
                "The forecast follows the overall trend and does not include seasonal peaks."
            )
            if forecast_data["excluded_months"]:
                note += (
                    " Unusual months left out: "
                    f"{', '.join(forecast_data['excluded_months'])}."
                )
            st.caption(note)

        health = st.session_state.health
        st.divider()
        st.subheader(
            "💊 Business Health Score"
        )
        st.metric(
            "iRaaya Score",
            f"{health['score']}/100",
            health["label"],
            delta_color=health["color"],
            delta_arrow="off"
        )
        for factor in health["factors"]:
            st.write(f"• {factor}")

        st.divider()
        st.subheader("📤 Export")

        col1, col2 = st.columns(2)

        with col1:
            company_name = st.text_input("Company name for the report", "My Business")
            pdf_bytes = generate_pdf(
                st.session_state.summary,
                st.session_state.insights,
                forecast_data,
                company_name,
                health,
                st.session_state.anomalies
            )
            st.download_button(
                "📄 Download PDF Report",
                pdf_bytes,
                "iraaya_report.pdf",
                "application/pdf"
            )
            if not st.session_state.insights:
                st.caption("Tip: generate insights first to include them in the PDF.")

        with col2:
            if st.button(
                "💬 Create WhatsApp Summary"
            ):
                try:
                    with st.spinner("Creating summary..."):
                        st.session_state.whatsapp = generate_whatsapp_summary(
                            data_context(),
                            GROQ_KEY,
                            selected_language
                        )
                except Exception as e:
                    show_error(e)
            if st.session_state.whatsapp:
                st.code(st.session_state.whatsapp, language=None, wrap_lines=True)
                st.caption("Use the copy icon at the top right of the box.")
                st.link_button(
                    "Open in WhatsApp",
                    "https://wa.me/?text=" + quote(st.session_state.whatsapp)
                )

save_session()

# ---------- Footer ----------
st.divider()
st.caption(
    "🎯 Powered by iRaaya · "
    "Built by Riverrax · "
    "riverrax.com"
)
