# PROJECT_SPEC.md — FrostMind MVP Specification

## 1. What is this?
FrostMind is an open-source, edge-AI smart refrigerator assistant that logs grocery items via receipt/barcode text parsing and triggers ambient meal-time voice/display alerts for expiring food and prescription medication schedules.

## 2. Who uses it?
Urban working professionals and multi-generational households managing home cooking and daily chronic health routines (e.g., daily post-meal prescriptions).

## 3. What must it do? (Functional Requirements)
- [REQ-1] Capture raw OCR text strings or barcode inputs via text/image upload.
- [REQ-2] Parse raw text using Python regex and fuzzy matching (`difflib`) to extract clean item names.
- [REQ-3] Automatically calculate expiry dates based on a local SQLite default shelf-life table (e.g., Milk = 7 days, Bread = 4 days).
- [REQ-4] Store items in a persistent local SQLite database (`inventory.db`).
- [REQ-5] Simulate a "Fridge Door Open" event during designated meal windows (Breakfast, Lunch, Dinner).
- [REQ-6] Display a real-time ambient prompt summarizing expiring items and meal-dependent med reminders.

## 4. What does it NOT do? (Explicit Scope Exclusions)
- [EXC-1] NO cloud user authentication or multi-tenant user accounts (strictly single-household local DB).
- [EXC-2] NO complex multi-room object tracking (keys, glasses, or non-kitchen items).
- [EXC-3] NO real-time video stream micro-decay visual modeling (relies strictly on logging + database timers).
- [EXC-4] NO external payment gateways, e-commerce auto-reordering, or third-party cloud API dependencies.

## 5. What data does it use?
- Local `inventory.db` (SQLite):
  - `inventory` table: (id, item_name, date_added, expiry_date)
  - `medications` table: (id, med_name, meal_window)
- Data Sensitivity: Local household habits & basic prescription notes (MUST remain 100% offline).

## 6. What are the constraints?
- Time: Built during a 30-hour hackathon sprint.
- Stack: Python 3.11, Streamlit, SQLite, OpenCV/pytesseract.
- Execution: Must execute completely offline on a basic mid-range laptop without GPU acceleration.

## 7. What does DONE mean?
A user can input receipt text, view the populated inventory table with auto-assigned expiration dates, click "Simulate Door Open (Breakfast)", and receive an ambient prompt showing expiring food plus the breakfast medication alert.

## 8. What is still unknown?
- What is the exact OCR character error rate under poor webcam lighting for handwritten vs. thermal receipts?
- Will non-technical household members find a Streamlit web interface intuitive on a mounted screen?