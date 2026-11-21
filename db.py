"""SQLite storage. The app creates one FridgeDB per browser session."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pandas as pd

DEFAULT_MEDS = [("Metformin 500mg", "Breakfast"), ("Amlodipine 5mg", "Dinner")]
FLATMATES = ("Shared", "Member 1", "Member 2")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    price REAL NOT NULL DEFAULT 0,
    date_added TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT NOT NULL DEFAULT 'Shared'
);
CREATE TABLE IF NOT EXISTS receipts (fingerprint TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    med_name TEXT NOT NULL,
    meal_window TEXT NOT NULL,
    UNIQUE (med_name, meal_window)
);
CREATE TABLE IF NOT EXISTS med_log (
    med_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    log_date TEXT NOT NULL,
    PRIMARY KEY (med_id, log_date)
);
"""


class FridgeDB:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(_SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(inventory)")}
            if "owner" not in cols:
                c.execute("ALTER TABLE inventory ADD COLUMN owner TEXT NOT NULL DEFAULT 'Shared'")
            if c.execute("PRAGMA user_version").fetchone()[0] == 0:
                self._seed(c)
                c.execute("PRAGMA user_version = 1")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _seed(c):
        c.executemany("INSERT OR IGNORE INTO medications (med_name, meal_window) "
                      "VALUES (?, ?)", DEFAULT_MEDS)

    # ---- inventory -------------------------------------------------------
    def add_receipt(self, fingerprint: str, rows: list[tuple], owner: str = "Shared"):
        """Insert rows. Returns (inserted, merged), or None if already logged."""
        with self._conn() as c:
            try:
                c.execute("INSERT INTO receipts (fingerprint) VALUES (?)", (fingerprint,))
            except sqlite3.IntegrityError:
                return None
            inserted = merged = 0
            for name, qty, price, added, expiry in rows:
                hit = c.execute(
                    "SELECT id FROM inventory WHERE item_name=? AND expiry_date=? "
                    "AND owner=? AND status='active'", (name, expiry, owner)).fetchone()
                if hit:
                    c.execute("UPDATE inventory SET quantity = quantity + ?, "
                              "price = price + ? WHERE id = ?", (qty, price, hit["id"]))
                    merged += 1
                else:
                    c.execute("INSERT INTO inventory (item_name, quantity, price, "
                              "date_added, expiry_date, owner) VALUES (?,?,?,?,?,?)",
                              (name, qty, price, added, expiry, owner))
                    inserted += 1
            return inserted, merged

    def inventory(self, status: str = "active", owner: str | None = None) -> pd.DataFrame:
        with self._conn() as c:
            c.row_factory = None
            if owner and owner != "All":
                return pd.read_sql_query(
                    "SELECT id, item_name, quantity, price, date_added, expiry_date, status, owner "
                    "FROM inventory WHERE status = ? AND owner = ? ORDER BY expiry_date, item_name",
                    c, params=(status, owner))
            return pd.read_sql_query(
                "SELECT id, item_name, quantity, price, date_added, expiry_date, status, owner "
                "FROM inventory WHERE status = ? ORDER BY expiry_date, item_name",
                c, params=(status,))

    def set_status(self, item_id: int, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE inventory SET status = ? WHERE id = ?", (status, item_id))

    def money_stats(self, owner: str | None = None) -> dict:
        out = {"consumed_qty": 0, "wasted_qty": 0,
               "consumed_value": 0.0, "wasted_value": 0.0}
        with self._conn() as c:
            if owner and owner != "All":
                rows = c.execute("SELECT status, SUM(quantity) q, SUM(price) p "
                                 "FROM inventory WHERE owner = ? GROUP BY status", (owner,))
            else:
                rows = c.execute("SELECT status, SUM(quantity) q, SUM(price) p "
                                 "FROM inventory GROUP BY status")
            for r in rows:
                if r["status"] in ("consumed", "wasted"):
                    out[f"{r['status']}_qty"] = r["q"] or 0
                    out[f"{r['status']}_value"] = r["p"] or 0.0
        return out

    # ---- medication ------------------------------------------------------
    def meds(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id, med_name, meal_window FROM medications ORDER BY id")]

    def add_med(self, name: str, meal: str) -> bool:
        name = " ".join(name.split())[:60]
        if not name:
            return False
        try:
            with self._conn() as c:
                c.execute("INSERT INTO medications (med_name, meal_window) VALUES (?, ?)",
                          (name, meal))
        except sqlite3.IntegrityError:
            return False
        return True

    def delete_med(self, med_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM medications WHERE id = ?", (med_id,))

    def log_dose(self, med_id: int, day_iso: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO med_log (med_id, log_date) VALUES (?, ?)",
                      (med_id, day_iso))

    def doses_taken(self, day_iso: str) -> set[int]:
        with self._conn() as c:
            return {r["med_id"] for r in c.execute(
                "SELECT med_id FROM med_log WHERE log_date = ?", (day_iso,))}

    # ---- housekeeping ----------------------------------------------------
    def reset(self) -> None:
        with self._conn() as c:
            for table in ("med_log", "inventory", "receipts", "medications"):
                c.execute(f"DELETE FROM {table}")
            self._seed(c)