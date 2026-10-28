"""Run with:  pip install pytest && pytest -q"""
import datetime as dt
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ui  # noqa: E402
from db import FridgeDB  # noqa: E402
from engine import (IST, ambient_text, build_ambient_card, food_status,  # noqa: E402
                    freshness, meal_for_hour, phrase_days, schedule_day)
from receipts import fingerprint, normalise, parse_receipt, to_rows  # noqa: E402

TODAY = dt.date(2026, 10, 29)


def item_of(line):
    return parse_receipt(line)[0].item


@pytest.fixture
def db(tmp_path):
    return FridgeDB(str(tmp_path / "t.db"))


# ---- parser: things that must match -------------------------------------
@pytest.mark.parametrize("line,expected", [
    ("AMUL TONED MILK 1L POUCH     MRP 66.00", "milk"),
    ("BRITANNIA BROWN BREAD 400G   MRP 45.00", "bread"),
    ("FARM FRESH EGGS TRAY OF 6    MRP 48.00", "eggs"),
    ("2x MALAI PANEER 200G         MRP 95.00", "paneer"),
    ("FRESH TAMATAR 500G           MRP 24.00", "tomatoes"),
    ("ANDA 6 PC TRAY", "eggs"),
    ("FRESH PALAK 250G", "spinach"),
    ("BUTTON MUSHROOM 200G         MRP 40.00", "mushroom"),
    ("1x BRREAD WHOLEWHEAT", "bread"),          # OCR typo
    ("PANNER 200G", "paneer"),                  # OCR typo
    ("TOMATOS 1KG", "tomatoes"),                # OCR typo
])
def test_matches(line, expected):
    assert item_of(line) == expected


# ---- parser: regressions from the audit (all were wrong before) ----------
@pytest.mark.parametrize("line", [
    "PEANUT BUTTER 340G MRP 180.00", "VANILLA ICE CREAM 500ML",
    "CADBURY MILK CHOCOLATE 50G", "MAGGI TOMATO KETCHUP 500G",
    "LAYS POTATO CHIPS 52G", "ASHIRVAAD ATTA 5KG", "INDIA GATE BASMATI RICE 5KG",
    "IDLI DOSA BATTER 1KG", "TOMATO PUREE 200G",
    "TATA SALT 1KG", "GST 5% 12.40", "CASH PAID 250.00",
])
def test_rejects_non_fresh_or_non_food(line):
    assert item_of(line) is None


def test_button_never_becomes_mutton():
    assert item_of("BUTTON 5 PCS") is None


def test_curd_alias_is_not_shadowed():
    assert item_of("CURD 400G") == "yogurt"


def test_qty_and_price():
    q, price, _ = normalise("2x MALAI PANEER 200G         MRP 190.00")
    assert (q, price) == (2, 190.0)
    assert normalise("CHICKEN 1KG MRP 1,250.00")[1] == 1250.0
    assert normalise("MILK X2 1L")[0] == 2
    assert normalise("TOMATO 0.50KG")[1] == 0.0      # a weight is not a price


def test_rows_use_shelf_life():
    rows = to_rows(parse_receipt("BREAD 400G MRP 45.00"), TODAY)
    assert rows == [("Bread", 1, 45.0, "2026-10-29", "2026-11-02")]


def test_fingerprint_ignores_spacing_and_case():
    assert fingerprint("Milk  1L\nBread", TODAY) == fingerprint("milk 1l\n\nBREAD", TODAY)
    assert fingerprint("milk", TODAY) != fingerprint("milk", TODAY + dt.timedelta(days=1))


# ---- database -------------------------------------------------------------
def test_marking_used_twice_does_not_crash(db):
    """Regression: the old UNIQUE(item, expiry, status) raised IntegrityError."""
    row = ("Milk", 1, 66.0, TODAY.isoformat(), "2026-11-05")
    for n in range(2):
        db.add_receipt(f"r{n}", [row])
        db.set_status(int(db.inventory().iloc[0]["id"]), "consumed")
    assert len(db.inventory("consumed")) == 2


def test_same_receipt_twice_is_ignored(db):
    rows = [("Milk", 1, 66.0, "2026-10-29", "2026-11-05")]
    assert db.add_receipt("abc", rows) == (1, 0)
    assert db.add_receipt("abc", rows) is None
    assert int(db.inventory().quantity.sum()) == 1


def test_new_receipt_merges_same_item_and_expiry(db):
    row = ("Milk", 1, 66.0, "2026-10-29", "2026-11-05")
    db.add_receipt("a", [row])
    assert db.add_receipt("b", [row]) == (0, 1)
    inv = db.inventory()
    assert len(inv) == 1 and inv.iloc[0].quantity == 2 and inv.iloc[0].price == 132.0


def test_money_stats(db):
    db.add_receipt("a", [("Milk", 2, 100.0, "2026-10-29", "2026-11-05"),
                         ("Bread", 1, 45.0, "2026-10-29", "2026-11-02")])
    ids = {r.item_name: int(r.id) for r in db.inventory().itertuples()}
    db.set_status(ids["Milk"], "consumed")
    db.set_status(ids["Bread"], "wasted")
    s = db.money_stats()
    assert (s["consumed_value"], s["wasted_value"], s["wasted_qty"]) == (100.0, 45.0, 1)


def test_meds_seeded_once_and_deletable(db):
    assert [m["med_name"] for m in db.meds()] == ["Metformin 500mg", "Amlodipine 5mg"]
    for m in db.meds():
        db.delete_med(m["id"])
    assert FridgeDB(db.path).meds() == []            # not re-seeded on reopen


def test_add_med_validation(db):
    assert db.add_med("  Thyronorm   50mcg ", "Breakfast") is True
    assert db.add_med("Thyronorm 50mcg", "Breakfast") is False   # duplicate
    assert db.add_med("   ", "Lunch") is False                    # empty


def test_dose_log_is_idempotent_and_cascades(db):
    mid = db.meds()[0]["id"]
    db.log_dose(mid, "2026-10-29")
    db.log_dose(mid, "2026-10-29")
    assert db.doses_taken("2026-10-29") == {mid}
    db.delete_med(mid)
    assert db.doses_taken("2026-10-29") == set()


def test_reset_restores_defaults(db):
    db.add_receipt("a", [("Milk", 1, 1.0, "2026-10-29", "2026-11-05")])
    db.reset()
    assert db.inventory().empty and len(db.meds()) == 2


def test_connections_are_closed(db):
    with db._conn() as c:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        c.execute("SELECT 1")


# ---- engine -----------------------------------------------------------------
def test_meal_windows():
    assert [meal_for_hour(h) for h in (4, 5, 10, 11, 15, 16, 23)] == \
        ["Dinner", "Breakfast", "Breakfast", "Lunch", "Lunch", "Dinner", "Dinner"]


def test_medication_day_rolls_over_at_5am_ist():
    two_am = dt.datetime(2026, 10, 30, 2, 50, tzinfo=IST)
    six_am = dt.datetime(2026, 10, 30, 6, 0, tzinfo=IST)
    assert schedule_day(two_am) == dt.date(2026, 10, 29)   # still last night
    assert schedule_day(six_am) == dt.date(2026, 10, 30)


def test_ist_is_plus_530():
    assert IST.utcoffset(None) == dt.timedelta(hours=5, minutes=30)


@pytest.mark.parametrize("d,text", [
    (-1, "expired 1 day ago"), (-3, "expired 3 days ago"), (0, "expires today"),
    (1, "expires tomorrow"), (4, "expires in 4 days")])
def test_phrase_days(d, text):
    assert phrase_days(d) == text


def test_food_status_and_freshness():
    assert [food_status(d) for d in (-1, 0, 3, 4)] == ["expired", "urgent", "urgent", "fresh"]
    assert freshness("2026-10-29", "2026-11-05", TODAY) == 1.0
    assert freshness("2026-10-29", "2026-11-05", TODAY + dt.timedelta(days=30)) == 0.0


def test_ambient_card_logic(db):
    db.add_receipt("a", [("Bread", 1, 45.0, "2026-10-29", "2026-11-02"),
                         ("Milk", 1, 66.0, "2026-10-29", "2026-11-05")])
    later = TODAY + dt.timedelta(days=5)             # bread expired, milk urgent
    card = build_ambient_card(db, later, "Dinner")
    assert [e["name"] for e in card["expired"]] == ["Bread"]
    assert [e["name"] for e in card["urgent"]] == ["Milk"]
    assert [m["med_name"] for m in card["due"]] == ["Amlodipine 5mg"]
    assert [m["med_name"] for m in card["missed"]] == ["Metformin 500mg"]
    assert card["at_risk_value"] == 111.0
    db.log_dose(card["missed"][0]["id"], later.isoformat())
    db.log_dose(card["due"][0]["id"], later.isoformat())
    card = build_ambient_card(db, later, "Dinner")
    assert card["due"] == [] and card["missed"] == [] and len(card["done"]) == 1


def test_ambient_text_mentions_everything(db):
    db.add_receipt("a", [("Bread", 1, 45.0, "2026-10-29", "2026-11-02")])
    text = ambient_text(build_ambient_card(db, TODAY + dt.timedelta(days=5), "Breakfast"), "08:00 AM")
    assert "Metformin 500mg" in text and "Bread expired 1 day ago" in text


# ---- ui -----------------------------------------------------------------------
def test_ui_escapes_user_text():
    card = {"meal": "Dinner", "due": [{"med_name": "<script>alert(1)</script>"}],
            "done": [], "missed": [], "expired": [], "urgent": []}
    html = ui.ambient_card(card, "now")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "\n" not in html                           # one line, or Markdown breaks it


def test_item_card_escapes_and_has_no_newlines():
    html = ui.item_card("<b>x</b>", 1, "fresh", 5, 0.8, "2026-10-29", "2026-11-03", 66)
    assert "<b>x</b>" not in html and "\n" not in html


# ---- whole app, driven headlessly -------------------------------------------
def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()


def _click(at, label):
    next(b for b in at.button if b.label == label).click()
    return at.run()


def test_app_boots_and_demo_flow_works():
    at = _app()
    assert not at.exception
    at = _click(at, "⚡ Load demo")
    assert not at.exception
    assert at.session_state.parse_result["kind"] == "success"
    assert len(at.session_state.parse_result["trace"]) == 9
    at = _click(at, "⚡ Load demo")                      # same receipt again
    assert at.session_state.parse_result["kind"] == "warning"
    at = _click(at, "Open the fridge door")
    assert not at.exception and at.session_state.door_open


def test_app_kiosk_view_and_taken_button():
    at = _app()
    at.session_state["view"] = "Door display"
    at = at.run()
    assert not at.exception
    taken = [b for b in at.button if b.label.startswith("✓ ")]
    if taken:
        taken[0].click()
        assert not at.run().exception