"""SmartCare - AI-Based Hospital Appointment and Patient Support System.

Run:  python app.py   then open http://127.0.0.1:5000
"""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = Path(os.environ.get("HOSPITAL_DB") or Path(__file__).with_name("hospital.db"))
SLOT_MINUTES = 30
BOOKING_WINDOW_DAYS = 60
# Change these to the real hospital details.
HOSPITAL = {
    "name": "SmartCare Hospital",
    "phone": "+968 2400 0000",
    "email": "info@smartcare.test",
    "address": "Muscat, Sultanate of Oman",
    "hours": "Clinics: Sunday to Thursday, 8:00 AM - 2:00 PM.\nEmergency department: open 24/7.",
    "emergency": "9999",
}
DAY_NAMES = [("6", "Sun"), ("0", "Mon"), ("1", "Tue"), ("2", "Wed"), ("3", "Thu"), ("4", "Fri"), ("5", "Sat")]
STATUSES = ("booked", "completed", "cancelled", "no-show")

app = Flask(__name__)
app.config.update(
    # ponytail: random key per run logs everyone out on restart; set SECRET_KEY env var for a stable one.
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_SAMESITE="Lax",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('patient','doctor','admin')),
    department TEXT,
    work_days TEXT NOT NULL DEFAULT '6,0,1,2,3',
    start_time TEXT NOT NULL DEFAULT '08:00',
    end_time TEXT NOT NULL DEFAULT '14:00',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS appointments(
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES users(id),
    doctor_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    time TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'booked' CHECK(status IN ('booked','completed','cancelled','no-show')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- A doctor slot can only hold one active booking.
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot ON appointments(doctor_id, day, time) WHERE status='booked';
"""

# Demo accounts (also listed in README.md).
DEMO_DOCTORS = [
    ("Dr. Ahmed Al-Balushi", "ahmed", "General Medicine"),
    ("Dr. Fatma Al-Harthy", "fatma", "Pediatrics"),
    ("Dr. Salim Al-Rawahi", "salim", "Cardiology"),
    ("Dr. Maryam Al-Hinai", "maryam", "Dermatology"),
    ("Dr. Khalid Al-Siyabi", "khalid", "Orthopedics"),
    ("Dr. Aisha Al-Kindi", "aisha", "Dental"),
    ("Dr. Yousuf Al-Lawati", "yousuf", "Ophthalmology"),
]


# ---------------------------------------------------------------- database
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def q(sql, args=(), one=False):
    rows = db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT 1 FROM users").fetchone():
            return
        add = "INSERT INTO users(name,email,phone,password,role,department) VALUES(?,?,?,?,?,?)"
        conn.execute(add, ("Hospital Admin", "admin@smartcare.test", "", generate_password_hash("admin123"), "admin", None))
        for name, key, dept in DEMO_DOCTORS:
            conn.execute(add, (name, f"{key}@smartcare.test", "", generate_password_hash("doctor123"), "doctor", dept))
        pid = conn.execute(add, ("Demo Patient", "patient@smartcare.test", "+968 9000 0000",
                                 generate_password_hash("patient123"), "patient", None)).lastrowid
        # One past visit and one upcoming visit so the dashboards are not empty.
        past, soon = date.today() - timedelta(days=7), date.today() + timedelta(days=1)
        conn.execute("INSERT INTO appointments(patient_id,doctor_id,day,time,reason,status) VALUES(?,2,?,'09:00','Annual check-up','completed')",
                     (pid, past.isoformat()))
        conn.execute("INSERT INTO appointments(patient_id,doctor_id,day,time,reason) VALUES(?,7,?,'10:30','Tooth pain')",
                     (pid, soon.isoformat()))


# ---------------------------------------------------------------- scheduling
def doctors():
    return q("SELECT * FROM users WHERE role='doctor' ORDER BY department, name")


def free_slots(doctor, day):
    """Open slots for a doctor on a date, from their schedule minus active bookings."""
    if str(day.weekday()) not in doctor["work_days"].split(","):
        return []
    taken = {r["time"] for r in q("SELECT time FROM appointments WHERE doctor_id=? AND day=? AND status='booked'",
                                  (doctor["id"], day.isoformat()))}
    t = datetime.combine(day, time.fromisoformat(doctor["start_time"]))
    end = datetime.combine(day, time.fromisoformat(doctor["end_time"]))
    now, slots = datetime.now(), []
    while t + timedelta(minutes=SLOT_MINUTES) <= end:
        if t > now and t.strftime("%H:%M") not in taken:
            slots.append(t.strftime("%H:%M"))
        t += timedelta(minutes=SLOT_MINUTES)
    return slots


def earliest_slots(docs, n=3, days=14):
    """The n earliest open slots across the given doctors."""
    found = []
    for i in range(days):
        d = date.today() + timedelta(days=i)
        for doc in docs:
            found += [(d, s, doc) for s in free_slots(doc, d)]
        if len(found) >= n:
            break
    return sorted(found, key=lambda x: (x[0], x[1]))[:n]


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@app.template_filter("nice_date")
def nice_date(value):
    d = parse_day(value)
    return d.strftime("%a %d %b %Y") if d else value


# ---------------------------------------------------------------- auth
def login_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "uid" not in session:
                return redirect(url_for("login", next=request.full_path))
            if roles and session["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco


def start_session(user):
    session.clear()
    session.update(uid=user["id"], name=user["name"], role=user["role"])


@app.context_processor
def inject_globals():
    return {"hospital": HOSPITAL, "day_names": DAY_NAMES, "statuses": STATUSES}


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("name", "email", "phone", "password")}
        if not f["name"] or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", f["email"]):
            flash("Please enter your name and a valid email.", "error")
        elif len(f["password"]) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            try:
                uid = db().execute("INSERT INTO users(name,email,phone,password,role) VALUES(?,?,?,?,'patient')",
                                   (f["name"], f["email"], f["phone"], generate_password_hash(f["password"]))).lastrowid
                db().commit()
            except sqlite3.IntegrityError:
                flash("An account with this email already exists.", "error")
            else:
                start_session(q("SELECT * FROM users WHERE id=?", (uid,), one=True))
                flash("Welcome! Your account has been created.", "ok")
                return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.values.get("next", "")
    if request.method == "POST":
        user = q("SELECT * FROM users WHERE email=?", (request.form.get("email", "").strip(),), one=True)
        if user and check_password_hash(user["password"], request.form.get("password", "")):
            start_session(user)
            safe = nxt.startswith("/") and not nxt.startswith(("//", "/\\"))
            return redirect(nxt if safe else url_for("dashboard"))
        flash("Wrong email or password.", "error")
    return render_template("auth.html", mode="login", next=nxt)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    return redirect(url_for({"patient": "patient_home", "doctor": "doctor_home", "admin": "admin_home"}[session["role"]]))


# ---------------------------------------------------------------- public pages
@app.route("/")
def index():
    by_dept = {}
    for d in doctors():
        by_dept.setdefault(d["department"], []).append(d)
    return render_template("index.html", by_dept=by_dept)


@app.route("/about")
def about():
    return render_template("about.html")


# ---------------------------------------------------------------- patient
@app.route("/patient")
@login_required("patient")
def patient_home():
    rows = q("""SELECT a.*, d.name doctor, d.department FROM appointments a JOIN users d ON d.id=a.doctor_id
                WHERE a.patient_id=? ORDER BY a.day, a.time""", (session["uid"],))
    today = date.today().isoformat()
    upcoming = [r for r in rows if r["status"] == "booked" and r["day"] >= today]
    history = [r for r in reversed(rows) if r["id"] not in {u["id"] for u in upcoming}]
    soon = (date.today() + timedelta(days=2)).isoformat()
    reminders = [r for r in upcoming if r["day"] <= soon]
    return render_template("patient.html", upcoming=upcoming, history=history, reminders=reminders)


@app.route("/book", methods=["GET", "POST"])
@login_required("patient")
def book():
    resched = None
    rid = request.values.get("reschedule", type=int)
    if rid:
        resched = q("""SELECT a.*, d.name doctor FROM appointments a JOIN users d ON d.id=a.doctor_id
                       WHERE a.id=? AND a.patient_id=? AND a.status='booked'""", (rid, session["uid"]), one=True)
        if not resched:
            abort(404)

    if request.method == "POST":
        doc = q("SELECT * FROM users WHERE id=? AND role='doctor'", (request.form.get("doctor", type=int),), one=True)
        day, slot = parse_day(request.form.get("day")), request.form.get("time", "")
        too_far = day and day > date.today() + timedelta(days=BOOKING_WINDOW_DAYS)
        if resched and doc and doc["id"] != resched["doctor_id"]:
            doc = None  # rescheduling keeps the same doctor
        if not doc or not day or too_far or slot not in free_slots(doc, day):
            flash("That time is not available. Please choose another slot.", "error")
        else:
            try:
                if resched:
                    db().execute("UPDATE appointments SET day=?, time=? WHERE id=?", (day.isoformat(), slot, resched["id"]))
                else:
                    db().execute("INSERT INTO appointments(patient_id,doctor_id,day,time,reason) VALUES(?,?,?,?,?)",
                                 (session["uid"], doc["id"], day.isoformat(), slot, request.form.get("reason", "").strip()[:500]))
                db().commit()
            except sqlite3.IntegrityError:
                flash("Someone just booked that slot. Please pick another one.", "error")
            else:
                flash(f"Appointment {'rescheduled' if resched else 'booked'} with {doc['name']} on "
                      f"{nice_date(day.isoformat())} at {slot}.", "ok")
                return redirect(url_for("patient_home"))

    return render_template("book.html", doctors=doctors(), resched=resched,
                           pick={k: request.values.get(k, "") for k in ("doctor", "day", "time")},
                           today=date.today().isoformat(),
                           max_day=(date.today() + timedelta(days=BOOKING_WINDOW_DAYS)).isoformat())


@app.route("/api/slots")
def api_slots():
    doc = q("SELECT * FROM users WHERE id=? AND role='doctor'", (request.args.get("doctor", type=int),), one=True)
    day = parse_day(request.args.get("day"))
    if not doc or not day:
        return jsonify(slots=[])
    return jsonify(slots=free_slots(doc, day), works=str(day.weekday()) in doc["work_days"].split(","))


@app.post("/appointments/<int:aid>/status")
@login_required()
def set_status(aid):
    appt = q("SELECT * FROM appointments WHERE id=?", (aid,), one=True)
    status = request.form.get("status")
    role, uid = session["role"], session["uid"]
    allowed = appt and status in STATUSES and (
        role == "admin"
        or (role == "doctor" and appt["doctor_id"] == uid)
        or (role == "patient" and appt["patient_id"] == uid and appt["status"] == "booked" and status == "cancelled"))
    if not allowed:
        abort(403)
    try:
        db().execute("UPDATE appointments SET status=? WHERE id=?", (status, aid))
        db().commit()
        flash(f"Appointment #{aid} marked as {status}.", "ok")
    except sqlite3.IntegrityError:
        flash("That slot has been re-booked by another patient, so it cannot be restored.", "error")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------- doctor
@app.route("/doctor")
@login_required("doctor")
def doctor_home():
    rows = q("""SELECT a.*, p.name patient, p.phone FROM appointments a JOIN users p ON p.id=a.patient_id
                WHERE a.doctor_id=? ORDER BY a.day, a.time""", (session["uid"],))
    today = date.today().isoformat()
    return render_template("doctor.html",
                           me=q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True),
                           today_rows=[r for r in rows if r["day"] == today],
                           upcoming=[r for r in rows if r["day"] > today and r["status"] == "booked"],
                           past=[r for r in reversed(rows) if r["day"] < today][:30])


# ---------------------------------------------------------------- admin
@app.route("/admin")
@login_required("admin")
def admin_home():
    status, day = request.args.get("status", ""), request.args.get("day", "")
    sql = """SELECT a.*, p.name patient, d.name doctor, d.department FROM appointments a
             JOIN users p ON p.id=a.patient_id JOIN users d ON d.id=a.doctor_id WHERE 1=1"""
    args = []
    if status in STATUSES:
        sql += " AND a.status=?"
        args.append(status)
    if parse_day(day):
        sql += " AND a.day=?"
        args.append(day)
    appts = q(sql + " ORDER BY a.day DESC, a.time DESC LIMIT 300", args)
    patients = q("""SELECT u.*, COUNT(a.id) visits FROM users u LEFT JOIN appointments a ON a.patient_id=u.id
                    WHERE u.role='patient' GROUP BY u.id ORDER BY u.name""")
    return render_template("admin.html", appts=appts, patients=patients, doctors=doctors(),
                           f={"status": status, "day": day})


@app.post("/admin/doctors/<int:did>")
@login_required("admin")
def admin_schedule(did):
    days = [d for d in request.form.getlist("days") if d in {k for k, _ in DAY_NAMES}]
    start, end = request.form.get("start_time", ""), request.form.get("end_time", "")
    if not re.fullmatch(r"\d\d:\d\d", start) or not re.fullmatch(r"\d\d:\d\d", end) or start >= end:
        flash("Start time must be before end time.", "error")
    else:
        db().execute("UPDATE users SET work_days=?, start_time=?, end_time=?, department=? WHERE id=? AND role='doctor'",
                     (",".join(days), start, end, request.form.get("department", "").strip() or "General Medicine", did))
        db().commit()
        flash("Doctor schedule updated.", "ok")
    return redirect(url_for("admin_home") + "#doctors")


@app.post("/admin/doctors")
@login_required("admin")
def admin_add_doctor():
    f = {k: request.form.get(k, "").strip() for k in ("name", "email", "department", "password")}
    if not all(f.values()) or len(f["password"]) < 6:
        flash("Fill in all doctor fields (password at least 6 characters).", "error")
    else:
        try:
            db().execute("INSERT INTO users(name,email,password,role,department) VALUES(?,?,?,'doctor',?)",
                         (f["name"], f["email"], generate_password_hash(f["password"]), f["department"]))
            db().commit()
            flash(f"{f['name']} added.", "ok")
        except sqlite3.IntegrityError:
            flash("That email is already used.", "error")
    return redirect(url_for("admin_home") + "#doctors")


@app.route("/admin/reports")
@login_required("admin")
def reports():
    counts = "COUNT(a.id) total, " + ", ".join(f"IFNULL(SUM(a.status='{s}'),0) {s.replace('-', '')}" for s in STATUSES)
    totals = q(f"SELECT {counts} FROM appointments a", one=True)
    by_dept = q(f"""SELECT d.department label, {counts} FROM users d LEFT JOIN appointments a ON a.doctor_id=d.id
                    WHERE d.role='doctor' GROUP BY d.department ORDER BY total DESC""")
    by_doc = q(f"""SELECT d.name label, d.department, {counts} FROM users d LEFT JOIN appointments a ON a.doctor_id=d.id
                   WHERE d.role='doctor' GROUP BY d.id ORDER BY total DESC""")
    week = [(date.today() + timedelta(days=i)).isoformat() for i in range(7)]
    load = {r["day"]: r["n"] for r in q("SELECT day, COUNT(*) n FROM appointments WHERE status='booked' AND day BETWEEN ? AND ? GROUP BY day",
                                       (week[0], week[-1]))}
    people = q("SELECT SUM(role='patient') patients, SUM(role='doctor') doctors FROM users", one=True)
    return render_template("reports.html", totals=totals, by_dept=by_dept, by_doc=by_doc, people=people,
                           week=[(d, load.get(d, 0)) for d in week], generated=datetime.now().strftime("%d %b %Y %H:%M"))


# ---------------------------------------------------------------- AI assistant
SYMPTOMS = {
    "General Medicine": "fever cough cold flu headache tired fatigue checkup sick stomach vomiting diarrhea general",
    "Pediatrics": "child children baby kid kids son daughter infant newborn pediatric pediatrics",
    "Cardiology": "heart chest palpitation palpitations cardiac cardiology pressure hypertension",
    "Dermatology": "skin rash acne itch itching itchy hair eczema allergy dermatology",
    "Orthopedics": "bone bones joint joints back knee shoulder fracture neck sprain orthopedic orthopedics",
    "Dental": "tooth teeth toothache dental dentist gum gums",
    "Ophthalmology": "eye eyes vision sight blurry glasses ophthalmology",
}
EMERGENCY = set("emergency urgent bleeding unconscious fainted faint accident stroke seizure suicide overdose".split())


def tokens(text):
    words = set(re.findall(r"[a-z']+", text.lower()))
    return words | {w[:-1] for w in words if w.endswith("s")}  # crude plural stemming


def bot_reply(text):
    """Rule-based NLP: keyword intent matching + symptom-to-department mapping + live slot lookup."""
    words, low = tokens(text), text.lower()
    has = lambda vocab: bool(words & set(vocab.split()))

    if words & EMERGENCY or "can't breathe" in low or "cannot breathe" in low:
        return {"reply": f"This sounds urgent. Please call {HOSPITAL['emergency']} or go to the nearest emergency department now. "
                         "Our emergency department is open 24/7."}
    if has("cancel reschedule postpone change move"):
        return {"reply": "To cancel or reschedule: log in, open My Appointments, then press Cancel or Reschedule next to the visit. "
                         "Rescheduling keeps the same doctor and lets you pick a new free time."}
    if has("my mine") and has("appointment booking visit"):
        if session.get("role") != "patient":
            return {"reply": "Please log in as a patient and I will show your upcoming appointments."}
        rows = q("""SELECT a.day, a.time, d.name FROM appointments a JOIN users d ON d.id=a.doctor_id
                    WHERE a.patient_id=? AND a.status='booked' AND a.day>=? ORDER BY a.day, a.time""",
                 (session["uid"], date.today().isoformat()))
        if not rows:
            return {"reply": "You have no upcoming appointments. Would you like me to find a free slot?"}
        return {"reply": "Your upcoming appointments:\n" + "\n".join(f"- {nice_date(r['day'])} at {r['time']} with {r['name']}" for r in rows)}

    docs = doctors()
    named = [d for d in docs if any(part in words for part in d["name"].lower().replace("-", " ").split()[1:] if len(part) > 3)]
    dept = max(SYMPTOMS, key=lambda k: len(words & set(SYMPTOMS[k].split())))
    dept = dept if words & set(SYMPTOMS[dept].split()) else None
    if named or dept or has("book booking available slot free earliest soon appointment"):
        pool = named or [d for d in docs if d["department"] == dept] or docs
        slots = earliest_slots(pool)
        if named:
            intro = f"Here are the earliest free times with {named[0]['name']}:"
        elif dept:
            intro = (f"Based on what you described, the {dept} department is the right place to start "
                     "(this is guidance, not a diagnosis). Earliest free times:")
        else:
            intro = "Here are the earliest free appointments across the hospital:"
        if not slots:
            return {"reply": intro + "\nNo free slots in the next two weeks, sorry. Please call us at " + HOSPITAL["phone"]}
        return {"reply": intro, "slots": [
            {"doctor": doc["name"], "label": f"{doc['department']} - {nice_date(d.isoformat())} {s}",
             "url": url_for("book", doctor=doc["id"], day=d.isoformat(), time=s)} for d, s, doc in slots]}

    if has("hour open opening close closing timing time when working"):
        return {"reply": HOSPITAL["hours"]}
    if has("contact phone call number address location where email find"):
        return {"reply": f"Phone: {HOSPITAL['phone']}\nEmail: {HOSPITAL['email']}\nAddress: {HOSPITAL['address']}"}
    if has("department service specialty specialties clinic doctor list"):
        lines = [f"- {d['department']}: {d['name']}" for d in docs]
        return {"reply": "Our departments and doctors:\n" + "\n".join(lines)}
    if has("hi hello hey salam salaam marhaba morning evening"):
        return {"reply": "Hello! I'm the SmartCare assistant. Tell me your symptoms or a department and I'll find you a free appointment."}
    if has("thank thanks thx shukran"):
        return {"reply": "You're welcome! Get well soon."}
    return {"reply": "I can help you:\n- find a free appointment (e.g. \"I have a toothache\")\n- show your appointments\n"
                     "- explain how to cancel or reschedule\n- give opening hours and contact details"}


@app.post("/chat")
def chat():
    message = ((request.get_json(silent=True) or {}).get("message") or "").strip()[:500]
    if not message:
        return jsonify(reply="Please type a question.")
    return jsonify(bot_reply(message))


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
