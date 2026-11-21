import base64
import difflib
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st

# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & CLEAN UI STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="FrostMind | Zero-Hassle Kitchen & Care OS",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = "frostmind_prod.db"

# ---------------------------------------------------------
# 2. PRODUCTION DATABASE LAYER (WAL MODE + METRICS)
# ---------------------------------------------------------
@st.cache_resource
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> sqlite3.Connection:
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT 'Family',
            source TEXT NOT NULL DEFAULT 'Quick-Commerce',
            added_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            med_name TEXT NOT NULL,
            meal_window TEXT NOT NULL,
            in_fridge INTEGER NOT NULL DEFAULT 0,
            taken_today INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Seed realistic Indian household + flatmate data on first boot
    c.execute("SELECT COUNT(*) FROM inventory")
    if c.fetchone()[0] == 0:
        now = datetime.now()
        seeds = [
            ("Amul Malai Paneer (200g)", "Dairy", "Family", "Blinkit", now.isoformat(), (now + timedelta(hours=9)).isoformat(), "active"),
            ("Cooked Dal Dabba", "Leftover", "Family", "1-Tap Dabba", now.isoformat(), (now + timedelta(hours=16)).isoformat(), "active"),
            ("ID Idli/Dosa Batter (1kg)", "Batter", "Rahul", "Zepto", now.isoformat(), (now + timedelta(hours=38)).isoformat(), "active"),
            ("Mother Dairy Full Cream Milk (1L)", "Dairy", "Aarav", "MilkBasket", now.isoformat(), (now + timedelta(hours=14)).isoformat(), "active"),
        ]
        c.executemany(
            """
            INSERT INTO inventory (item_name, category, owner, source, added_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            seeds,
        )

    c.execute("SELECT COUNT(*) FROM medications")
    if c.fetchone()[0] == 0:
        med_seeds = [
            ("Metformin 500mg (Post-Breakfast)", "Breakfast (8:00 - 10:30 AM)", 0, 0),
            ("Human Mixtard Insulin Pen", "Dinner (8:00 - 10:30 PM)", 1, 0),
        ]
        c.executemany(
            "INSERT INTO medications (med_name, meal_window, in_fridge, taken_today) VALUES (?, ?, ?, ?)",
            med_seeds,
        )

    conn.commit()
    return conn


conn = init_db()

# ---------------------------------------------------------
# 3. INDIAN PERISHABLE SHELF-LIFE ENGINE (DIFLIB + RULES)
# ---------------------------------------------------------
PERISHABLE_CATALOG: Dict[str, Tuple[str, int]] = {
    "milk": ("Dairy", 36),
    "doodh": ("Dairy", 36),
    "paneer": ("Dairy", 48),
    "curd": ("Dairy", 72),
    "dahi": ("Dairy", 72),
    "buttermilk": ("Dairy", 48),
    "chaas": ("Dairy", 48),
    "cream": ("Dairy", 72),
    "batter": ("Batter", 72),
    "idli": ("Batter", 72),
    "dosa": ("Batter", 72),
    "bread": ("Bakery", 72),
    "pav": ("Bakery", 48),
    "bun": ("Bakery", 48),
    "mushroom": ("Produce", 48),
    "coriander": ("Produce", 48),
    "dhaniya": ("Produce", 48),
    "spinach": ("Produce", 48),
    "palak": ("Produce", 48),
    "methi": ("Produce", 48),
    "leftover": ("Leftover", 36),
    "dabba": ("Leftover", 36),
    "dal": ("Leftover", 36),
    "sabzi": ("Leftover", 36),
    "biryani": ("Leftover", 36),
    "curry": ("Leftover", 36),
    "chicken": ("Meat/Seafood", 24),
    "mutton": ("Meat/Seafood", 24),
    "fish": ("Meat/Seafood", 24),
    "prawns": ("Meat/Seafood", 24),
}


def extract_perishables(raw_text: str, default_owner: str = "Family") -> List[Tuple[str, str, str, str, str]]:
    """
    Filters quick-commerce bills or voice transcripts to capture ONLY high-spoilage items,
    automatically ignoring non-perishable staples (atta, rice, oil, salt, detergent).
    """
    lines = [line.strip() for line in re.split(r"[\n,;]+", raw_text) if line.strip()]
    catalog_keys = list(PERISHABLE_CATALOG.keys())
    extracted = []

    for line in lines:
        # Strip currency symbols, prices, and package weights
        cleaned = re.sub(
            r"(₹|rs\.?)\s*\d+(\.\d+)?|\b\d+(\.\d+)?\s*(g|gm|gms|kg|ml|l|ltr|pcs|pack|pkt)\b",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip(" -–—:")

        tokens = re.findall(r"[a-zA-Z]+", cleaned.lower())
        matched_key: Optional[str] = None

        for token in tokens:
            if token in PERISHABLE_CATALOG:
                matched_key = token
                break
            close = difflib.get_close_matches(token, catalog_keys, n=1, cutoff=0.84)
            if close:
                matched_key = close[0]
                break

        if matched_key:
            category, shelf_hours = PERISHABLE_CATALOG[matched_key]
            now = datetime.now()
            expires = now + timedelta(hours=shelf_hours)
            display_name = cleaned.title() if len(cleaned) >= 3 else matched_key.title()
            extracted.append((display_name, category, default_owner, now.isoformat(), expires.isoformat()))

    return extracted


# ---------------------------------------------------------
# 4. SARVAM AI PRODUCTION CLIENT (SAFE SECRETS + RETRIES)
# ---------------------------------------------------------
def get_sarvam_api_key() -> str:
    try:
        if "SARVAM_API_KEY" in st.secrets:
            return str(st.secrets["SARVAM_API_KEY"]).strip()
    except Exception:
        pass
    return os.getenv("SARVAM_API_KEY", "").strip()


def sarvam_speech_to_text(audio_bytes: bytes, api_key: str) -> str:
    """Transcribes Hinglish/Indian audio into Latin transliteration via Sarvam Saaras v4."""
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {"api-subscription-key": api_key}
    files = {"file": ("voice_drop.wav", audio_bytes, "audio/wav")}
    data = {
        "model": "saaras:v4",
        "mode": "translit",  # Outputs Latin script so fuzzy keyword matching works across Hindi/English
    }
    response = requests.post(url, headers=headers, files=files, data=data, timeout=25)
    response.raise_for_status()
    return response.json().get("transcript", "").strip()


def sarvam_text_to_speech(text: str, lang_code: str, speaker: str, api_key: str) -> bytes:
    """Generates low-latency Indian speech audio via Sarvam Bulbul v4 Flash."""
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:500],
        "target_language_code": lang_code,
        "speaker": speaker,
        "model": "bulbul:v4-flash",
        "pace": 1.0,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=25)
    response.raise_for_status()
    audios = response.json().get("audios", [])
    if not audios:
        raise RuntimeError("Sarvam TTS returned empty audio payload.")
    return base64.b64decode("".join(audios))


# ---------------------------------------------------------
# 5. SIDEBAR: HOUSEHOLD MODE, SARVAM AI & POWER-CUT SIMULATOR
# ---------------------------------------------------------
with st.sidebar:
    st.title("❄️ FrostMind OS")
    st.caption("Zero-Hassle Kitchen & Care OS")

    mode = st.radio(
        "Deployment Mode",
        ["Indian Family Mode", "PG / Flatmate Mode"],
        help="Family Mode prioritizes elderly post-meal meds & zero-effort kitchen digests. PG Mode tracks roommate item ownership.",
    )

    st.divider()
    st.subheader("🔑 Sarvam AI Voice Config")
    default_key = get_sarvam_api_key()
    sarvam_key = st.text_input(
        "Sarvam API Key",
        value=default_key,
        type="password",
        placeholder="Paste key or set SARVAM_API_KEY in secrets",
    )

    voice_profiles = {
        "Hindi — Sanchita (hi-IN)": ("hi-IN", "sanchita"),
        "Indian English — Sophia (en-IN)": ("en-IN", "sophia"),
        "Bengali — Arnab (bn-IN)": ("bn-IN", "arnab"),
        "Tamil — Ishita (ta-IN)": ("ta-IN", "ishita"),
        "Marathi — Sanchita (mr-IN)": ("mr-IN", "sanchita"),
    }
    selected_voice = st.selectbox("Spoken Reminder Voice", list(voice_profiles.keys()))
    lang_code, speaker_id = voice_profiles[selected_voice]

    st.divider()
    st.subheader("🌡️ Power-Cut Cold-Chain Guard")
    fridge_temp = st.slider("Internal Temp (°C)", min_value=2.0, max_value=18.0, value=4.5, step=0.5)
    warm_minutes = st.slider("Cumulative Minutes > 8°C", min_value=0, max_value=240, value=15, step=15)

    st.divider()
    if st.button("🔄 Reset Daily Meds Status", use_container_width=True):
        conn.execute("UPDATE medications SET taken_today = 0")
        conn.commit()
        st.rerun()

# ---------------------------------------------------------
# 6. TOP METRICS & COLD-CHAIN STATUS BANNER
# ---------------------------------------------------------
st.header(f"❄️ FrostMind — {mode}")
st.markdown(
    "Solving **household food spoilage** and **missed post-meal/cold-chain medications** with **zero daily dashboard friction**."
)

c = conn.cursor()
c.execute("SELECT COUNT(*) FROM inventory WHERE status = 'active'")
active_count = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM inventory WHERE status = 'consumed'")
saved_count = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM medications WHERE taken_today = 0")
pending_med_count = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM medications WHERE in_fridge = 1")
insulin_stored = c.fetchone()[0] > 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Active Perishables", f"{active_count} items")
m2.metric("Items Saved Before Expiry", f"{saved_count} items")
m3.metric("Pending Meds Today", f"{pending_med_count} doses")
m4.metric("Fridge Zone", f"{fridge_temp}°C", delta="Safe (2–8°C)" if fridge_temp <= 8.0 else "Warm Drift", delta_color="normal" if fridge_temp <= 8.0 else "inverse")

# Cumulative thermal exposure logic (avoids false alarms on brief door openings)
if fridge_temp > 8.0 and warm_minutes >= 90:
    st.error(
        f"🚨 **CRITICAL COLD-CHAIN RISK:** Internal temperature at **{fridge_temp}°C** for **{warm_minutes} mins**. "
        + ("**Refrigerated Insulin potency compromised** & milk/batter spoiling!" if insulin_stored else "High spoilage risk for milk, paneer, and batters!")
    )
elif fridge_temp > 8.0 and warm_minutes >= 30:
    st.warning(
        f"⚠️ **Power-Cut Cooling Drift ({fridge_temp}°C for {warm_minutes}m):** Tracking thermal exposure. Alert escalates at 90 mins."
    )
else:
    st.success(f"✅ **Cold-Chain Protected ({fridge_temp}°C):** Refrigerated medicines and dairy are safely within 2–8°C.")

st.divider()

# ---------------------------------------------------------
# 7. CORE 3-COLUMN PRODUCTION WORKFLOW
# ---------------------------------------------------------
col_input, col_tracker, col_output = st.columns([1.15, 1.2, 1.1])

# === COLUMN 1: ZERO-FRICTION INGESTION ===
with col_input:
    st.subheader("1. Zero-Typing Ingestion")

    owner_tag = (
        st.selectbox("Item Owner", ["Family", "Rahul", "Aarav", "Priya", "Sneha"])
        if mode == "PG / Flatmate Mode"
        else "Family"
    )

    st.markdown("**🍲 1-Tap Leftover Steel Dabba**")
    if st.button("+ Log Cooked Leftover (36h Timer)", use_container_width=True):
        now = datetime.now()
        conn.execute(
            "INSERT INTO inventory (item_name, category, owner, source, added_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Cooked Leftover Dabba", "Leftover", owner_tag, "1-Tap Dabba", now.isoformat(), (now + timedelta(hours=36)).isoformat(), "active"),
        )
        conn.commit()
        st.toast("Logged Leftover Dabba (36h expiry)")
        st.rerun()

    st.markdown("---")
    st.markdown("**🛒 Quick-Commerce Bill Auto-Filter**")
    default_bill = (
        "Amul Taaza Toned Milk 1L - ₹54\n"
        "Mother Dairy Malai Paneer 200g - ₹95\n"
        "Aashirvaad Shudh Chakki Atta 5kg - ₹245\n"
        "Tata Sampann Toor Dal 1kg - ₹160\n"
        "ID Fresh Idli Dosa Batter 1kg - ₹85"
    )
    bill_input = st.text_area(
        "Paste Blinkit / Zepto / Instamart / MilkBasket order (auto-ignores dry staples):",
        value=default_bill,
        height=125,
    )
    if st.button("📥 Extract Perishables Only", use_container_width=True):
        items = extract_perishables(bill_input, default_owner=owner_tag)
        if items:
            for item_name, cat, own, added, exp in items:
                conn.execute(
                    "INSERT INTO inventory (item_name, category, owner, source, added_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (item_name, cat, own, "Quick-Commerce", added, exp, "active"),
                )
            conn.commit()
            st.success(f"Added {len(items)} perishable(s) — dry staples ignored.")
            st.rerun()
        else:
            st.info("No high-spoilage items detected in pasted order.")

    st.markdown("---")
    st.markdown("**🎙️ Sarvam Voice Drop (Hands-Free)**")
    voice_blob = st.audio_input("Speak naturally (e.g., 'Rahul ka paneer aur kal ki dal')")
    if voice_blob is not None:
        if not sarvam_key:
            st.warning("Add your Sarvam API Key in the sidebar to transcribe live speech.")
        else:
            if st.button("Transcribe & Auto-Log", use_container_width=True):
                with st.spinner("Processing via Sarvam Saaras v4..."):
                    try:
                        transcript = sarvam_speech_to_text(voice_blob.getvalue(), sarvam_key)
                        st.info(f"**Heard:** `{transcript}`")
                        inferred_owner = owner_tag
                        for candidate in ["Rahul", "Aarav", "Priya", "Sneha"]:
                            if candidate.lower() in transcript.lower():
                                inferred_owner = candidate
                                break
                        items = extract_perishables(transcript, default_owner=inferred_owner)
                        if items:
                            for item_name, cat, own, added, exp in items:
                                conn.execute(
                                    "INSERT INTO inventory (item_name, category, owner, source, added_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (item_name, cat, own, "Sarvam Voice", added, exp, "active"),
                                )
                            conn.commit()
                            st.success(f"Logged {len(items)} item(s) for {inferred_owner}!")
                            st.rerun()
                        else:
                            st.warning("Heard voice note, but no perishable food keyword matched.")
                    except Exception as exc:
                        st.error(f"Sarvam STT Error: {exc}")

# === COLUMN 2: EXPIRY WATCHLIST & MEDICATION SCHEDULE ===
with col_tracker:
    st.subheader("2. Expiry & Medication Watch")

    c.execute(
        "SELECT id, item_name, category, owner, source, expires_at FROM inventory WHERE status = 'active' ORDER BY expires_at ASC"
    )
    active_items = c.fetchall()
    urgent_items: List[str] = []

    if not active_items:
        st.info("Zero expiring items in fridge right now.")
    else:
        now = datetime.now()
        for row_id, name, cat, owner, src, exp_iso in active_items:
            exp_dt = datetime.fromisoformat(exp_iso)
            hrs_left = round((exp_dt - now).total_seconds() / 3600, 1)
            owner_label = f" · **[{owner}]**" if mode == "PG / Flatmate Mode" else ""

            if hrs_left <= 24:
                urgent_items.append(f"{name} ({owner})" if mode == "PG / Flatmate Mode" else name)
                urgency_badge = f"🔴 **{max(0.0, hrs_left)}h left**"
            else:
                urgency_badge = f"🟢 {round(hrs_left / 24, 1)}d left"

            i_col, act_col = st.columns([3.4, 1])
            i_col.markdown(f"**{name}**{owner_label}  \n{cat} · {src} · {urgency_badge}")
            if act_col.button("Used", key=f"consume_{row_id}"):
                conn.execute("UPDATE inventory SET status = 'consumed' WHERE id = ?", (row_id,))
                conn.commit()
                st.rerun()

    st.markdown("---")
    st.markdown("**💊 Meal-Anchored Medications**")
    c.execute("SELECT id, med_name, meal_window, in_fridge, taken_today FROM medications")
    med_rows = c.fetchall()
    pending_med_names: List[str] = []

    for med_id, med_name, meal_win, in_fridge, taken in med_rows:
        if not taken:
            pending_med_names.append(med_name)
        m_col, btn_col = st.columns([3.4, 1])
        storage_badge = "❄️ Fridge Cold-Chain" if in_fridge else "🍽️ Post-Meal"
        icon = "✅" if taken else "⏰"
        m_col.markdown(f"{icon} **{med_name}**  \n{storage_badge} · {meal_win}")
        if not taken:
            if btn_col.button("Taken", key=f"take_med_{med_id}"):
                conn.execute("UPDATE medications SET taken_today = 1 WHERE id = ?", (med_id,))
                conn.commit()
                st.rerun()

    with st.expander("➕ Add Household Medication"):
        with st.form("add_med_form", clear_on_submit=True):
            new_med = st.text_input("Medicine Name", placeholder="e.g., Telma 40mg (BP)")
            new_win = st.selectbox(
                "Meal Anchor Window",
                ["Breakfast (8:00 - 10:30 AM)", "Lunch (1:00 - 3:00 PM)", "Dinner (8:00 - 10:30 PM)"],
            )
            new_fridge = st.checkbox("Stored inside fridge (e.g., Insulin / Pediatric Syrup)")
            if st.form_submit_button("Save Medicine") and new_med.strip():
                conn.execute(
                    "INSERT INTO medications (med_name, meal_window, in_fridge, taken_today) VALUES (?, ?, ?, 0)",
                    (new_med.strip(), new_win, int(new_fridge)),
                )
                conn.commit()
                st.rerun()

# === COLUMN 3: AMBIENT KITCHEN VOICE & WHATSAPP DIGEST ===
with col_output:
    st.subheader("3. Ambient Kitchen Output")
    st.caption("Zero-screen output delivered via spoken door chime + morning WhatsApp summary.")

    active_meal = st.selectbox(
        "Current Meal Window",
        ["Breakfast (8:00 - 10:30 AM)", "Lunch (1:00 - 3:00 PM)", "Dinner (8:00 - 10:30 PM)"],
    )

    lead_item = urgent_items[0] if urgent_items else "Paneer"
    lead_med = pending_med_names[0] if pending_med_names else "subah ki dawai"

    if mode == "PG / Flatmate Mode":
        auto_nudge = (
            f"Namaste! {lead_item} aaj expire hone wala hai, please use kar lijiye, "
            f"aur apni {lead_med} lena mat bhooliye."
        )
    else:
        auto_nudge = (
            f"Namaste! Aaj khane mein {lead_item} pehle use kar lijiye, "
            f"aur khana khane ke baad {lead_med} zaroor le lijiye."
        )

    final_script = st.text_area("Fridge Door Spoken Nudge:", value=auto_nudge, height=95)

    if st.button("🔊 Play Kitchen Voice Nudge", type="primary", use_container_width=True):
        if sarvam_key:
            with st.spinner("Synthesizing Sarvam Bulbul v4 Flash voice..."):
                try:
                    audio_wav = sarvam_text_to_speech(final_script, lang_code, speaker_id, sarvam_key)
                    st.audio(audio_wav, format="audio/wav", autoplay=True)
                    st.success("Spoken via Sarvam Bulbul v4 Flash!")
                except Exception as exc:
                    st.error(f"Sarvam TTS Error: {exc}")
        else:
            st.info("No Sarvam API key entered — playing browser speech preview.")
            clean_js = final_script.replace('"', '\\"').replace("\n", " ")
            st.components.v1.html(
                f"""
                <script>
                    const utter = new SpeechSynthesisUtterance("{clean_js}");
                    utter.lang = "{lang_code}";
                    window.speechSynthesis.cancel();
                    window.speechSynthesis.speak(utter);
                </script>
                """,
                height=0,
            )

    st.markdown("---")
    st.markdown("**📲 7:30 AM Family / Flat WhatsApp Digest**")
    use_today_str = ", ".join(urgent_items) if urgent_items else "No items expiring today"
    med_status_str = ", ".join(pending_med_names) if pending_med_names else "All doses completed ✅"
    cold_chain_str = (
        f"🚨 Power-cut risk ({fridge_temp}°C for {warm_minutes}m) — check insulin & milk!"
        if (fridge_temp > 8.0 and warm_minutes >= 90)
        else f"✅ Normal ({fridge_temp}°C)"
    )

    digest_msg = (
        f"*❄️ FrostMind Daily Digest ({mode})*\n"
        f"• *Cook / Use Today:* {use_today_str}\n"
        f"• *Pending Medications:* {med_status_str}\n"
        f"• *Cold-Chain Status:* {cold_chain_str}"
    )
    st.code(digest_msg, language="markdown")