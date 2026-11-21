# FrostMind OS update — multi-member household support

## What changed
- Added a Household Members workspace to add and remove named family members or flatmates.
- Grocery receipt ownership and pantry filters now use the shared household label plus the members stored in SQLite.
- Leftover Dabba entries can be assigned to a named member.
- Medicine reminders now have a member assignment. The same medicine and meal can be scheduled separately for different people.
- Fridge-door medication reminders include the assigned member's name.
- Removing a member safely reassigns their groceries, leftovers and medicine schedules to the shared household instead of deleting those records.
- Existing databases are migrated to the member-aware medication tables when the app starts.

## Files revised
- `app.py` — Household Members UI, dynamic ownership choices, medicine assignment.
- `db.py` — household member storage, member-aware medication schedules, migration and reassignment.
- `ui.py` — member names on the fridge-door reminder.
- `tests/test_core.py` — multi-member and reassignment regression tests.

## Run
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app uses the existing local SQLite database. Back up `frostmind.db` before replacing an older project folder. The database migration preserves existing inventory and migrates existing medicine reminders to the shared `Family` owner.
