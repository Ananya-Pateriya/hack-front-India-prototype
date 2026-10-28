"""Presentation layer: CSS and HTML builders. Pure functions, no Streamlit.

Every user-supplied string goes through esc() before it reaches HTML.
HTML is emitted on a single line because Markdown treats indented or
blank-line-separated HTML as code.
"""
from __future__ import annotations

import datetime as dt
from html import escape as esc

from engine import phrase_days, short_days
from knowledge import ITEM_EMOJI

CSS = """<style>
.block-container{padding-top:1.4rem;max-width:1200px}
#MainMenu,footer{visibility:hidden}
.stButton>button{border-radius:12px;font-weight:600}
.stTabs [data-baseweb="tab"]{font-weight:600;font-size:1rem}
[class*="st-key-fmcard"]{background:#fff;border-radius:18px;box-shadow:0 4px 14px rgba(15,23,42,.06)}
.fm-hero{background:linear-gradient(120deg,#082f49 0%,#0e7490 60%,#22d3ee 140%);border-radius:24px;padding:26px 32px;color:#fff;box-shadow:0 14px 34px rgba(8,47,73,.22);margin-bottom:18px}
.fm-hero h1{margin:0;padding:0;font-size:2.4rem;font-weight:800;letter-spacing:-.02em;color:#fff}
.fm-hero p{margin:.3rem 0 0;font-size:1.02rem;color:#d7f4fb}
.fm-chip{display:inline-block;margin:14px 8px 0 0;padding:5px 13px;border-radius:999px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);font-size:.8rem;color:#fff}
.fm-kpi{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:16px 18px;box-shadow:0 4px 14px rgba(15,23,42,.05)}
.fm-kpi .l{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#64748b}
.fm-kpi .v{font-size:1.9rem;font-weight:800;color:#0f172a;line-height:1.25}
.fm-kpi .s{font-size:.78rem;color:#94a3b8}
.fm-kpi.warn .v{color:#c2410c}.fm-kpi.good .v{color:#15803d}.fm-kpi.bad .v{color:#b91c1c}
.fm-item .top{display:flex;align-items:center}
.fm-item .em{font-size:2rem;line-height:1;margin-right:12px}
.fm-item .nm{font-weight:700;color:#0f172a;font-size:1.05rem}
.fm-item .meta{font-size:.78rem;color:#64748b}
.fm-pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:700}
.fm-pill.fresh{background:#dcfce7;color:#166534}.fm-pill.urgent{background:#ffedd5;color:#9a3412}.fm-pill.expired{background:#fee2e2;color:#991b1b}
.fm-bar{height:8px;border-radius:99px;background:#e2e8f0;overflow:hidden;margin:12px 0 6px}
.fm-bar span{display:block;height:100%;border-radius:99px}
.fm-bar .fresh{background:#22c55e}.fm-bar .urgent{background:#f59e0b}.fm-bar .expired{background:#ef4444}
.fm-empty{text-align:center;padding:38px 20px;border:2px dashed #cbd5e1;border-radius:20px;color:#64748b;background:#fff}
.fm-empty .big{font-size:2.6rem}.fm-empty b{display:block;color:#0f172a;font-size:1.1rem;margin:6px 0 2px}
.fm-amb{background:#0b1220;border:1px solid #1e293b;border-radius:26px;padding:26px 30px;color:#e2e8f0;box-shadow:0 18px 40px rgba(2,6,23,.35)}
.fm-amb-top{display:flex;justify-content:space-between;align-items:center;font-size:.8rem;letter-spacing:.14em;text-transform:uppercase;color:#7dd3fc}
.fm-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#22c55e;margin-right:8px;box-shadow:0 0 0 4px rgba(34,197,94,.22)}
.fm-amb-sec{margin-top:20px;padding-top:18px;border-top:1px solid #1e293b}
.fm-amb-h{font-size:.85rem;letter-spacing:.1em;text-transform:uppercase;color:#94a3b8;margin-bottom:10px}
.fm-med{font-size:1.5rem;font-weight:700;color:#fff;margin:6px 0}
.fm-med small{font-weight:500;color:#94a3b8;font-size:.9rem}
.fm-med.done{color:#86efac}
.fm-muted{color:#94a3b8;font-size:1.05rem}
.fm-food{padding:10px 14px;border-radius:14px;margin:8px 0;font-size:1.05rem;color:#f1f5f9}
.fm-food.bad{background:rgba(239,68,68,.16);border:1px solid rgba(239,68,68,.38)}
.fm-food.warn{background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.38)}
.fm-food.ok{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.32)}
.fm-food i{display:block;font-style:normal;font-size:.88rem;color:#cbd5e1;margin-top:3px}
.fm-miss{background:rgba(245,158,11,.14);border:1px solid rgba(245,158,11,.45);border-radius:14px;padding:10px 14px;margin-top:16px;color:#fde68a}
.fm-amb-foot{margin-top:18px;font-size:.72rem;color:#64748b}
.fm-amb.kiosk{padding:46px 56px}.fm-amb.kiosk .fm-med{font-size:2.6rem}.fm-amb.kiosk .fm-food{font-size:1.45rem}.fm-amb.kiosk .fm-amb-top{font-size:1rem}
</style>"""

KIOSK_CSS = ("<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
             "[data-testid='collapsedControl'],header{display:none !important}</style>")


def inr(value: float) -> str:
    return f"₹{value:,.0f}"


def emoji_for(name: str) -> str:
    return ITEM_EMOJI.get(name.lower(), "🛒")


def hero(clock: str, meal: str, offset: int, fridge_date: dt.date) -> str:
    demo = (f'<span class="fm-chip">⏩ Demo clock +{offset}d · {fridge_date:%d %b}</span>'
            if offset else "")
    return (
        '<div class="fm-hero"><h1>🧊 FrostMind</h1>'
        '<p>The fridge door that reminds you what to eat first and what to take with it.</p>'
        f'<span class="fm-chip">🕒 {esc(clock)}</span>'
        f'<span class="fm-chip">🍽️ {esc(meal)} window</span>'
        '<span class="fm-chip">📴 Runs offline</span>'
        '<span class="fm-chip">🔒 Data stays on the device</span>'
        f'{demo}</div>')


def kpi(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return (f'<div class="fm-kpi {tone}"><div class="l">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div><div class="s">{esc(sub)}&nbsp;</div></div>')


def item_card(name: str, qty: int, status: str, days: int, pct: float,
              added: str, expires: str, price: float) -> str:
    width = max(pct, 0.04) * 100
    cost = f" · {inr(price)}" if price else ""
    return (
        f'<div class="fm-item"><div class="top"><div class="em">{emoji_for(name)}</div>'
        f'<div><div class="nm">{esc(name)} × {qty}</div>'
        f'<div class="meta">Added {esc(added)}{cost}</div></div></div>'
        f'<div class="fm-bar"><span class="{status}" style="width:{width:.0f}%"></span></div>'
        f'<span class="fm-pill {status}">{esc(short_days(days))}</span> '
        f'<span class="meta">&nbsp;{esc(expires)}</span></div>')


def empty_state(emoji: str, title: str, sub: str) -> str:
    return (f'<div class="fm-empty"><div class="big">{emoji}</div>'
            f'<b>{esc(title)}</b>{esc(sub)}</div>')


def ambient_card(card: dict, clock: str, kiosk: bool = False) -> str:
    meal = card["meal"]
    parts = [f'<div class="fm-amb{" kiosk" if kiosk else ""}">'
             f'<div class="fm-amb-top"><span><span class="fm-dot"></span>Door open</span>'
             f'<span>{esc(clock)} · {esc(meal)}</span></div>']
    if card["missed"]:
        names = ", ".join(f"{esc(m['med_name'])} ({m['meal_window'].lower()})"
                          for m in card["missed"])
        parts.append(f'<div class="fm-miss">⏰ <b>Missed earlier today:</b> {names}</div>')

    parts.append(f'<div class="fm-amb-sec"><div class="fm-amb-h">💊 With your {esc(meal.lower())}</div>')
    for m in card["due"]:
        parts.append(f'<div class="fm-med">Take {esc(m["med_name"])}</div>')
    for m in card["done"]:
        parts.append(f'<div class="fm-med done">✓ {esc(m["med_name"])} <small>taken</small></div>')
    if not (card["due"] or card["done"]):
        parts.append(f'<div class="fm-muted">Nothing scheduled at {esc(meal.lower())}.</div>')
    parts.append("</div>")

    parts.append('<div class="fm-amb-sec"><div class="fm-amb-h">🥦 Food</div>')
    for e in card["expired"]:
        parts.append(f'<div class="fm-food bad">🗑️ <b>Throw out {esc(e["name"])}</b> · '
                     f'{esc(phrase_days(e["days"]))}</div>')
    for e in card["urgent"]:
        tip = f'<i>💡 {esc(e["tip"])}</i>' if e["tip"] else ""
        parts.append(f'<div class="fm-food warn">{emoji_for(e["name"])} <b>Use {esc(e["name"])} first</b> · '
                     f'{esc(phrase_days(e["days"]))}{tip}</div>')
    if not (card["expired"] or card["urgent"]):
        parts.append('<div class="fm-food ok">✅ Everything in the fridge is fresh.</div>')
    parts.append("</div>")
    parts.append('<div class="fm-amb-foot">Reminders only, not medical advice · '
                 'FrostMind runs offline on the fridge door</div></div>')
    return "".join(parts)