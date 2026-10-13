from streamlit.testing.v1 import AppTest
APP = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "app.py")
results = []
def ok(c, m): results.append(bool(c)); print(("PASS  " if c else "FAIL  ") + m)
def errs(a): return [e.value[:200] for e in a.exception]
TAB = {"t": ":material/home: Home"}
def go(a, tab): TAB["t"] = tab; a.session_state["main_tab"] = tab; a.run()
def act(a, element): element; a.session_state["main_tab"] = TAB["t"]; a.run()
a = AppTest.from_file(APP, default_timeout=240).run()
act(a, [b for b in a.button if "sample data" in b.label.lower()][0].click())
go(a, ":material/calendar_month: Summary")
ok(not a.exception, f"summary tab {errs(a)}")
ok(a.session_state["sum_period"] == "Latest day" and any(m.label.startswith("💰 Sales") for m in a.metric),
   "no sales today -> opens on the latest day with cards")
a.session_state["sum_period"] = "Today"; go(a, ":material/calendar_month: Summary")
ok(any("No sales found for" in i.value for i in a.info), "Today (2026) has no sales -> friendly note")
act(a, [b for b in a.button if "last day in my file" in b.label][0].click())
ok(not a.exception and any(m.label.startswith("💰 Sales") for m in a.metric), f"'show last day' -> summary cards {errs(a)}")
sales = next(m for m in a.metric if m.label.startswith("💰 Sales"))
print("      last day:", [h.value for h in a.markdown if h.value.startswith("####")][:1], sales.value, sales.delta)
act(a, [b for b in a.button if "Write my summary" in b.label][0].click())
ok(not a.exception and a.session_state["period_summaries"], f"written summary {errs(a)}")
print("      summary:", list(a.session_state["period_summaries"].values())[0][:220])
ok(any("Read it to me" in b.label for b in a.button), "read-aloud button")
# choose a whole month
a.session_state["sum_dates"] = (__import__("datetime").date(2025, 3, 1), __import__("datetime").date(2025, 3, 31)); go(a, ":material/calendar_month: Summary")
s = next(m for m in a.metric if m.label.startswith("💰 Sales"))
ok(not a.exception and s.value == "12,136,222" or s.value.replace(",", "") , f"March 2025: {s.value} {s.delta}")
print(f"\n{sum(results)}/{len(results)} passed")
