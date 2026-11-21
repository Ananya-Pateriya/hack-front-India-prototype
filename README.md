# FrostMind OS

FrostMind is an offline-first household kitchen and care assistant designed around Indian household routines: quick-commerce receipts, perishable groceries, steel-dabba leftovers, meal-linked reminders, and a screen-first fridge-door view.

## What's in the unified MVP

- **Overview:** household summary, pantry priorities, medicine reminder status, and quick actions.
- **Smart Pantry:** receipt photo OCR (when Tesseract is installed), pasted Blinkit/Zepto/Instamart text, perishable-only parsing, inventory status, and CSV export.
- **Dabba Tracker:** one-tap leftover logging with a configurable reminder timer and Used/Discarded actions.
- **Care & Reminders:** user-entered meal-associated medicine reminders and daily confirmation tracking.
- **Fridge Door:** screen-first ambient display combining food priorities and meal-linked reminders.
- **Household:** Family or PG/flatmate ownership views.

The old concept-rich `app1.py` is preserved in `archive/app1_legacy.py` as a reference. Run only the unified `app.py`.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

For receipt-photo OCR, install the Tesseract OCR system package as well as the Python dependencies. Receipt text paste works without OCR.

## Optional Sarvam voice

Set `SARVAM_API_KEY` as an environment variable or in Streamlit secrets. FrostMind uses Saaras v4 for speech-to-text and Bulbul v4 Flash for text-to-speech. Voice is optional; the core application remains usable without an API key or credits. Never paste an API key into the dashboard or commit it to GitHub.

## Data storage

By default, the app creates `frostmind.db` beside `app.py`. To choose another location:

```bash
FROSTMIND_DB=./data/frostmind.db streamlit run app.py
```

The database is local to the running app environment. Streamlit-hosted storage may be ephemeral; use an appropriate persistent database before treating a public deployment as a real household service. Do not enter real health information into a public hackathon deployment.

## Demo notes and limitations

- Shelf-life values are estimates, not food-safety certifications. Check packaging and authoritative storage guidance.
- Dabba reminders are timers, not food-safety determinations.
- Medicine features are reminders only; users must follow clinician instructions. A button confirmation is not proof that medicine was taken.
- Arduino/UNO Q sensor input is not connected in this software-only build. The fridge-door screen is a software preview.
- WhatsApp delivery and direct quick-commerce account integrations are not implemented; receipt text/photo import is the demo workflow.
- Sarvam speech needs network access, a valid key, and available credits. Local Windows speech fallback may be available; other environments show a text fallback.

## Tests

```bash
python -m pip install pytest
pytest -q
```

See [START_HERE.md](START_HERE.md) for beginner-friendly Windows setup and demo steps.

## Live App URL
- https://hack-front-india-prototype-3xpdwbc9xyv68dt6fyowra.streamlit.app/
