"""Time helpers and the pure logic that builds the ambient door card.

Nothing here imports Streamlit, so the same card can drive the web dashboard,
a terminal, or an e-ink panel on the fridge itself.
"""
from __future__ import annotations

import datetime as dt

from knowledge import EXPIRY_ALERT_DAYS, MEALS, RESCUE_IDEAS

# Cloud servers run in UTC. India has no daylight saving, so a fixed +05:30
# offset is exact and needs no timezone database (works on Windows too).
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def schedule_day(now: dt.datetime) -> dt.date:
    """The 'medication day' rolls over at 05:00, not midnight, so a 2 AM fridge
    visit still belongs to yesterday's dinner window (not a fresh day with
    breakfast already 'missed')."""
    return (now - dt.timedelta(hours=5)).date()


def meal_for_hour(hour: int) -> str:
    if 5 <= hour < 11:
        return "Breakfast"
    if 11 <= hour < 16:
        return "Lunch"
    return "Dinner"


def days_left(expiry_iso: str, today: dt.date) -> int:
    return (dt.date.fromisoformat(expiry_iso) - today).days


def food_status(days: int) -> str:
    if days < 0:
        return "expired"
    return "urgent" if days <= EXPIRY_ALERT_DAYS else "fresh"


def freshness(added_iso: str, expiry_iso: str, today: dt.date) -> float:
    """1.0 = just bought, 0.0 = expired."""
    total = max(1, (dt.date.fromisoformat(expiry_iso)
                    - dt.date.fromisoformat(added_iso)).days)
    return max(0.0, min(1.0, days_left(expiry_iso, today) / total))


def phrase_days(days: int) -> str:
    if days < 0:
        return f"expired {abs(days)} day{'s' if days != -1 else ''} ago"
    if days == 0:
        return "expires today"
    if days == 1:
        return "expires tomorrow"
    return f"expires in {days} days"


def short_days(days: int) -> str:
    if days < 0:
        return f"Expired {abs(days)}d ago"
    if days == 0:
        return "Expires today"
    if days == 1:
        return "Expires tomorrow"
    return f"{days} days left"


def build_ambient_card(db, today: dt.date, meal: str) -> dict:
    """Everything the door display needs for this moment."""
    expired, urgent = [], []
    for r in db.inventory("active").itertuples():
        d = days_left(r.expiry_date, today)
        entry = {"id": int(r.id), "name": r.item_name, "qty": int(r.quantity),
                 "price": float(r.price), "days": d,
                 "tip": RESCUE_IDEAS.get(r.item_name.lower(), "")}
        status = food_status(d)
        if status == "expired":
            expired.append(entry)
        elif status == "urgent":
            urgent.append(entry)

    taken = db.doses_taken(today.isoformat())
    meds, idx = db.meds(), MEALS.index(meal)
    return {
        "meal": meal,
        "due": [m for m in meds if m["meal_window"] == meal and m["id"] not in taken],
        "done": [m for m in meds if m["meal_window"] == meal and m["id"] in taken],
        "missed": [m for m in meds
                   if MEALS.index(m["meal_window"]) < idx and m["id"] not in taken],
        "expired": expired,
        "urgent": urgent,
        "at_risk_value": sum(e["price"] for e in expired + urgent),
    }


def ambient_text(card: dict, clock: str) -> str:
    """Plain-text rendering for terminals and small displays."""
    lines = ["=" * 46, f" DOOR OPEN  {clock}  ({card['meal']})", "=" * 46]
    for m in card["missed"]:
        lines.append(f" !! MISSED earlier: {m['med_name']} ({m['meal_window']})")
    for m in card["due"]:
        lines.append(f" PILL  Take {m['med_name']} with your {card['meal'].lower()}")
    for m in card["done"]:
        lines.append(f" OK    {m['med_name']} already taken")
    if not (card["due"] or card["done"] or card["missed"]):
        lines.append(f" PILL  Nothing scheduled at {card['meal'].lower()}")
    for e in card["expired"]:
        lines.append(f" BIN   {e['name']} {phrase_days(e['days'])}")
    for e in card["urgent"]:
        tip = f" - {e['tip']}" if e["tip"] else ""
        lines.append(f" USE   {e['name']} {phrase_days(e['days'])}{tip}")
    if not (card["expired"] or card["urgent"]):
        lines.append(" FOOD  Everything is fresh")
    lines.append("=" * 46)
    return "\n".join(lines)