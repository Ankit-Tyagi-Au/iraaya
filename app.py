"""iRaaya — your business, explained simply, in any language.

Run: streamlit run app.py
"""

import hashlib
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from analyser import (
    load_data,
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
from insights import (
    IRaayaError,
    ask_iraaya,
    generate_insights,
    generate_whatsapp_summary
)
from languages import LANGUAGES
from pdf_report import generate_pdf
from voice import (
    DEFAULT_VOICE_ID,
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
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


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


def show_error(e: Exception):
    st.error(str(e) if isinstance(e, IRaayaError) else f"Something went wrong: {e}")


# ---------- Sidebar ----------
st.sidebar.title("🎯 iRaaya")
st.sidebar.caption(
    "Your Business Voice · by Riverrax"
)
st.sidebar.divider()

uploaded_file = st.sidebar.file_uploader(
    "Upload your business data",
    type=["csv", "xlsx", "xls"],
    help="CSV or Excel with Date, Product, Region and Total_Revenue columns"
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    data_key = hashlib.md5(file_bytes).hexdigest()
    if data_key != st.session_state.data_key:
        try:
            set_data(load_data(uploaded_file), uploaded_file.name, data_key)
        except ValueError as e:
            st.sidebar.error(str(e))
elif st.session_state.data_key is None:
    if st.sidebar.button("✨ Try with sample data", width="stretch"):
        set_data(load_data(SAMPLE_FILE), "Sample data", "sample")
        st.rerun()

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
    index=0
)

selected_mode = st.sidebar.radio(
    "💬 Response style",
    options=[
        "Professional",
        "Simple",
        "Friendly"
    ],
    index=1,
    horizontal=True
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
selected_currency = st.sidebar.selectbox("💱 Currency of your data", list(CURRENCIES))
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


speak_answers = st.sidebar.toggle("🔊 Speak answers aloud", value=True)

use_elevenlabs = st.sidebar.toggle(
    "🎙️ Premium voice",
    value=False,
    disabled=not EL_KEY,
    help=(
        "Uses ElevenLabs for more natural voice output."
        if EL_KEY else
        "Add ELEVENLABS_API_KEY to enable premium voice."
    )
)



@st.cache_data(ttl=3600, show_spinner=False)
def cached_voices(api_key: str) -> dict:
    return list_voices(api_key)


@st.cache_data(ttl=600, show_spinner=False)
def cached_plan(api_key: str) -> dict:
    return get_plan(api_key)


premium_voice_id = DEFAULT_VOICE_ID
if use_elevenlabs and EL_KEY:
    voices = cached_voices(EL_KEY)
    if st.session_state.cloned_voice_id:
        voices = {f"{st.session_state.cloned_voice_name} (cloned)": st.session_state.cloned_voice_id, **voices}
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
                with st.spinner("Cloning voice..."):
                    voice_id = clone_voice(
                        EL_KEY,
                        voice_name,
                        audio_sample.getvalue(),
                        audio_sample.name
                    )
                if voice_id:
                    st.session_state.cloned_voice_id = voice_id
                    st.session_state.cloned_voice_name = voice_name
                    cached_voices.clear()
                    st.success(
                        f"Voice '{voice_name}' cloned! Turn on Premium voice to use it."
                    )
                else:
                    st.error(
                        "Clone failed. Please try a clearer recording, "
                        "or check your ElevenLabs plan."
                    )
    if st.session_state.cloned_voice_id:
        st.caption(f"Using cloned voice: {st.session_state.cloned_voice_name}")

st.sidebar.divider()
st.sidebar.caption(
    "🔒 To answer questions, a summary of your data is sent to Groq (AI). "
    "Spoken answers use Google TTS or ElevenLabs. Nothing is stored by iRaaya."
)

if not GROQ_KEY:
    st.sidebar.error("GROQ_API_KEY is missing — questions and insights won't work.")

# ---------- Main area ----------
st.title("🎯 iRaaya")
st.caption(
    "Your business, explained simply — "
    "in any language"
)

tab1, tab2, tab3 = st.tabs([
    "📊 Dashboard",
    "💬 Ask iRaaya",
    "🔍 Insights"
])

# ---------- Tab 1: Dashboard ----------
with tab1:
    if st.session_state.df is None:
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


def answer_question(question: str):
    try:
        with st.spinner("iRaaya is thinking..."):
            answer = ask_iraaya(
                question=question,
                data_context=data_context(),
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
    if speak_answers:
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
    st.session_state.last_audio = {"bytes": audio, "fresh": True} if audio else None


with tab2:
    if st.session_state.df is None:
        st.info(
            "Upload data first "
            "to ask iRaaya questions!"
        )
    else:
        st.subheader(
            f"Ask iRaaya in "
            f"{selected_language}"
        )
        st.caption(
            "Type a question, or tap the 🎤 mic in the box below to speak. "
            "Voice works in Chrome, Edge and Safari."
        )

        st.caption("Quick questions:")
        cols = st.columns(len(QUICK_QUESTIONS))
        pending_question = None
        for col, (label, q) in zip(cols, QUICK_QUESTIONS.items()):
            if col.button(label, width="stretch"):
                pending_question = q

        submission = st.chat_input(
            "Ask about your business...",
            accept_audio=True,
            submit_mode="disable",
            key="ask_input"
        )

        if submission:
            text = (submission.text or "").strip()
            if submission.audio is not None:
                with st.spinner("Listening..."):
                    heard = transcribe_audio_file(
                        submission.audio.getvalue(),
                        GROQ_KEY,
                        language=LANGUAGES[selected_language]["gtts_code"].split("-")[0]
                    ) if GROQ_KEY else ""
                if heard:
                    text = f"{text} {heard}".strip()
                elif not text:
                    st.warning("Sorry, I couldn't hear that. Please try again or type your question.")
            if text:
                pending_question = text

        if pending_question:
            answer_question(pending_question)

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
                    autoplay=last["fresh"]
                )
                # Only autoplay once, not on every rerun
                last["fresh"] = False

            if st.button("Clear conversation"):
                st.session_state.chat_history = []
                st.session_state.last_audio = None
                st.rerun()

# ---------- Tab 3: Insights ----------
with tab3:
    if st.session_state.df is None:
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

# ---------- Footer ----------
st.divider()
st.caption(
    "🎯 Powered by iRaaya · "
    "Built by Riverrax · "
    "riverrax.com"
)
