"""FrostMind: smart fridge and health assistant (Streamlit prototype).

Run locally:  streamlit run app.py
Persist data: FROSTMIND_DB=inventory.db streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import sqlite3
import tempfile
import uuid
from html import escape as esc

import pandas as pd
import streamlit as st

import ui
from db import FridgeDB
from engine import (build_ambient_card, days_left, food_status, freshness,
                    meal_for_hour, now_ist, schedule_day)
from knowledge import MEALS
from receipts import fingerprint, ocr_image, parse_receipt, to_rows

st.set_page_config(page_title="FrostMind", page_icon="🧊", layout="wide")

SAMPLE_RECEIPT = (
    "AMUL TONED MILK 1L POUCH     MRP 66.00\n"
    "BRITANNIA BROWN BREAD 400G   MRP 45.00\n"
    "FARM FRESH EGGS TRAY OF 6    MRP 48.00\n"
    "2x MALAI PANEER 200G         MRP 190.00\n"
    "FRESH TAMATAR 500G           MRP 24.00\n"
    "BUTTON MUSHROOM 200G         MRP 40.00\n"
    "PEANUT BUTTER 340G           MRP 180.00\n"
    "MAGGI TOMATO KETCHUP 500G    MRP 95.00\n"
    "TATA SALT 1KG                MRP 28.00"
)


# ---------------------------------------------------------------- state ----
def get_db() -> FridgeDB:
    """One private database per browser session, so two judges opening the
    same public link never see each other's data. Set FROSTMIND_DB to persist."""
    if "db_path" not in st.session_state:
        st.session_state.db_path = os.getenv("FROSTMIND_DB") or os.path.join(
            tempfile.gettempdir(), f"frostmind_{uuid.uuid4().hex}.db")
    return FridgeDB(st.session_state.db_path)


def flash(msg: str, icon: str = "✅") -> None:
    st.session_state.setdefault("flash", []).append((msg, icon))


def guarded(fn):
    """Turn database errors into a friendly toast instead of a traceback."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except sqlite3.Error as exc:
            flash(f"Database error: {exc}", "⚠️")
    return wrapper


# ------------------------------------------------------------ callbacks ----
@guarded
def cb_parse(today_iso: str) -> None:
    today = dt.date.fromisoformat(today_iso)
    text = st.session_state.get("receipt_text", "")
    if not text.strip():
        st.session_state.parse_result = {"kind": "warning", "trace": [],
                                         "msg": "Nothing to parse. Paste a receipt first."}
        return
    parsed = parse_receipt(text)
    trace = [{"Receipt line": p.raw, "Matched": p.item.capitalize() if p.item else "—",
              "Confidence": p.score if p.item else None, "Qty": p.qty,
              "₹": (p.price or None) if p.item else None,
              "Expires": p.expiry(today).isoformat() if p.item else "skipped",
              "Why": p.note} for p in parsed]
    rows = to_rows(parsed, today)
    if not rows:
        res = {"kind": "error", "msg": "No groceries recognised. Check the text, "
               "or add the item to SHELF_LIFE_DB in knowledge.py."}
    else:
        outcome = get_db().add_receipt(fingerprint(text, today), rows)
        if outcome is None:
            res = {"kind": "warning", "msg": "This receipt is already logged for this "
                   "date, so nothing changed. (Prevents accidental double-counting.)"}
        else:
            new, merged = outcome
            msg = f"Logged {new} new item{'s' if new != 1 else ''}"
            msg += f" and merged {merged} into existing stock." if merged else "."
            skipped = len(parsed) - len(rows)
            if skipped:
                msg += f" Skipped {skipped} non-grocery line{'s' if skipped != 1 else ''}."
            res = {"kind": "success", "msg": msg}
            flash(f"Logged {new + merged} items")
    st.session_state.parse_result = {**res, "trace": trace}


def cb_load_demo(today_iso: str) -> None:
    st.session_state.receipt_text = SAMPLE_RECEIPT
    cb_parse(today_iso)


@guarded
def cb_reset() -> None:
    get_db().reset()
    for key in ("parse_result", "door_open", "ocr_sig", "ocr_msg"):
        st.session_state.pop(key, None)
    st.session_state.receipt_text = SAMPLE_RECEIPT
    flash("Demo reset to a clean fridge", "🧹")


@guarded
def cb_status(item_id: int, status: str, name: str) -> None:
    get_db().set_status(item_id, status)
    flash(f"{name} marked as {'used' if status == 'consumed' else 'binned'}",
          "✅" if status == "consumed" else "🗑️")


@guarded
def cb_taken(med_id: int, day_iso: str, name: str) -> None:
    get_db().log_dose(med_id, day_iso)
    flash(f"{name} logged as taken", "💊")


@guarded
def cb_add_med() -> None:
    ok = get_db().add_med(st.session_state.get("new_med", ""), st.session_state.new_meal)
    st.session_state.new_med = ""
    flash("Medication added" if ok else "Enter a new medicine name", "💊" if ok else "⚠️")


@guarded
def cb_del_med(med_id: int) -> None:
    get_db().delete_med(med_id)


def cb_door(opened: bool) -> None:
    st.session_state.door_open = opened


def cb_view(view: str) -> None:
    st.session_state.view = view


def taken_buttons(card: dict, day_iso: str, prefix: str) -> None:
    pending = card["due"] + card["missed"]
    if not pending:
        return
    st.caption("Tap when you have taken it:")
    cols = st.columns(min(len(pending), 3))
    for i, m in enumerate(pending):
        cols[i % len(cols)].button(
            f"✓ {m['med_name']}", key=f"{prefix}_taken_{m['id']}", on_click=cb_taken,
            args=(m["id"], day_iso, m["med_name"]))


# ------------------------------------------------------------------ run ----
st.markdown(ui.CSS, unsafe_allow_html=True)
st.session_state.setdefault(
    "view", "Door display" if st.query_params.get("view") == "door" else "Dashboard")
st.session_state.setdefault("receipt_text", SAMPLE_RECEIPT)

with st.sidebar:
    st.markdown("### ⚙️ Demo controls")
    st.radio("View", ["Dashboard", "Door display"], key="view", horizontal=True)
    offset = st.slider("Fast-forward the fridge clock (days)", 0, 21, 0, key="offset",
                       help="Shelf life only runs out over days. Drag this to see alerts.")
    st.selectbox("Meal window", ["Auto (from clock)", *MEALS], key="meal_choice")

now = now_ist()
today = schedule_day(now) + dt.timedelta(days=offset)
today_iso = today.isoformat()
choice = st.session_state.meal_choice
meal = meal_for_hour(now.hour) if choice.startswith("Auto") else choice
clock = now.strftime("%a %d %b · %I:%M %p IST")

try:
    db = get_db()
    inv = db.inventory("active")
    money = db.money_stats()
    meds = db.meds()
    taken = db.doses_taken(today_iso)
    card = build_ambient_card(db, today, meal)
except sqlite3.Error as exc:
    st.error(f"Database error: {exc}")
    st.stop()

with st.sidebar:
    c1, c2 = st.columns(2)
    c1.button("⚡ Load demo", on_click=cb_load_demo, args=(today_iso,),
              help="Logs a sample receipt so you can start instantly.")
    c2.button("🧹 Reset", on_click=cb_reset)
    st.divider()
    st.markdown("##### 💊 Medication schedule")
    for m in meds:
        a, b = st.columns([5, 1])
        a.markdown(f"**{esc(m['med_name'])}**<br><span style='color:#64748b;font-size:.8rem'>"
                   f"with {m['meal_window'].lower()}</span>", unsafe_allow_html=True)
        b.button("✕", key=f"delmed_{m['id']}", on_click=cb_del_med, args=(m["id"],))
    st.text_input("Medicine name", key="new_med", max_chars=60,
                  placeholder="e.g. Thyronorm 50mcg")
    st.selectbox("With which meal?", MEALS, key="new_meal")
    st.button("Add medication", on_click=cb_add_med)
    st.caption("⚠️ Demo only: don't enter real medication on a public link. "
               "FrostMind gives reminders, not medical advice.")

for msg, icon in st.session_state.pop("flash", []):
    st.toast(msg, icon=icon)

# ---- Door-display (kiosk) view --------------------------------------------
if st.session_state.view == "Door display":
    st.markdown(ui.KIOSK_CSS, unsafe_allow_html=True)
    st.markdown(ui.ambient_card(card, now.strftime("%I:%M %p"), kiosk=True),
                unsafe_allow_html=True)
    taken_buttons(card, today_iso, "kiosk")
    st.button("← Back to dashboard", on_click=cb_view, args=("Dashboard",))
    st.stop()

# ---- Dashboard ------------------------------------------------------------
st.markdown(ui.hero(clock, meal, offset, today), unsafe_allow_html=True)

attention = len(card["expired"]) + len(card["urgent"])
k = st.columns(5)
k[0].markdown(ui.kpi("In the fridge", str(int(inv.quantity.sum())) if not inv.empty else "0",
                     f"{len(inv)} line item{'s' if len(inv) != 1 else ''}"), unsafe_allow_html=True)
k[1].markdown(ui.kpi("Needs attention", str(attention),
                     f"{ui.inr(card['at_risk_value'])} at risk" if attention else "All good",
                     "warn" if attention else "good"), unsafe_allow_html=True)
k[2].markdown(ui.kpi("Doses today", f"{sum(m['id'] in taken for m in meds)}/{len(meds)}",
                     "taken", "good" if meds and all(m["id"] in taken for m in meds) else ""),
              unsafe_allow_html=True)
k[3].markdown(ui.kpi("Food saved", ui.inr(money["consumed_value"]),
                     f"{money['consumed_qty']} item{'s' if money['consumed_qty'] != 1 else ''} used", "good"), unsafe_allow_html=True)
k[4].markdown(ui.kpi("Food wasted", ui.inr(money["wasted_value"]),
                     f"{money['wasted_qty']} item{'s' if money['wasted_qty'] != 1 else ''} binned", "bad" if money["wasted_qty"] else ""),
              unsafe_allow_html=True)
st.write("")

tab1, tab2, tab3 = st.tabs(["🧾 Log groceries", "🚪 Door open", "📦 Fridge contents"])

with tab1:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Step 1 · Log what you bought")
        st.caption("Upload a photo of the receipt or paste its text. Prices, weights "
                   "and brand names are stripped automatically.")
        photo = st.file_uploader("📷 Receipt photo (optional)", type=["png", "jpg", "jpeg"])
        if photo is not None:
            sig = f"{photo.name}:{photo.size}"
            if st.session_state.get("ocr_sig") != sig:
                st.session_state.ocr_sig = sig
                text, err = ocr_image(photo.getvalue())
                if text:
                    st.session_state.receipt_text = text
                    st.session_state.ocr_msg = ("success", "Read the photo. Check the text before saving.")
                else:
                    st.session_state.ocr_msg = ("warning", f"{err} Paste the receipt text instead.")
        if st.session_state.get("ocr_msg"):
            getattr(st, st.session_state.ocr_msg[0])(st.session_state.ocr_msg[1])
        st.text_area("Receipt text", key="receipt_text", height=240)
        st.button("Parse and save", type="primary", on_click=cb_parse, args=(today_iso,))
    with right:
        st.markdown("#### What happens next")
        st.markdown("1. Each line is cleaned of prices and weights.\n"
                    "2. Words are matched to a shelf-life table, with typo tolerance.\n"
                    "3. Packaged goods like ketchup or peanut butter are skipped.\n"
                    "4. The price is kept, so you can see ₹ saved and wasted.")
        res = st.session_state.get("parse_result")
        if res:
            getattr(st, res["kind"])(res["msg"])
    res = st.session_state.get("parse_result")
    if res and res["trace"]:
        with st.expander("Why these items? (parser trace)", expanded=True):
            st.dataframe(
                pd.DataFrame(res["trace"]), hide_index=True,
                column_config={
                    "Confidence": st.column_config.ProgressColumn(
                        "Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                    "₹": st.column_config.NumberColumn("₹", format="%.0f")})

with tab2:
    st.markdown("#### Step 2 · The ambient moment")
    st.caption("This is what the door display shows the second the fridge opens. "
               "No app to open, no notification to dismiss.")
    if not st.session_state.get("door_open"):
        st.markdown(ui.empty_state("🚪", "The door is closed",
                                   "Open it to see what FrostMind shows."),
                    unsafe_allow_html=True)
        st.write("")
        st.button("Open the fridge door", type="primary", on_click=cb_door, args=(True,))
    else:
        st.markdown(ui.ambient_card(card, now.strftime("%I:%M %p")), unsafe_allow_html=True)
        st.write("")
        taken_buttons(card, today_iso, "door")
        st.button("Close the door", on_click=cb_door, args=(False,))
        st.caption("Tip: switch the sidebar to **Door display** for the full-screen version.")

with tab3:
    if inv.empty:
        st.markdown(ui.empty_state("🧊", "The fridge is empty",
                                   "Log a receipt, or press ⚡ Load demo in the sidebar."),
                    unsafe_allow_html=True)
    else:
        st.markdown("#### What is in the fridge")
        cols = st.columns(3)
        for i, r in enumerate(inv.itertuples()):
            d = days_left(r.expiry_date, today)
            status = food_status(d)
            with cols[i % 3], st.container(border=True, key=f"fmcard_{r.id}"):
                st.markdown(ui.item_card(r.item_name, int(r.quantity), status, d,
                                         freshness(r.date_added, r.expiry_date, today),
                                         r.date_added, r.expiry_date, float(r.price)),
                            unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                b1.button("✓ Used", key=f"use_{r.id}", on_click=cb_status,
                          args=(int(r.id), "consumed", r.item_name))
                b2.button("🗑 Binned", key=f"bin_{r.id}", on_click=cb_status,
                          args=(int(r.id), "wasted", r.item_name))
        st.markdown("#### Expiry timeline")
        timeline = pd.DataFrame(
            {"Days left": [days_left(r.expiry_date, today) for r in inv.itertuples()]},
            index=[f"{r.item_name} · {r.expiry_date[5:]}" for r in inv.itertuples()])
        st.bar_chart(timeline)
        st.download_button("Download inventory as CSV", inv.to_csv(index=False).encode(),
                           file_name="frostmind_inventory.csv", mime="text/csv")

st.caption("FrostMind prototype · shelf-life values are conservative estimates "
           "(verify against USDA FoodKeeper) · reminders only, not medical advice.")