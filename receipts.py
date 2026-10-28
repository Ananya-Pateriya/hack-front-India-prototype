"""Receipt parsing: noisy OCR lines -> grocery items with qty, price, expiry."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from knowledge import ALIASES, NEGATIVE_WORDS, SHELF_LIFE_DB, STOPWORDS

FUZZY_CUTOFF = 0.80
FUZZY_MIN_LEN = 5  # short words ("rice", "salt") never fuzzy-match

_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:kg|gms|gm|g|ml|ltr|litre|liter|l|pcs|pc)\b")
_PRICE = re.compile(r"\d[\d,]*\.\d{2}")
_PRICE_STRIP = re.compile(r"(?:rs\.?|inr|mrp|₹)?\s*\d[\d,]*\.\d{2}")
_QTY_LEAD = re.compile(r"^\s*(\d{1,2})\s*[x*×]\s")
_QTY_TRAIL = re.compile(r"\bx\s*(\d{1,2})\b")

_FUZZY_KEYS = [k for k in [*SHELF_LIFE_DB, *ALIASES] if len(k) >= FUZZY_MIN_LEN]


@dataclass
class ParsedLine:
    raw: str
    qty: int
    price: float          # line total in rupees, 0 if absent
    item: str | None      # canonical key, None if skipped
    score: float
    note: str

    def expiry(self, today: dt.date) -> dt.date:
        return today + dt.timedelta(days=SHELF_LIFE_DB[self.item])


def normalise(line: str) -> tuple[int, float, list[str]]:
    """Return (quantity, price, tokens) with units, prices and noise removed."""
    text = line.lower()
    m = _QTY_LEAD.match(text) or _QTY_TRAIL.search(text)
    qty = max(1, int(m.group(1))) if m else 1
    text = _UNIT.sub(" ", text)
    prices = _PRICE.findall(text)
    price = float(prices[-1].replace(",", "")) if prices else 0.0
    text = _PRICE_STRIP.sub(" ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = [t for t in text.split() if len(t) > 1 and t not in STOPWORDS]
    return qty, price, tokens


def match_item(tokens: list[str]) -> tuple[str | None, float, str]:
    """Return (canonical item | None, confidence, human-readable note)."""
    blocked = sorted(NEGATIVE_WORDS.intersection(tokens))
    if blocked:
        return None, 0.0, f"Packaged product ({blocked[0]}), not fresh stock"
    for t in tokens:                       # 1. exact canonical name wins
        if t in SHELF_LIFE_DB:
            return t, 1.0, "Exact match"
    for t in tokens:                       # 2. regional / informal name
        if t in ALIASES:
            return ALIASES[t], 1.0, f"Alias '{t}'"
    best, best_score, best_tok = None, 0.0, ""
    for t in tokens:                       # 3. fuzzy, OCR typos only
        if len(t) < FUZZY_MIN_LEN:
            continue
        for key in _FUZZY_KEYS:
            if key[0] != t[0]:             # blocks button -> mutton
                continue
            score = SequenceMatcher(None, t, key).ratio()
            if score >= FUZZY_CUTOFF and score > best_score:
                best, best_score, best_tok = ALIASES.get(key, key), score, t
    if best:
        return best, best_score, f"Typo-tolerant match for '{best_tok}'"
    return None, 0.0, "No grocery keyword found"


def parse_receipt(raw_text: str) -> list[ParsedLine]:
    out = []
    for raw in raw_text.splitlines():
        if not raw.strip():
            continue
        qty, price, tokens = normalise(raw)
        item, score, note = match_item(tokens)
        out.append(ParsedLine(raw.strip(), qty, price, item, score, note))
    return out


def to_rows(parsed: list[ParsedLine], today: dt.date) -> list[tuple]:
    """Matched lines -> (name, qty, price, date_added, expiry) DB rows."""
    return [(p.item.capitalize(), p.qty, p.price, today.isoformat(),
             p.expiry(today).isoformat()) for p in parsed if p.item]


def fingerprint(raw_text: str, today: dt.date) -> str:
    """Stable id for a receipt, so pressing 'Parse' twice cannot double stock."""
    canon = "\n".join(" ".join(ln.split()).lower()
                      for ln in raw_text.splitlines() if ln.strip())
    return hashlib.sha256(f"{today.isoformat()}|{canon}".encode()).hexdigest()[:16]


def ocr_image(data: bytes) -> tuple[str | None, str]:
    """Photo bytes -> (text, '') or (None, reason). Never raises."""
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        return None, "OCR libraries are not installed."
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return None, "The Tesseract OCR engine is not available here."
    try:
        img = ImageOps.autocontrast(
            ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L"))
        text = pytesseract.image_to_string(img, config="--psm 6").strip()
    except Exception as exc:  # corrupt or unsupported image
        return None, f"Could not read that image ({exc})."
    return (text, "") if text else (None, "No text was found in that image.")