# Start FrostMind on your laptop (Windows)

## 1. Install Python
Install Python 3.11 or newer from https://www.python.org/downloads/ . During setup, tick **Add Python to PATH**.

## 2. Open this project folder
Extract the ZIP. Open the extracted `hack-front-India-prototype-main` folder.

## 3. Install the app packages
Open Command Prompt or the VS Code terminal in this folder and run:

```bash
python -m pip install -r requirements.txt
```

## 4. Start FrostMind
Run:

```bash
python -m streamlit run app.py
```

A browser tab should open with FrostMind. If it does not, copy the `http://localhost:8501` address shown in the terminal into your browser.

## 5. Try the demo
1. In the left sidebar, click **Load sample household**.
2. Open **Smart Pantry** to see the sample groceries.
3. Open **Dabba Tracker** and add a sample leftover.
4. Open **Care & Reminders** to see medicine reminder controls.
5. Open **Fridge Door** to show the screen-first household reminder.
6. Open **Household** to add people (for example, Mother, Father, Grandma or Roommate 1).
7. Return to **Smart Pantry** or **Dabba Tracker** and assign each grocery or leftover to a household member.
8. Open **Care & Reminders** and choose the person a medicine reminder belongs to.

## Important
- Start the unified app using `app.py`, not `archive/app1_legacy.py`.
- You do not need a Sarvam API key to use the main app. Receipt text, pantry, Dabba, care reminders and fridge display work without it.
- Sarvam voice requires a valid `SARVAM_API_KEY`, internet access and available account credits.
- Receipt photo OCR additionally needs the Tesseract program installed on your computer. Pasting receipt text works without Tesseract.
- Use sample data for public judging. Do not enter real personal medical information into a public demo.
- Household members and their assignments are stored in the local SQLite database. Back up `frostmind.db` before replacing an older project folder.
- Removing a member moves their grocery, leftover and medicine reminder assignments to the shared household label; it does not erase those records.
