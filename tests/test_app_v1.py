from streamlit.testing.v1 import AppTest
APP = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "app.py")
results = []
def ok(c, m): results.append(c); print(("PASS  " if c else "FAIL  ") + m)
def errs(a): return [e.value for e in a.exception]

a = AppTest.from_file(APP, default_timeout=180).run()
ok(not a.exception, f"app starts {errs(a)}")
ok(any("Your business voice" in m.value for m in a.markdown), "welcome screen with brand and tagline")
ok(any(b.label == "Try with sample data" for b in a.button), "three ways to start shown")
[b for b in a.button if "sample data" in b.label.lower()][0].click().run()
ok(not a.exception and a.session_state["df"] is not None, f"sample loads {errs(a)}")
ok(len([m for m in a.metric if m.label.startswith(("💰","🧾","🧮","📦","🏆","📍","⭐","💳"))]) == 8, "8 cards on My business")
ok(any("Compared with" in c.value for c in a.caption) and "▲" not in "" , "period caption with comparison")
ok((next(m for m in a.metric if m.label.startswith("💰")).delta or "").startswith("+27.8%"), "last 30 days vs the 30 before: +27.8%")
ok(len(a.get("plotly_chart")) >= 5, f"charts on dashboard: {len(a.get('plotly_chart'))}")
ok(any("glance" in e.label for e in a.expander), "data preview shown")
ok(len([b for b in a.button if b.key and b.key.startswith("ex_")]) >= 4, "Explain this chart buttons")

# New Home: snapshot, cards, things to know, monthly target
HOME = ":material/home: Home"
a.session_state["main_tab"] = HOME; a.run()
md = " ".join(m.value for m in a.markdown)
ok(not a.exception and "vs a usual" in md and "Sun 22 Jun 2025" in md, f"snapshot shows latest day vs usual {errs(a)}")
ok("Hello" not in md, "no 'Hello' greeting")
ok("Things to know" in md and "in the last 7 days" in md, "things to know from the data")
a.number_input(key="target_entry").set_value(1500000); a.session_state["main_tab"] = HOME; a.run()
[b for b in a.button if b.label == "Save target"][0].click(); a.session_state["main_tab"] = HOME; a.run()
md = " ".join(m.value for m in a.markdown)
ok(a.session_state["target"] == 1500000 and "67% there" in md, f"monthly target progress (June 2025: 1,000,227 of 1,500,000) {errs(a)}")
a.button(key="go_ask").click(); a.run()
ok(a.session_state["main_tab"] == ":material/mic: Ask iRaaya", "big voice card opens Ask iRaaya")
a.session_state["main_tab"] = ":material/mic: Ask iRaaya"; a.run()
ok(any(b.label == "How did Floor Cleaner do in June?" for b in a.button), "example questions use the shop's own products")
a.session_state["main_tab"] = ":material/bar_chart: My business"; a.run()
for tab in [":material/mic: Ask iRaaya", ":material/calendar_month: Summary", ":material/lightbulb: Tips & reports", ":material/settings: Settings", ":material/home: Home", ":material/bar_chart: My business"]:
    a.session_state["main_tab"] = tab; a.run()
    ok(not a.exception, f"tab {tab} renders {errs(a)}")
print(f"\n{sum(results)}/{len(results)} passed")
