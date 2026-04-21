# ✦ Mr.Creative — AI Creative Engine

> Automate marketing content generation using Google's Pomelli + Gemini AI

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure (config.py)
Your Gemini API key is already set. Before Batch 3 (Selenium), you'll also need:
- `GOOGLE_EMAIL` — your Google account for Pomelli
- `GOOGLE_PASSWORD` — your Google password
- Chrome browser installed for Selenium

### 3. Run the App
```bash
python app.py
```
Open **http://localhost:5000** in your browser.

### 4. First Steps
1. Register an account
2. Go to **Prompt Studio** → write prompts or click **"AI Generate Prompts"**
3. Approve prompts to queue them for Pomelli
4. Create **Collections** to organize outputs
5. Create **Projects** to group work by brand/business

---

## Batch Status

| Batch | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Foundation, Auth, Database, UI |
| 2 | ✅ Complete | UI pages (Dashboard, Prompts, Collections, Projects) |
| 3 | 🔜 Next | Gemini Prompt Engine (API connected, needs testing) |
| 4 | ⏳ Pending | Selenium Bot (Pomelli automation) |
| 5 | ⏳ Pending | Download & Collection System |
| 6 | ⏳ Pending | Queue, Scheduling & Sharing |

---

## Project Structure
```
mr_creative/
├── app.py                  # Flask entry point
├── config.py               # API keys, paths, settings
├── models.py               # Database models (7 models)
├── requirements.txt        # Python dependencies
├── routes/
│   ├── auth.py             # Login, Register, Logout
│   ├── dashboard.py        # Dashboard with stats
│   ├── prompts.py          # Prompt CRUD + favorites
│   ├── collections.py      # Collection CRUD + sharing
│   ├── projects.py         # Project CRUD
│   └── api.py              # JSON API + Gemini integration
├── modules/
│   ├── gemini_engine.py    # (Batch 3) Prompt generation
│   ├── selenium_bot.py     # (Batch 4) Pomelli automation
│   ├── collection_mgr.py   # (Batch 5) Output management
│   └── queue_manager.py    # (Batch 6) Job queue
├── static/
│   ├── css/style.css       # White theme + animations
│   ├── js/app.js           # Client-side JS
│   ├── uploads/            # User-uploaded images
│   └── outputs/            # Generated outputs
├── templates/
│   ├── base.html           # App layout + sidebar
│   ├── dashboard.html      # Dashboard page
│   ├── prompts.html        # Prompt Studio
│   ├── collections.html    # Collections list
│   ├── collection_detail.html
│   ├── collection_shared.html
│   ├── projects.html       # Projects list
│   ├── project_detail.html
│   └── auth/
│       ├── login.html
│       └── register.html
└── database.db             # SQLite (auto-created)
```

## Tech Stack
- **Backend:** Python Flask, Flask-Login, Flask-SQLAlchemy
- **Database:** SQLite
- **AI:** Google Gemini Pro (prompt generation)
- **Automation:** Selenium WebDriver (Batch 4)
- **Target:** Google Pomelli (labs.google.com/pomelli)
- **Frontend:** Custom CSS (white theme, animations, shadows)
