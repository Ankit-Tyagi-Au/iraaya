from streamlit.testing.v1 import AppTest
import datetime as dt
APP = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "app.py")
results = []
def ok(c, m): results.append(bool(c)); print(("PASS  " if c else "FAIL  ") + m)
def errs(a): return [e.value[:200] for e in a.exception]
def card(a, prefix): return next((m for m in a.metric if m.label.startswith(prefix)), None)
TAB = {"t": ":material/bar_chart: My business"}
def go(a, tab): TAB["t"] = tab; a.session_state["main_tab"] = tab; a.run()
def act(a, element): element; a.session_state["main_tab"] = TAB["t"]; a.run()

a = AppTest.from_file(APP, default_timeout=240).run()
act(a, [b for b in a.button if "sample data" in b.label.lower()][0].click())

# Settings: company, currency, number style — then switch tabs and back
go(a, ":material/settings: Settings")
act(a, a.text_input(key="company").input("Sharma Cleaning Co."))
act(a, a.selectbox(key="currency").select("₹ Indian Rupee (INR)"))
act(a, a.selectbox(key="number_style").select("12,34,567.89 (Indian lakh/crore)"))
ok(not a.exception, f"settings change {errs(a)}")
go(a, ":material/bar_chart: My business")
ok(card(a, "💰").value == "₹1,21,36,222", f"currency + Indian format on card: {card(a,'💰').value}")
ok(any("Sharma Cleaning Co." in s.value for s in a.subheader), "company name on dashboard")
go(a, ":material/settings: Settings")
ok(a.text_input(key="company").value == "Sharma Cleaning Co." and a.selectbox(key="currency").value.startswith("₹"),
   "settings kept after switching tabs")
go(a, ":material/bar_chart: My business")

# Filters: Q1 2025, North India
act(a, a.date_input(key="f_dates").set_value((dt.date(2025, 1, 1), dt.date(2025, 3, 31))))
act(a, a.multiselect(key="f_Region").select("North India"))
ok(not a.exception, f"filters apply {errs(a)}")
c = card(a, "💰")
ok(c.value == "₹7,73,842" and "+9.5%" in (c.delta or ""), f"filtered total + change vs Q4: {c.value} {c.delta}")
ok(any("North India" in m.value for m in a.markdown), "active filter tags shown")
mom = card(a, "🔁"); ok(mom and "Mar 2025 vs Feb 2025" in (mom.delta or ""), f"MoM card: {mom.value} {mom.delta}")

# Ask with filters: typed question
go(a, ":material/mic: Ask iRaaya")
act(a, a.chat_input(key="ask_input").set_value("What was my total revenue?"))
ok(not a.exception, f"typed question {errs(a)}")
hist = a.session_state["chat_history"]
ok(len(hist) == 2 and hist[1].get("time") and hist[1].get("audio") is None, "answer with timestamp, text only (typed)")
print("      answer:", hist[1]["content"][:160] if hist else None)
ok("7,73,842" in hist[1]["content"] or "773,842" in hist[1]["content"] or "773842" in hist[1]["content"].replace(",", ""),
   "answer uses the filtered total")

# Always speak + speed Slow
act(a, a.radio(key="speak").set_value("Always"))
act(a, a.select_slider(key="speed").set_value("Slow"))
act(a, [b for b in a.button if b.label == "What was my best month?"][0].click())
h = a.session_state["chat_history"]
ok(len(h) == 4 and h[3].get("audio"), f"'Always' -> spoken answer stored with the message {errs(a)}")

# Reset filters
go(a, ":material/bar_chart: My business")
act(a, [b for b in a.button if "Reset filters" in b.label][0].click())
ok(card(a, "💰").value == "₹1,21,36,222", f"reset filters -> full total {card(a,'💰').value}")

# Insights + PDF + WhatsApp
go(a, ":material/lightbulb: Tips & reports")
act(a, [b for b in a.button if "Generate iRaaya Insights" in b.label][0].click())
ok(not a.exception and len(a.session_state["insights"]) >= 3, f"insights generated: {len(a.session_state['insights'])} {errs(a)}")
ok(any(d.label.startswith("📄 Download PDF") for d in a.get("download_button")), "PDF report ready")
act(a, [b for b in a.button if "WhatsApp" in b.label][0].click())
ok(a.session_state["whatsapp"], "WhatsApp summary created")

# Clear chat, then Start fresh
go(a, ":material/mic: Ask iRaaya")
act(a, [b for b in a.button if "Clear chat" in b.label][0].click())
ok(a.session_state["chat_history"] == [], "clear chat")
[b for b in a.sidebar.button if "Start fresh" in b.label][0].click().run()
ok(not a.exception and a.session_state["df"] is None and a.session_state["company"] == "", f"start fresh resets data and settings {errs(a)}")
print(f"\n{sum(results)}/{len(results)} passed")
