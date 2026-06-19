# ⚓ Harbour View Gospel Chapel — Website

A modern, animated church website with an easy content manager so a non-technical
volunteer can keep it up to date. Built with **HTML, CSS, three.js, GSAP** on the
front end and a small **Flask** backend.

It also links to **HVGC LINEUP** — the AV team scheduling app (separate project).

---

## ✨ What's on the site
- **Animated hero** — a three.js "harbour of light" particle scene with GSAP
  entrance and scroll animations. Christian *anchor / hope* theme (Hebrews 6:19).
- **Weekly live stream** — embeds whatever YouTube link the editor pastes in.
- **Welcome, sermons/presentations, news/blog, photo gallery, visit & contact.**
- A **Volunteer Portal** button (in the menu and footer) that links to HVGC LINEUP.
- A **browsable photo gallery** (with a lightbox) and a **sermons archive** page.
- Fully responsive, and **works even if JavaScript or the CDN is blocked**
  (animations are progressive enhancement only).

## 💾 Database
Runs on **Postgres** (set `DATABASE_URL`) or **SQLite** (default, local dev) from
the same code. **Uploaded sermon files and photos are stored in the database**
(not on disk), so they persist across deploys on hosts with an ephemeral
filesystem — no separate disk required. The `render.yaml` provisions Postgres
automatically.

## 🛠️ The content manager (no coding needed)
Sign in at **`/admin`** and you get a friendly dashboard of plain-English tasks:

| Task | What it does |
|------|--------------|
| 📺 Set this week's live stream | Paste a YouTube link → it appears on the homepage |
| 📝 Write & manage news | Add/edit/delete blog posts (with a picture) |
| 🖼️ Add photos & graphics | Upload images to the gallery |
| 📖 Share sermons & presentations | Add a slide link or upload a PDF/PowerPoint |
| ⚙️ Edit homepage text | Welcome message, service times, contact details, the LINEUP link |
| 🔑 Change password | Update the editor's login |

Everything updates the live site instantly. No HTML required.

---

## 🚀 Run locally
```bash
pip install -r requirements.txt
python3 app.py
```
- Website: **http://localhost:5000**
- Manager: **http://localhost:5000/admin**  (sign in: `admin` / `admin123`, then change the password)

## ☁️ Deploy (Render.com)
A [`render.yaml`](render.yaml) Blueprint is included. New → Blueprint → select the
repo → Apply. Set the **HVGC LINEUP link** under *Edit homepage text* once it's live.

> On the free plan the database and uploaded files reset on each deploy. To keep
> them, enable the disk + `DATABASE_PATH` (see `render.yaml`) on a paid plan.

## 🔗 Connecting to HVGC LINEUP
In the manager → **Edit homepage text** → set **"HVGC LINEUP web address"** to your
deployed LINEUP URL (e.g. `https://hvgc-lineup.onrender.com`). The menu/footer
"Volunteer Portal" links there.

## 🗂️ Structure
```
app.py                # Flask routes (public site + /admin manager)
db.py                 # SQLite schema + defaults + seed
templates/public/     # homepage, blog, post
templates/admin/      # the content manager
static/css/           # style.css (site), admin.css (manager)
static/js/main.js     # three.js hero + GSAP animations
static/uploads/       # uploaded images & files (git-ignored)
```
