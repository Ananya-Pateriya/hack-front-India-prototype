# 🧊 FrostMind

A smart-fridge and health assistant that runs entirely offline on the fridge door.
Open the door, and the display tells you two things you would otherwise forget:
which food is about to spoil, and which medicine goes with this meal.

## Why

Two everyday problems share one trigger. Households throw out food they forgot
they had, and people on daily medication miss doses because a phone reminder
fires when they are nowhere near their pills. The fridge door is opened several
times a day, at meal times, by the same person. It is the one surface where both
reminders actually land.

## How it works

1. **Log** — paste the OCR text of a grocery receipt. The parser strips prices,
   weights and brand names, matches each token against a shelf-life table, and
   computes an expiry date per item.
2. **Trigger** — a reed switch on the door fires when it opens (simulated by a
   button here).
3. **Display** — the app renders a single ambient card: medication for the
   current meal window, plus anything expiring, with a rule-based suggestion for
   using it up.

No cloud, no LLM call, no account. Everything is local SQLite and deterministic
rules, so it runs on a Raspberry Pi Zero with the network unplugged.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501

## Demo script (90 seconds)

1. Open the sidebar. Point out the medication schedule is user-editable.
2. Tab 1 — click **Parse and save**. Expand the parser trace: show that
   `TATA SALT` was correctly skipped and `BRREAD` was recovered as bread.
3. Sidebar — drag the day slider to +5.
4. Tab 2 — click **Simulate door open**. This is the product: one card, read in
   two seconds, while the door is already open.
5. Tab 3 — mark an item **Used**. Watch the saved/wasted counter move.

## Architecture

```
receipt text ─▶ normalise() ─▶ match_item() ─▶ SQLite (inventory)
                                                    │
door reed switch ─▶ expiry_report() ◀───────────────┤
                          │                          │
medication schedule ◀─────┴──▶ ambient display ◀────┘
```

## Roadmap

- Camera + Tesseract OCR on-device, replacing pasted text
- Load-cell weight sensing to infer consumption without a button press
- E-ink panel driver for the physical door display
- Household shared list over local mDNS, no server

## Stack

Python · Streamlit · SQLite · difflib. Target hardware: Raspberry Pi Zero 2 W,
reed switch, 4.2" e-ink panel.