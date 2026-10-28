# 🧊 FrostMind

A smart-fridge assistant that runs offline on the fridge door. Open the door and
it shows two things you would otherwise forget: what food to use first, and
which medicine goes with this meal.

**Why the fridge door?** Phone reminders fire when you are nowhere near your
pills or your food. The fridge is opened at every meal by the same person, so
it is the one surface where both reminders land at the right moment.

## What it does

- **Log groceries** from a receipt photo (Tesseract OCR) or pasted text. Prices,
  weights and brand names are stripped, words are matched to a shelf-life table
  with typo tolerance, and packaged goods (ketchup, peanut butter) are skipped.
- **Door-open card** with medication for the current meal, missed-dose alerts,
  expired and expiring food, and rule-based "use it up" ideas. No LLM, no cloud.
- **Dose tracking:** tap *Taken*; earlier unticked doses show as missed.
- **₹ impact:** the receipt price is kept, so the dashboard shows food saved and wasted.
- **Door display (kiosk) view** for the fridge-door screen: sidebar -> View -> Door display,
  or open `?view=door`.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Receipt photos need the Tesseract engine (`sudo apt install tesseract-ocr`, or
`brew install tesseract`). Without it the app still works: paste text instead.

Each browser session gets its own private temporary database. To keep data
between runs, set `FROSTMIND_DB=inventory.db`.

## Tests

```bash
pip install pytest
pytest -q
```

## On the fridge hardware

`door_watcher.py` uses the same engine and database and prints the door card
when the door opens. Simulated by default (press Enter). With a reed switch:
`FROSTMIND_GPIO_PIN=17 FROSTMIND_DB=inventory.db python door_watcher.py`.
**The GPIO path is untested on real hardware.**

## Deploy (Streamlit Community Cloud)

Push this repo to GitHub, then share.streamlit.io -> New app -> `app.py`.
`packages.txt` installs Tesseract for you.

## Honest limits

- Shelf-life numbers are conservative estimates, **not** copied from a
  reference. Verify against the USDA FoodKeeper open dataset
  (FoodSafety.gov/FoodKeeper, also on Data.gov) or FSSAI guidance before real use.
- OCR quality depends on the photo. The paste box is the fallback.
- Fridge-door sensing and consumption tracking are simulated (buttons).
- Reminders only, not medical advice. Do not enter real medication on a public demo.
- The medication day rolls over at 05:00 IST, and times use a fixed +05:30 offset.
- the tesseract spec may not work due to incompatibility issue.

## Layout

| File | Role |
|---|---|
| `app.py` | Streamlit UI and callbacks |
| `ui.py` | CSS and escaped HTML builders |
| `engine.py` | Pure logic: time, expiry, the ambient card |
| `receipts.py` | Receipt parsing and OCR |
| `db.py` | SQLite storage |
| `knowledge.py` | Shelf life, aliases, filters, tips |
| `door_watcher.py` | Hardware-side loop (simulated sensor by default) |
| `tests/test_core.py` | Unit tests and a headless app run |

APP URL : http://localhost:8501/
