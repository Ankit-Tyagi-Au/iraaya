# iRaaya — Your Business Voice

AI powered business intelligence
assistant that explains your business
data in any language, in any voice.

Built by Riverrax
Brisbane, Australia
riverrax.com
hello@riverrax.com

Named after Iraaya —
because every business deserves
to be understood clearly,
in any language.

## Features
- Upload CSV or Excel business data
- Ask questions by voice or text
- Get answers in 13 languages
- Voice cloning — speak in any voice
- Auto business insights
- Revenue forecasting with a likely range
- Unusual-month detection
- Business health score
- PDF report export
- WhatsApp summary sharing

## Setup
1. Clone this repo
2. Create a virtual environment:
   `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`
5. Add your API keys to `.env`
6. `streamlit run app.py`

No data yet? Click **Try with sample data** in the sidebar.

## Your data file
Required columns: `Date`, `Product`, `Region`, `Total_Revenue`

Optional columns that give richer answers:
`Units_Sold`, `Unit_Price`, `Customer_Type`, `Payment_Method`, `Month`, `Quarter`

`sample_data.csv` is made by `generate_sample_data.py` (fixed seed, same output every run).

## API keys needed
| Key | Where | Cost |
|---|---|---|
| `GROQ_API_KEY` | console.groq.com | Free tier |
| `ELEVENLABS_API_KEY` | elevenlabs.io | Optional. Free tier is non-commercial; voice cloning needs Starter plan or above |

`GROQ_MODEL` (optional) picks the chat model. Default: `llama-3.3-70b-versatile`.
If your Groq account can't use it, set `GROQ_MODEL=openai/gpt-oss-120b`.

Without ElevenLabs, iRaaya speaks with free Google Text-to-Speech (gTTS).

## Privacy
To answer questions, a summary of the uploaded data is sent to Groq.
Spoken answers are sent to Google TTS or ElevenLabs.

So a page refresh doesn't lose your work, iRaaya keeps your data, conversation
and settings **in server memory for up to 24 hours**, under a random private
code in your page address. It is **never saved to disk**, and it disappears when
the app restarts. Anyone with your full link (including the code) could see it,
so share only `iraaya.streamlit.app`. Use **Start fresh** to forget it immediately.

### Your cloned voice stays private
- A cloned voice is only used to speak **your own** answers, in your own session.
- It is **never shown to, or shared with, other iRaaya users.** Other users only ever see the standard voices.
- Your recording is sent to our voice partner ElevenLabs only to create the voice. iRaaya does not keep a copy.
- You can **delete your voice at any time** with the "Delete my voice" button.
- If you don't, iRaaya **removes it automatically after 7 days.**

## Deploy to Streamlit Cloud
1. Push to GitHub (`.env` and `.streamlit/secrets.toml` are git-ignored)
2. share.streamlit.io → New app → repo `iraaya`, branch `main`, file `app.py`
3. App settings → Secrets → paste:
   ```toml
   GROQ_API_KEY = "your_key"
   ELEVENLABS_API_KEY = "your_key"
   ```
