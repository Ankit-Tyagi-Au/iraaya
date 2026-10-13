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
- iRaaya Ocean design: day and night look that follows your device, works on computer and phone
  (tab bar on computers, an icon bar at the bottom on phones)
- Home: today's sales vs a usual day, a big "What would you like to know?" voice card,
  things to know (worked out from your data) and a monthly target with progress
- 3 simple ways to start: your sales file, a sample, or any other file
- Upload sales data: CSV or Excel (.xlsx, .xls), or a PDF/Word file with a sales table
- Any other file (PDF, Word, text, any table) becomes a short summary, checked key numbers
  (with page and sentence) and charts of its tables
- Summary of today, this week, this month or chosen dates: cards, chart, a written summary,
  read aloud, copy or send on WhatsApp
- Works with files from anywhere: column names in 13 languages, European (1.234,56),
  Indian (12,34,567) and US number styles, day/month or month/day dates
- Only a date and an amount column are required (Product, Region, Customer type
  and Payment method are used when present)
- Data preview after upload: rows, date range, products, regions, missing values,
  how each column was read
- My business: Overview, Products, Places and All my sales; time buttons (last 7/30/90 days,
  12 months, all time, chosen dates) always compared with the time before; filters on the page;
  8 cards (sales, sales count, average sale, units, best product/place/day, payment);
  charts incl. day of the week, payment methods and customer types; tap a product or place
  to see its own page; search, sort and download every sale
- Settings page: company name, 31 currencies, 4 number formats, monthly target, language,
  answer style and voice
- Ask by voice (stops when you pause) or text, in 13 languages, 3 answer styles
- "Explain this chart" under every chart, with read-aloud; save any chart as a picture
- Example questions that use your own products and places
- Answers from your real data, including individual records ("What happened on 15 April?")
- Voice: free or premium voice, speed, preview, voice cloning with privacy protections
- Chat: timestamps, voice on every answer, copy buttons, save as text or PDF
- Ask questions about any PDF or Word document (with page numbers)
- Insights, 3-month forecast with likely range and trend fit, business health score
- PDF report with company header, logo, charts and currency; WhatsApp summary
- Your work is remembered on your device (refresh, restart and update safe)

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
Sales data: CSV, Excel, or a PDF/Word file containing a table.
Required columns: `Date`, `Product`, `Region`, `Total_Revenue`

Optional columns that give richer answers:
`Units_Sold`, `Unit_Price`, `Customer_Type`, `Payment_Method`, `Month`, `Quarter`

Any other PDF or Word (.docx) file opens as a **document**: ask questions about
it by voice or text. Long documents are sent in parts (the parts most related to
each question). Scanned PDFs (photos of pages) have no readable text and are not
supported yet.

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

Your data, conversation, spoken answers and settings are kept **only in your own
browser on your device** (IndexedDB), so a refresh, a server restart or an app update
doesn't lose them. Nothing is stored on the server. On a shared device, use
**Start fresh** / **Clear all my data** to remove them. (Safari may clear site data
after a few weeks without visits.)


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

## Tests
Run `python tests/test_app_v1.py`, `python tests/test_app_v1b.py` and `python tests/test_summary.py`
(they need GROQ_API_KEY in .env, as some checks ask the AI).
