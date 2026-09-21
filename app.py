"""
FrostMind — Smart Fridge & Health Assistant (MVP)
Offline-first ambient assistant for a fridge door: tracks grocery shelf life
and nudges medication at the right meal, using only local SQLite + rule logic.

Run:  streamlit run app.py
"""

import datetime
import re
import sqlite3
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st

DB_PATH = "inventory.db"
EXPIRY_ALERT_DAYS = 3

# --------------------------------------------------------------------------
# 1. KNOWLEDGE BASE
# --------------------------------------------------------------------------
# Shelf life in days once the item is home and refrigerated.
SHELF_LIFE_DB = {
    "milk": 7, "bread": 4, "eggs": 21, "yogurt": 10, "curd": 5,
    "butter": 30, "cheese": 21, "paneer": 5, "cream": 7,
    "tomatoes": 5, "apples": 14, "bananas": 4, "spinach": 3,
    "coriander": 4, "carrots": 14, "onions": 30, "potatoes": 21,
    "chicken": 2, "fish": 1, "mutton": 2, "juice": 5, "rice": 3,
}

# Alternate names an OCR line may use for a canonical item.
ALIASES = {
    "dahi": "yogurt", "curd": "yogurt", "toned": "milk", "doodh": "milk",
    "atta": "bread", "pav": "bread", "anda": "eggs", "egg": "eggs",
    "tamatar": "tomatoes", "tomato": "tomatoes", "seb": "apples",
    "apple": "apples", "palak": "spinach", "dhania": "coriander",
    "gajar": "carrots", "pyaz": "onions", "aloo": "potatoes",
    "makhan": "butter", "malai": "cream", "murgh": "chicken",
    "banana": "bananas", "carrot": "carrots", "potato": "potatoes",
    "onion": "onions",
}

# Noise words that appear on every Indian retail receipt and must never match.
STOPWORDS = {
    "mrp", "rs", "inr", "qty", "pc", "pcs", "pkt", "pack", "packet", "pouch",
    "tray", "box", "bottle", "jar", "g", "gm", "gms", "kg", "ml", "l", "ltr",
    "litre", "liter", "total", "gst", "cgst", "sgst", "bill", "invoice",
    "cash", "card", "upi", "change", "amt", "amount", "discount", "item",
    "items", "fresh", "farm", "premium", "special", "offer", "new", "pure",
    "amul", "britannia", "mother", "dairy", "nestle", "tata", "patanjali",
}

# Rule-based "use it up" ideas. No model needed — runs on a Pi with no network.
RESCUE_IDEAS = {
    "milk": "Boil into kheer or set it as curd overnight.",
    "bread": "Cube and bake into croutons, or make bread upma.",
    "eggs": "Hard-boil today — cooked eggs buy you another 5 days.",
    "yogurt": "Whisk into a marinade for tomorrow's chicken or paneer.",
    "tomatoes": "Cook down into a base gravy and freeze it.",
    "paneer": "Pan-fry and refrigerate — fried paneer keeps 2 days longer.",
    "spinach": "Blanch and freeze, or make palak dal tonight.",
    "coriander": "Blitz into chutney with green chilli and lemon.",
    "bananas": "Freeze the peeled fruit for smoothies or banana bread.",
    "chicken": "Cook it today, then it keeps 3 more days cooked.",
    "curd": "Churn into buttermilk with cumin and salt.",
}


# --------------------------------------------------------------------------
# 2. DATABASE
# --------------------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                date_added TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                UNIQUE (item_name, expiry_date, status)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                med_name TEXT NOT NULL,
                meal_window TEXT NOT NULL,
                UNIQUE (med_name, meal_window)
            )
        """)
        cur.execute("SELECT COUNT(*) FROM medications")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO medications (med_name, meal_window) VALUES (?, ?)",
                [("Metformin 500mg", "Breakfast"), ("Amlodipine 5mg", "Dinner")],
            )


def save_items(items):
    """UPSERT: same item + same expiry on the same run bumps quantity instead
    of creating a duplicate row."""
    inserted, merged = 0, 0
    with get_conn() as conn:
        cur = conn.cursor()
        for name, qty, added, expiry in items:
            cur.execute(
                "SELECT id, quantity FROM inventory "
                "WHERE item_name=? AND expiry_date=? AND status='active'",
                (name, expiry),
            )
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE inventory SET quantity=? WHERE id=?",
                            (row[1] + qty, row[0]))
                merged += 1
            else:
                cur.execute(
                    "INSERT INTO inventory (item_name, quantity, date_added, expiry_date) "
                    "VALUES (?, ?, ?, ?)", (name, qty, added, expiry))
                inserted += 1
    return inserted, merged


def fetch_inventory(status="active"):
    with get_conn() as conn:
        return pd.read_sql_query(
            "SELECT id, item_name, quantity, date_added, expiry_date, status "
            "FROM inventory WHERE status=? ORDER BY expiry_date ASC",
            conn, params=(status,))


def set_status(item_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE inventory SET status=? WHERE id=?", (status, item_id))


def fetch_meds(meal=None):
    with get_conn() as conn:
        if meal:
            rows = conn.execute(
                "SELECT med_name FROM medications WHERE meal_window=? ORDER BY med_name",
                (meal,)).fetchall()
            return [r[0] for r in rows]
        return pd.read_sql_query(
            "SELECT id, med_name, meal_window FROM medications ORDER BY id", get_conn())


def add_med(name, meal):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO medications (med_name, meal_window) VALUES (?, ?)",
            (name.strip(), meal))


def delete_med(med_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM medications WHERE id=?", (med_id,))


def waste_stats():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, SUM(quantity) FROM inventory GROUP BY status")
        d = dict(cur.fetchall())
    return d.get("consumed", 0) or 0, d.get("wasted", 0) or 0


# --------------------------------------------------------------------------
# 3. RECEIPT PARSING
# --------------------------------------------------------------------------
def normalise(line):
    """Strip prices, quantities and punctuation, return (qty, [tokens])."""
    line = line.lower()
    qty_match = re.match(r"\s*(\d{1,2})\s*[x*]\s", line)
    qty = int(qty_match.group(1)) if qty_match else 1
    line = re.sub(r"(rs|inr|mrp)?\.?\s*\d+[.,]\d{2}", " ", line)   # prices
    line = re.sub(r"\d+\s*(kg|g|gm|gms|ml|l|ltr|litre|liter|pc|pcs)\b", " ", line)
    line = re.sub(r"[^a-z\s]", " ", line)
    tokens = [t for t in line.split() if len(t) > 1 and t not in STOPWORDS]
    return qty, tokens


def match_item(tokens, cutoff=0.82):
    """Match per token, not per whole line. Exact/alias hits win outright;
    fuzzy only catches OCR typos like 'brread'."""
    # Pass 1: an exact canonical name anywhere in the line always wins, so
    # "MALAI PANEER" resolves to paneer and not to the alias malai -> cream.
    for token in tokens:
        if token in SHELF_LIFE_DB:
            return token, 1.0
    # Pass 2: regional / informal names.
    for token in tokens:
        if token in ALIASES:
            return ALIASES[token], 1.0
    # Pass 3: fuzzy, for OCR typos only.
    best, best_score = None, 0.0
    for token in tokens:
        for key in list(SHELF_LIFE_DB) + list(ALIASES):
            score = SequenceMatcher(None, token, key).ratio()
            if score >= cutoff and score > best_score:
                best_score = score
                best = ALIASES.get(key, key)
    return best, best_score


def process_receipt_text(raw_text, today):
    """Returns (rows_to_save, trace) — trace powers the explainability panel."""
    rows, trace = [], []
    for raw_line in raw_text.split("\n"):
        if not raw_line.strip():
            continue
        qty, tokens = normalise(raw_line)
        item, score = match_item(tokens)
        if item:
            expiry = today + datetime.timedelta(days=SHELF_LIFE_DB[item])
            rows.append((item.capitalize(), qty, today.isoformat(), expiry.isoformat()))
            trace.append({"Receipt line": raw_line.strip(), "Matched": item.capitalize(),
                          "Confidence": f"{score:.2f}", "Qty": qty,
                          "Expires": expiry.isoformat()})
        else:
            trace.append({"Receipt line": raw_line.strip(), "Matched": "—",
                          "Confidence": "—", "Qty": qty, "Expires": "skipped"})
    return rows, trace


def expiry_report(today):
    """Split active stock into expired / urgent, newest deadline first."""
    df = fetch_inventory("active")
    expired, urgent = [], []
    for _, r in df.iterrows():
        days_left = (datetime.date.fromisoformat(r["expiry_date"]) - today).days
        entry = {"id": int(r["id"]), "name": r["item_name"],
                 "qty": int(r["quantity"]), "days": days_left}
        if days_left < 0:
            expired.append(entry)
        elif days_left <= EXPIRY_ALERT_DAYS:
            urgent.append(entry)
    return expired, urgent


def phrase_days(days):
    if days < 0:
        return f"expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
    if days == 0:
        return "expires today"
    if days == 1:
        return "expires tomorrow"
    return f"expires in {days} days"


# --------------------------------------------------------------------------
# 4. UI
# --------------------------------------------------------------------------
init_db()
st.set_page_config(page_title="FrostMind MVP", page_icon="🧊", layout="centered")

with st.sidebar:
    st.header("⚙️ Demo controls")
    offset = st.slider("Days from today", 0, 21, 0,
                       help="Fast-forward the clock to watch shelf life run out.")
    today = datetime.date.today() + datetime.timedelta(days=offset)
    st.caption(f"Fridge clock: **{today.isoformat()}**")

    st.divider()
    st.subheader("💊 Medication schedule")
    meds_df = fetch_meds()
    for _, m in meds_df.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"{m['med_name']} · {m['meal_window']}")
        if c2.button("✕", key=f"delmed{m['id']}"):
            delete_med(int(m["id"]))
            st.rerun()
    new_med = st.text_input("Medicine name", placeholder="e.g. Thyronorm 50mcg")
    new_meal = st.selectbox("With which meal?", ["Breakfast", "Lunch", "Dinner"],
                            key="medmeal")
    if st.button("Add medication") and new_med.strip():
        add_med(new_med, new_meal)
        st.rerun()

st.title("🧊 FrostMind")
st.caption("Smart fridge and health assistant — runs fully offline on the fridge door.")

consumed, wasted = waste_stats()
active_df = fetch_inventory("active")
expired, urgent = expiry_report(today)

m1, m2, m3 = st.columns(3)
m1.metric("Items in fridge", int(active_df["quantity"].sum()) if not active_df.empty else 0)
m2.metric("Needs attention", len(expired) + len(urgent))
m3.metric("Saved vs wasted", f"{consumed} / {wasted}")

tab1, tab2, tab3 = st.tabs(["🧾 Log groceries", "🚪 Door open", "📦 Fridge contents"])

# ---- TAB 1 ---------------------------------------------------------------
with tab1:
    st.subheader("Step 1 — log what you bought")
    st.write("Paste the OCR text from a grocery receipt. Prices, weights and brand "
             "names are stripped automatically.")
    raw_input = st.text_area(
        "Receipt text",
        value=("AMUL TONED MILK 1L POUCH     MRP 66.00\n"
               "BRITANNIA BROWN BREAD 400G   MRP 45.00\n"
               "FARM FRESH EGGS TRAY OF 6    MRP 48.00\n"
               "2x MALAI PANEER 200G         MRP 95.00\n"
               "FRESH TAMATAR 500G           MRP 24.00\n"
               "TATA SALT 1KG                MRP 28.00"),
        height=170)

    if st.button("Parse and save", type="primary"):
        if not raw_input.strip():
            st.warning("Nothing to parse. Paste a receipt first.")
        else:
            rows, trace = process_receipt_text(raw_input, today)
            st.session_state["trace"] = trace
            if rows:
                new, merged = save_items(rows)
                msg = f"Logged {new} new item{'s' if new != 1 else ''}"
                if merged:
                    msg += f", merged {merged} into existing stock"
                st.success(msg + ".")
                st.rerun()
            else:
                st.error("No groceries recognised. Check the OCR text, or add the "
                         "item to SHELF_LIFE_DB.")

    if st.session_state.get("trace"):
        with st.expander("Why these items? (parser trace)", expanded=True):
            st.dataframe(pd.DataFrame(st.session_state["trace"]), hide_index=True)

# ---- TAB 2 ---------------------------------------------------------------
with tab2:
    st.subheader("Step 2 — the ambient moment")
    st.write("This is what the door display shows the second the fridge opens. "
             "No app to open, no notification to dismiss.")
    meal = st.selectbox("Current meal window", ["Breakfast", "Lunch", "Dinner"])

    if st.button("🚪 Simulate door open", type="primary"):
        st.info("Reed switch triggered — building ambient prompt…")
        meds = fetch_meds(meal)

        st.markdown("### 📢 Ambient display")
        if meds:
            st.error(f"💊 **Take {', '.join(meds)}** with your {meal.lower()}.")
        else:
            st.success(f"💊 Nothing to take at {meal.lower()}.")

        if expired:
            st.error("🗑️ **Throw out:** " + ", ".join(
                f"{e['name']} ({phrase_days(e['days'])})" for e in expired))
        if urgent:
            lines = []
            for u in urgent:
                idea = RESCUE_IDEAS.get(u["name"].lower(), "")
                lines.append(f"- **{u['name']}** — {phrase_days(u['days'])}."
                             + (f" {idea}" if idea else ""))
            st.warning("⚠️ **Use these first:**\n" + "\n".join(lines))
        if not expired and not urgent:
            st.success("🥦 Everything in the fridge is still fresh.")

# ---- TAB 3 ---------------------------------------------------------------
with tab3:
    st.subheader("Fridge contents")
    if active_df.empty:
        st.info("The fridge is empty. Log a receipt to fill it.")
    else:
        for _, r in active_df.iterrows():
            days = (datetime.date.fromisoformat(r["expiry_date"]) - today).days
            c1, c2, c3 = st.columns([5, 1.2, 1.2])
            dot = "🔴" if days < 0 else "🟠" if days <= EXPIRY_ALERT_DAYS else "🟢"
            c1.write(f"{dot} **{r['item_name']}** ×{r['quantity']} — {phrase_days(days)}")
            if c2.button("Used", key=f"use{r['id']}"):
                set_status(int(r["id"]), "consumed")
                st.rerun()
            if c3.button("Binned", key=f"bin{r['id']}"):
                set_status(int(r["id"]), "wasted")
                st.rerun()

        st.divider()
        st.download_button("Download inventory as CSV",
                           active_df.to_csv(index=False).encode(),
                           file_name="frostmind_inventory.csv", mime="text/csv")