"""FrostMind OS — unified, multi-page Streamlit MVP.
Run: streamlit run app.py
Optional persistent DB path: FROSTMIND_DB=./frostmind.db
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from db import FridgeDB
from engine import (build_ambient_card, days_left, food_status, meal_for_hour,
                    now_ist, schedule_day, short_days)
from knowledge import MEALS, RESCUE_IDEAS
from receipts import fingerprint, ocr_image, parse_receipt, to_rows
from sarvam_voice import speak_card, transcribe_voice
import ui

st.set_page_config(
    page_title="FrostMind OS",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded",
)

SAMPLE_RECEIPT = """AMUL TONED MILK 1L POUCH     MRP 66.00
BRITANNIA BROWN BREAD 400G   MRP 45.00
FARM FRESH EGGS TRAY OF 6    MRP 48.00
2x MALAI PANEER 200G         MRP 190.00
FRESH TAMATAR 500G           MRP 24.00
BUTTON MUSHROOM 200G         MRP 40.00
IDLI DOSA BATTER 1KG         MRP 85.00
PEANUT BUTTER 340G           MRP 180.00
TATA SALT 1KG                MRP 28.00"""

# ------------------------------ styling ----------------------------------
st.markdown("""
<style>
:root { --fm-bg:#0b1220; --fm-panel:#131f33; --fm-panel2:#192941; --fm-line:#2a3b55; --fm-text:#eef4ff; --fm-muted:#a9bad1; --fm-teal:#22b8ad; }
.stApp { background:var(--fm-bg); color:var(--fm-text); }
.block-container {padding-top:1.25rem; padding-bottom:2.5rem; max-width:1420px;}
#MainMenu, footer {visibility:hidden;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stSidebar"] {background:#0e192b; border-right:1px solid var(--fm-line);}
[data-testid="stSidebar"] * {color:#eef4ff;}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding:7px 10px; border-radius:10px;}
h1,h2,h3,h4,p,li,label,.stMarkdown {color:var(--fm-text);}
small,[data-testid="stCaptionContainer"] {color:var(--fm-muted)!important;}
.fm-hero {padding:26px 30px; border-radius:22px; color:white; background:linear-gradient(115deg,#10243d,#087e8b 75%,#159e98); margin-bottom:18px; border:1px solid #2b8290;}
.fm-hero h1 {font-size:2.15rem; color:white; margin:0 0 4px 0;}
.fm-hero p {color:#d8f3f4; margin:0; font-size:1rem;}
.fm-chip {display:inline-block; border:1px solid #ffffff40; background:#ffffff1c; border-radius:30px; padding:5px 11px; margin:12px 7px 0 0; font-size:.76rem; color:#f5ffff;}
.fm-sub {color:var(--fm-muted); font-size:.94rem; margin-bottom:14px;}
div[data-testid="stMetric"] {background:var(--fm-panel); border:1px solid var(--fm-line); padding:15px 17px; border-radius:16px; box-shadow:0 4px 15px #02081740;}
div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricLabel"] {color:#b9cbe0!important;}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {color:#ffffff!important;}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {color:#7ee0bd!important;}
.stButton button, .stDownloadButton button {border-radius:10px; font-weight:650; min-height:2.55rem; border:1px solid #40536e; background:#192941; color:#f5f8ff;}
.stButton button:hover,.stDownloadButton button:hover {border-color:#2dd4bf;color:#ffffff;background:#203653;}
.stButton button[kind="primary"] {background:#0f8b8d;border-color:#20b7ad;color:white;}
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], [data-baseweb="input"] {border-radius:10px; background:#17263c; color:#f3f7ff; border-color:#40536e;}
[data-baseweb="popover"] {color:#f3f7ff;}
.fm-note {padding:13px 16px; border-radius:12px; background:#10352f; border:1px solid #1c6b5c; color:#c8fff0;}
.fm-warning {padding:13px 16px; border-radius:12px; background:#3a2c16; border:1px solid #8a6326; color:#ffe7b0;}
.fm-card {padding:15px 17px; border:1px solid var(--fm-line); border-radius:15px; background:var(--fm-panel); margin-bottom:10px; color:var(--fm-text);}
.fm-muted {color:var(--fm-muted)!important; font-size:.84rem;}
[data-testid="stDataFrame"] {border:1px solid var(--fm-line); border-radius:12px; overflow:hidden;}
[data-testid="stTabs"] button {color:#c8d6e8!important;}
[data-testid="stTabs"] button[aria-selected="true"] {color:#5eead4!important; border-bottom-color:#2dd4bf!important;}
[data-testid="stAlert"] {border-radius:12px;}
</style>
""", unsafe_allow_html=True)

# ------------------------------ database ---------------------------------
@st.cache_resource
def get_db() -> FridgeDB:
    db_path = os.getenv("FROSTMIND_DB", str(Path(__file__).with_name("frostmind.db")))
    return FridgeDB(db_path)

db = get_db()
now = now_ist()
today = schedule_day(now)
today_iso = today.isoformat()

# ------------------------------ helpers ----------------------------------
def flash_result(message: str, kind: str = "success") -> None:
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.error(message)


def add_sample_data(owner: str) -> None:
    parsed = parse_receipt(SAMPLE_RECEIPT)
    rows = to_rows(parsed, today)
    outcome = db.add_receipt(f"frostmind-demo-{today_iso}-{owner}", rows, owner=owner)
    if outcome is None:
        st.info("Sample groceries are already loaded for today.")
    else:
        st.success(f"Demo groceries added: {outcome[0]} new items, {outcome[1]} merged.")


def status_label(expiry: str) -> tuple[str, str]:
    remaining = days_left(expiry, today)
    state = food_status(remaining)
    return state, short_days(remaining)


def render_voice(card: dict, language: str) -> None:
    st.markdown("#### 🔊 Kitchen voice reminder")
    if language == "hi-IN":
        st.caption("Hindi reminder preview. Speech generation requires a configured Sarvam API key and available credits.")
    else:
        st.caption("English reminder preview. Speech generation requires a configured Sarvam API key and available credits.")
    if st.button("Generate spoken reminder", key="speak_kitchen"):
        audio, error = speak_card(card, lang=language)
        if audio:
            st.audio(audio, format="audio/wav")
        else:
            st.info("Voice service is unavailable right now. Your reminder is still available as text below.")
            if error:
                st.caption(error)
            st.write(ui.ambient_text(card, now.strftime("%I:%M %p")))


def page_header(title: str, subtitle: str) -> None:
    st.title(title)
    st.markdown(f'<div class="fm-sub">{subtitle}</div>', unsafe_allow_html=True)


def owner_picker(label: str, widget_key: str, shared_label: str = "Shared") -> str:
    """Pick Shared or a named household member; create a member inline when requested."""
    names_now = [m["name"] for m in db.members()]
    add_option = "＋ Add another member…"
    options = [shared_label, *names_now, add_option]
    pending_key = f"{widget_key}_pending"
    if pending_key in st.session_state:
        st.session_state[widget_key] = st.session_state.pop(pending_key)
    current = st.session_state.get(widget_key, shared_label)
    if current not in options:
        current = shared_label
    selected = st.selectbox(label, options, index=options.index(current), key=widget_key)
    if selected == add_option:
        with st.container(border=True):
            st.caption("Add a person to this household")
            name_key = f"{widget_key}_new_name"
            new_name = st.text_input("Member name", placeholder="e.g. Mother, Aarav, Grandma", key=name_key)
            clean_name = " ".join(new_name.split())
            exists = any(n.casefold() == clean_name.casefold() for n in names_now)
            c1, c2 = st.columns([1, 2])
            with c1:
                add_clicked = st.button("＋ Add member", key=f"{widget_key}_add_btn",
                                         type="primary", use_container_width=True,
                                         disabled=not clean_name or exists)
            with c2:
                if exists:
                    st.caption("That member already exists. Select their name above.")
            if add_clicked and db.add_member(clean_name, "Family member"):
                st.session_state[pending_key] = clean_name
                st.session_state.pop(name_key, None)
                st.success(f"{clean_name} added. Assigning this grocery to them.")
                st.rerun()
        return shared_label
    return selected

# ------------------------------ navigation -------------------------------
with st.sidebar:
    st.markdown("# 🧊 FrostMind OS")
    st.caption("Zero-hassle kitchen & care")
    st.divider()
    mode = st.radio("Household mode", ["🏠 Indian Family", "🏢 PG / Flatmates"], key="household_mode")
    is_flatmate = mode.startswith("🏢")
    owner_default = "Shared"
    household_members = db.members()
    member_names = [m["name"] for m in household_members]
    owner_options = [owner_default, *member_names]
    if "navigate_to" in st.session_state:
        st.session_state.active_page = st.session_state.pop("navigate_to")
    page = st.radio(
        "WORKSPACE",
        ["Overview", "Smart Pantry", "Dabba Tracker", "Care & Reminders", "Fridge Door", "Household"],
        key="active_page",
    )
    st.divider()
    st.caption("DEMO TOOLS")
    if st.button("⚡ Load sample household", use_container_width=True):
        add_sample_data(owner_default)
    if st.button("↻ Reset demo data", use_container_width=True):
        db.reset()
        st.session_state.pop("parse_result", None)
        st.success("Demo data reset. Your default reminder templates are restored.")
    st.divider()
    st.caption("Prototype · Offline-first · Local SQLite")

inv = db.inventory("active")
meds = db.meds()
taken = db.doses_taken(today_iso)
leftovers = db.leftovers("active")
meal = meal_for_hour(now.hour)
card = build_ambient_card(db, today, meal, flatmate_mode=is_flatmate)
money = db.money_stats()

# ------------------------------ overview ---------------------------------
if page == "Overview":
    st.markdown(f'''<div class="fm-hero"><h1>Good {'morning' if now.hour < 12 else 'afternoon' if now.hour < 17 else 'evening'} 👋</h1>
    <p>Your kitchen, groceries and family-care reminders — in one calm workspace.</p>
    <span class="fm-chip">🍽️ {meal} window</span><span class="fm-chip">🧺 {len(inv)} active pantry items</span>
    <span class="fm-chip">🏡 {'Flatmate mode' if is_flatmate else 'Family mode'}</span></div>''', unsafe_allow_html=True)
    attention = sum(1 for r in inv.itertuples() if days_left(r.expiry_date, today) <= 3)
    cols = st.columns(4)
    cols[0].metric("In your pantry", int(inv.quantity.sum()) if not inv.empty else 0, f"{len(inv)} tracked items")
    cols[1].metric("Use soon", attention, "Prioritise these items")
    cols[2].metric("Medicine doses", f"{len(taken)}/{len(meds)}", "Confirmed today")
    cols[3].metric("Food saved", f"₹{money['consumed_value']:,.0f}", f"{money['consumed_qty']} items used")

    st.markdown("### Today's priorities")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        urgent_items = [r for r in inv.itertuples() if days_left(r.expiry_date, today) <= 3]
        if urgent_items:
            for r in urgent_items[:5]:
                state, label = status_label(r.expiry_date)
                st.markdown(f"<div class='fm-card'><b>🥬 {r.item_name}</b><br><span class='fm-muted'>{label} · Qty {r.quantity}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="fm-note">✅ No pantry items need urgent attention right now.</div>', unsafe_allow_html=True)
        if leftovers:
            st.markdown("#### Leftover Dabbas")
            for item in leftovers[:3]:
                due_at = dt.datetime.fromisoformat(item["remind_at"])
                st.write(f"🍱 **{item['item_name']}** · reminder {due_at.strftime('%d %b, %I:%M %p')}")
    with right:
        st.markdown("#### Care reminders")
        if meds:
            for med in meds:
                is_done = med["id"] in taken
                st.markdown(f"{'✅' if is_done else '💊'} **{med['med_name']}** · {med['meal_window']} · {'Confirmed' if is_done else 'Pending'}")
        else:
            st.info("No medicine schedules added yet.")
        st.markdown("#### Quick actions")
        a, b = st.columns(2)
        if a.button("＋ Log groceries", use_container_width=True):
            st.session_state.navigate_to = "Smart Pantry"
            st.rerun()
        if b.button("🍱 Add leftover", use_container_width=True):
            st.session_state.navigate_to = "Dabba Tracker"
            st.rerun()
        if st.button("🚪 Open fridge door display", use_container_width=True):
            st.session_state.door_open = True
            st.session_state.navigate_to = "Fridge Door"
            st.rerun()

# ------------------------------ smart pantry -----------------------------
elif page == "Smart Pantry":
    page_header("🧺 Smart Pantry", "Bring groceries in once. FrostMind helps you remember what to use first.")
    if st.session_state.pop("show_pantry_after_parse", False):
        st.session_state.pantry_workspace = "Your pantry"
    pantry_view = st.radio("Pantry workspace", ["＋ Add groceries", "Your pantry"], horizontal=True,
                           key="pantry_workspace", label_visibility="collapsed")
    if pantry_view == "＋ Add groceries":
        st.markdown("#### Add a quick-commerce order or grocery receipt")
        st.caption("Paste receipt text or upload a receipt photo. Packaged staples are filtered out; recognised perishables are added to your pantry.")
        uploaded = st.file_uploader("Receipt photo (optional)", type=["png", "jpg", "jpeg"], key="pantry_receipt_photo")
        if uploaded is not None and st.button("Read receipt photo", key="read_receipt"):
            extracted, error = ocr_image(uploaded.getvalue())
            if extracted:
                st.session_state.receipt_text = extracted
                st.success("Receipt text extracted. Review it below before saving.")
            else:
                st.warning(error)
        voice_clip = st.audio_input("Or record a quick grocery voice drop (Hindi / Hinglish)")
        if voice_clip is not None and st.button("Transcribe voice drop", key="transcribe_grocery_voice"):
            transcript, voice_error = transcribe_voice(voice_clip.getvalue())
            if transcript:
                st.session_state.receipt_text = transcript
                st.success("Voice converted to text. Review it before saving.")
            else:
                st.info(voice_error or "Voice transcription is unavailable. Paste the grocery text instead.")
        owner = owner_picker("Who does this grocery belong to?", "receipt_owner_picker", "Shared")
        with st.form("receipt_form"):
            receipt_text = st.text_area("Receipt or voice transcript", value=st.session_state.get("receipt_text", SAMPLE_RECEIPT), height=190,
                                        placeholder="Paste Blinkit, Zepto, Instamart or MilkBasket order text…")
            submit_receipt = st.form_submit_button("✨ Identify perishables & add to pantry", type="primary", use_container_width=True)
        if submit_receipt:
            parsed = parse_receipt(receipt_text)
            rows = to_rows(parsed, today)
            if not rows:
                st.warning("No supported perishable items were recognised. Try another receipt or add the item manually later.")
            else:
                outcome = db.add_receipt(fingerprint(receipt_text, today) + f":{owner}", rows, owner=owner)
                if outcome is None:
                    st.info("This receipt has already been added today. Your existing pantry records are unchanged.")
                else:
                    st.success(f"Added {outcome[0]} new items and updated {outcome[1]} existing items.")
                st.session_state.receipt_text = receipt_text
            recognised = [p for p in parsed if p.item]
            if recognised:
                display_rows = [{"Grocery": p.item.title(), "Quantity": p.qty, "Amount": f"₹{p.price:,.0f}" if p.price else "—",
                                 "Estimated use-by": p.expiry(today).strftime("%d %b %Y")} for p in recognised]
                st.markdown("#### Items identified")
                st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
                st.caption("Expiry dates are estimates. Check the product label and storage guidance.")
                st.session_state.show_pantry_after_parse = True
                st.rerun()
    else:
        st.markdown("#### Pantry inventory")
        if inv.empty:
            st.info("Your pantry is empty. Add a receipt or load sample household data from the sidebar.")
        else:
            filter_owner = st.selectbox("Show groceries for", ["All", *owner_options], key=f"pantry_owner_filter_{'flatmate' if is_flatmate else 'family'}")
            inv_view = inv[inv.owner == filter_owner] if filter_owner != "All" else inv
            for r in inv_view.itertuples():
                state, label = status_label(r.expiry_date)
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.markdown(f"**{r.item_name}**  \n<span class='fm-muted'>{label} · Added {r.date_added} · {r.owner}</span>", unsafe_allow_html=True)
                    c2.write(f"Qty: **{r.quantity}**")
                    if c3.button("✓ Used", key=f"used_{r.id}"):
                        db.set_status(int(r.id), "consumed")
                        st.rerun()
                    if st.button("Mark wasted", key=f"waste_{r.id}"):
                        db.set_status(int(r.id), "wasted")
                        st.rerun()
            st.download_button("⬇ Download pantry CSV", inv_view.to_csv(index=False).encode("utf-8"),
                               file_name="frostmind_pantry.csv", mime="text/csv")

# ------------------------------ dabba tracker ----------------------------
elif page == "Dabba Tracker":
    page_header("🍱 Leftover Dabba Tracker", "A one-tap way to remember cooked food stored in steel dabbas.")
    st.markdown('<div class="fm-note">Log what went into the fridge. FrostMind starts a reminder timer so leftovers are not forgotten at the back of the shelf.</div>', unsafe_allow_html=True)
    st.write("")
    with st.form("dabba_form"):
        food_name = st.selectbox("What did you store?", ["Dal", "Sabzi", "Rice", "Roti", "Paneer", "Cooked vegetables", "Biryani", "Other"])
        custom_name = st.text_input("If other, enter the dish name", placeholder="e.g. Lauki kofta")
        col1, col2 = st.columns(2)
        with col1:
            stored_date = st.date_input("Stored date", value=now.date())
            stored_time = st.time_input("Stored time", value=now.time().replace(second=0, microsecond=0))
        with col2:
            reminder_hours = st.selectbox("Remind me after", [6, 12, 18, 24, 36], index=3, format_func=lambda x: f"{x} hours")
            dabba_owner = st.selectbox("Belongs to", owner_options, key=f"dabba_owner_{'flatmate' if is_flatmate else 'family'}")
        save_dabba = st.form_submit_button("＋ Start Dabba timer", type="primary", use_container_width=True)
    if save_dabba:
        chosen_name = custom_name.strip() if food_name == "Other" else food_name
        if not chosen_name:
            st.warning("Enter the dish name first.")
        else:
            stored_at = dt.datetime.combine(stored_date, stored_time).replace(tzinfo=now.tzinfo)
            remind_at = stored_at + dt.timedelta(hours=reminder_hours)
            db.add_leftover(chosen_name, stored_at.isoformat(), remind_at.isoformat(), dabba_owner)
            st.success(f"{chosen_name} added. Reminder set for {remind_at.strftime('%d %b, %I:%M %p')}.")
            st.rerun()
    st.markdown("### Active Dabbas")
    if not leftovers:
        st.info("No leftovers tracked yet. Add your first Dabba above.")
    for item in leftovers:
        remind_at = dt.datetime.fromisoformat(item["remind_at"])
        is_due = now >= remind_at
        with st.container(border=True):
            a, b, c = st.columns([3, 2, 1])
            a.markdown(f"**🍱 {item['item_name']}**  \n<span class='fm-muted'>{item['owner']} · Stored {dt.datetime.fromisoformat(item['stored_at']).strftime('%d %b, %I:%M %p')}</span>", unsafe_allow_html=True)
            b.markdown(f"{'🔔 Reminder due' if is_due else '⏳ Reminder'}  \n**{remind_at.strftime('%d %b, %I:%M %p')}**")
            if c.button("Used", key=f"dabba_used_{item['id']}"):
                db.set_leftover_status(item["id"], "consumed")
                st.rerun()
            if c.button("Discarded", key=f"dabba_discard_{item['id']}"):
                db.set_leftover_status(item["id"], "wasted")
                st.rerun()
    history = db.leftovers("consumed") + db.leftovers("wasted")
    if history:
        with st.expander("Recently completed Dabbas"):
            for item in history[-10:]:
                st.write(f"{ '✅ Used' if item['status']=='consumed' else '🗑️ Discarded'} · {item['item_name']}")

# ------------------------------ care -------------------------------------
elif page == "Care & Reminders":
    page_header("💊 Care & Reminders", "Keep household medicine schedules visible and easy to confirm.")
    st.markdown('<div class="fm-warning">FrostMind provides reminders only. Enter schedules exactly as prescribed by a qualified clinician. Do not use this prototype to decide doses or change treatment.</div>', unsafe_allow_html=True)
    st.write("")
    meds = db.meds()
    taken = db.doses_taken(today_iso)
    done_count = sum(m["id"] in taken for m in meds)
    st.progress(done_count / max(1, len(meds)), text=f"{done_count} of {len(meds)} scheduled reminders confirmed today")
    st.markdown("### Today's schedule")
    if not meds:
        st.info("No reminders yet. Add a schedule below.")
    for med in meds:
        with st.container(border=True):
            a, b, c = st.columns([3, 2, 1])
            a.markdown(f"**💊 {med['med_name']}**  \n<span class='fm-muted'>{med.get('member_name', 'Family')} · Linked to {med['meal_window'].lower()}</span>", unsafe_allow_html=True)
            b.write("✅ Confirmed" if med["id"] in taken else "🕒 Awaiting confirmation")
            if med["id"] not in taken and c.button("Confirm", key=f"med_taken_{med['id']}"):
                db.log_dose(med["id"], today_iso)
                st.rerun()
            if c.button("Remove", key=f"med_remove_{med['id']}"):
                db.delete_med(med["id"])
                st.rerun()
    st.markdown("### Add a reminder")
    with st.form("med_form"):
        med_name = st.text_input("Medicine name", placeholder="Enter the name exactly as prescribed")
        med_member = st.selectbox("Reminder for", owner_options, key=f"med_member_owner_{'flatmate' if is_flatmate else 'family'}")
        med_meal = st.selectbox("Associate with meal", MEALS)
        add_med = st.form_submit_button("＋ Add medicine reminder", type="primary")
    if add_med:
        if db.add_med(med_name, med_meal, med_member):
            st.success("Reminder added.")
            st.rerun()
        else:
            st.warning("Enter a medicine name. This reminder may already exist.")

# ------------------------------ fridge door -----------------------------
elif page == "Fridge Door":
    page_header("🚪 Fridge Door", "A simple ambient display that activates when the fridge door opens.")
    if "door_open" not in st.session_state:
        st.session_state.door_open = False
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.markdown("**Door status**")
        st.caption("Use the controls below to simulate the magnetic door sensor. Arduino integration can replace this control later.")
    with top_right:
        if not st.session_state.door_open:
            if st.button("🚪 Open door", type="primary", use_container_width=True):
                st.session_state.door_open = True
                st.rerun()
        else:
            if st.button("↩ Close door", use_container_width=True):
                st.session_state.door_open = False
                st.rerun()
    if not st.session_state.door_open:
        st.markdown("""<div style="background:#14243a;border:1px solid #30445f;border-radius:22px;padding:38px 24px;text-align:center;margin-top:12px;">
        <div style="font-size:3rem">🧊</div><h2 style="color:#f2f7ff;margin:8px 0">Fridge is closed</h2>
        <p style="color:#b6c8de;margin:0">Open the door to show food priorities and meal-linked care reminders.</p></div>""", unsafe_allow_html=True)
    else:
        card = build_ambient_card(db, today, meal, flatmate_mode=is_flatmate)
        st.markdown(ui.ambient_card(card, now.strftime("%I:%M %p"), kiosk=True), unsafe_allow_html=True)
        due_meds = card["due"] + card["missed"]
        if due_meds and not is_flatmate:
            st.markdown("#### Confirm a reminder")
            for med in due_meds:
                if st.button(f"✓ Confirm {med['med_name']}", key=f"door_med_{med['id']}"):
                    db.log_dose(med["id"], today_iso)
                    st.rerun()
        language = st.selectbox("Reminder language", ["hi-IN", "en-IN"], format_func=lambda x: "Hindi" if x == "hi-IN" else "Indian English")
        render_voice(card, language)
        st.caption("Speech generation is optional. The on-screen reminder works without Sarvam credits.")

# ------------------------------ household --------------------------------
elif page == "Household":
    page_header("🏡 Household Members", "Add the people in your home and assign groceries and care reminders to each person.")
    shared_label = "Shared"
    st.markdown(f"<div class='fm-card'><b>{'🏢 PG / Flatmates' if is_flatmate else '🏠 Indian Family'}</b><br><span class='fm-muted'>Shared groceries belong to Shared. Add any number of named people and assign personal groceries and medicine reminders to them.</span></div>", unsafe_allow_html=True)

    st.markdown("### Add a household member")
    with st.form("add_household_member", clear_on_submit=True):
        new_name = st.text_input("Member name", placeholder="e.g. Grandma, Aarav, Roommate 1")
        relationship = st.selectbox("Relationship / role", ["Family member", "Parent", "Grandparent", "Child", "Self", "Flatmate", "Caregiver", "Other"])
        add_member = st.form_submit_button("＋ Add member", type="primary")
    if add_member:
        if db.add_member(new_name, relationship):
            st.success(f"{new_name.strip()} added to your household.")
            st.rerun()
        else:
            st.warning("Enter a unique member name. Names Family, Shared and All are reserved for shared ownership.")

    current_members = db.members()
    st.markdown("### Household members")
    if not current_members:
        st.info("No individual members added yet. Use “＋ Add another member…” in the grocery selector or add people here. Shared remains available for common groceries.")
    for person in current_members:
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f"**👤 {person['name']}**  \n<span class='fm-muted'>{person['relationship']}</span>", unsafe_allow_html=True)
            if right.button("Remove", key=f"remove_member_{person['id']}"):
                db.delete_member(person["id"], shared_owner=shared_label)
                st.success(f"{person['name']} removed. Their grocery and reminder assignments were moved to {shared_label}.")
                st.rerun()

    st.markdown("### Household summary")
    all_items = db.inventory("active")
    all_meds = db.meds()
    summary_rows = []
    for label in [shared_label, *[m["name"] for m in current_members]]:
        summary_rows.append({"Member / ownership": label,
                             "Active groceries": int((all_items.owner == label).sum()) if not all_items.empty else 0,
                             "Medicine reminders": sum(m.get("member_name", shared_label) == label for m in all_meds)})
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    st.markdown("### Privacy & safety")
    st.caption("This prototype stores household names and assignments locally in SQLite. Medicine schedules should match clinician instructions. A member's medicine reminders are shown with their name so the household can distinguish them.")

st.divider()
st.caption("FrostMind OS · Hackathon prototype · Offline-first design · Demo data only. Avoid entering personal health information into a public deployment.")
