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

from translations import AR, AR_DAYS, AR_MONTHS

DB_PATH = Path(os.environ.get("HOSPITAL_DB") or Path(__file__).with_name("hospital.db"))
SLOT_MINUTES = 30
BOOKING_WINDOW_DAYS = 60
LANGUAGES = ("en", "ar")
# Change these to the real hospital details (and their Arabic versions in translations.py).
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


# ---------------------------------------------------------------- language
@app.before_request
def pick_language():
    lang = request.cookies.get("lang")
    g.lang = lang if lang in LANGUAGES else request.accept_languages.best_match(LANGUAGES) or "en"


def _(text):
    """Show UI text in the visitor's language. The English text is the key into translations.AR."""
    return AR.get(text, text) if g.get("lang") == "ar" else text


def safe_next(url, default):
    """Only follow redirects to pages on this site."""
    return url if url and url.startswith("/") and not url.startswith(("//", "/\\")) else default


@app.route("/lang/<code>")
def set_lang(code):
    resp = redirect(safe_next(request.args.get("next"), url_for("index")))
    if code in LANGUAGES:
        resp.set_cookie("lang", code, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


# ---------------------------------------------------------------- database
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
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
def nice_date(value, short=False):
    d = parse_day(value)
    if not d:
        return value
    if g.get("lang") == "ar":
        text = f"{AR_DAYS[d.weekday()]} {d.day}"
        return text if short else f"{text} {AR_MONTHS[d.month - 1]} {d.year}"
    return d.strftime("%a %d" if short else "%a %d %b %Y")


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
    return {"hospital": HOSPITAL, "day_names": DAY_NAMES, "statuses": STATUSES, "_": _, "lang": g.get("lang", "en")}


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("name", "email", "phone", "password")}
        if not f["name"] or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", f["email"]):
            flash(_("Please enter your name and a valid email."), "error")
        elif len(f["password"]) < 6:
            flash(_("Password must be at least 6 characters."), "error")
        else:
            try:
                uid = db().execute("INSERT INTO users(name,email,phone,password,role) VALUES(?,?,?,?,'patient')",
                                   (f["name"], f["email"], f["phone"], generate_password_hash(f["password"]))).lastrowid
                db().commit()
            except sqlite3.IntegrityError:
                flash(_("An account with this email already exists."), "error")
            else:
                start_session(q("SELECT * FROM users WHERE id=?", (uid,), one=True))
                flash(_("Welcome! Your account has been created."), "ok")
                return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.values.get("next", "")
    if request.method == "POST":
        user = q("SELECT * FROM users WHERE email=?", (request.form.get("email", "").strip(),), one=True)
        if user and check_password_hash(user["password"], request.form.get("password", "")):
            start_session(user)
            return redirect(safe_next(nxt, url_for("dashboard")))
        flash(_("Wrong email or password."), "error")
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
            flash(_("That time is not available. Please choose another slot."), "error")
        else:
            try:
                if resched:
                    db().execute("UPDATE appointments SET day=?, time=? WHERE id=?", (day.isoformat(), slot, resched["id"]))
                else:
                    db().execute("INSERT INTO appointments(patient_id,doctor_id,day,time,reason) VALUES(?,?,?,?,?)",
                                 (session["uid"], doc["id"], day.isoformat(), slot, request.form.get("reason", "").strip()[:500]))
                db().commit()
            except sqlite3.IntegrityError:
                flash(_("Someone just booked that slot. Please pick another one."), "error")
            else:
                msg = (_("Appointment rescheduled with {doctor} on {date} at {time}.") if resched
                       else _("Appointment booked with {doctor} on {date} at {time}."))
                flash(msg.format(doctor=_(doc["name"]), date=nice_date(day.isoformat()), time=slot), "ok")
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
        flash(_("Appointment #{id} marked as {status}.").format(id=aid, status=_(status)), "ok")
    except sqlite3.IntegrityError:
        flash(_("That slot has been re-booked by another patient, so it cannot be restored."), "error")
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
    days = [d for d in request.form.getlist("days") if d in {k for k, _n in DAY_NAMES}]
    start, end = request.form.get("start_time", ""), request.form.get("end_time", "")
    if not re.fullmatch(r"\d\d:\d\d", start) or not re.fullmatch(r"\d\d:\d\d", end) or start >= end:
        flash(_("Start time must be before end time."), "error")
    else:
        db().execute("UPDATE users SET work_days=?, start_time=?, end_time=?, department=? WHERE id=? AND role='doctor'",
                     (",".join(days), start, end, request.form.get("department", "").strip() or "General Medicine", did))
        db().commit()
        flash(_("Doctor schedule updated."), "ok")
    return redirect(url_for("admin_home") + "#doctors")


@app.post("/admin/doctors")
@login_required("admin")
def admin_add_doctor():
    f = {k: request.form.get(k, "").strip() for k in ("name", "email", "department", "password")}
    if not all(f.values()) or len(f["password"]) < 6:
        flash(_("Fill in all doctor fields (password at least 6 characters)."), "error")
    else:
        try:
            db().execute("INSERT INTO users(name,email,password,role,department) VALUES(?,?,?,'doctor',?)",
                         (f["name"], f["email"], generate_password_hash(f["password"]), f["department"]))
            db().commit()
            flash(_("{name} added.").format(name=f["name"]), "ok")
        except sqlite3.IntegrityError:
            flash(_("That email is already used."), "error")
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
                           week=[(d, load.get(d, 0)) for d in week], generated=datetime.now().strftime("%d/%m/%Y %H:%M"))


# ---------------------------------------------------------------- AI assistant
ARABIC_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
HARAKAT = re.compile("[\u064b-\u0652\u0640]")  # Arabic diacritics and tatweel
PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال")


def normalize(text):
    return HARAKAT.sub("", text.lower()).translate(ARABIC_LETTERS)


def stem(word):
    """Drop one attached Arabic article prefix (الأسنان -> اسنان)."""
    for p in PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 2:
            return word[len(p):]
    return word


def tokens(text):
    """Word forms in a message: as typed, without the article, without a leading 'و' (and), without plural -s."""
    words = set()
    for w in re.findall(r"\w+", normalize(text)):
        s = stem(w)
        words |= {w, s}
        if s.startswith("و") and len(s) > 3:
            words.add(stem(s[1:]))
        if s.endswith("s"):
            words.add(s[:-1])
    return words


def vocab(text):
    return {stem(w) for w in re.findall(r"\w+", normalize(text))}


def hits(words, terms):
    """How many terms appear. Arabic terms of 3+ letters also match the start of a word (اسناني -> اسنان)."""
    return sum(1 for t in terms if t in words or (len(t) > 2 and not t.isascii() and any(w.startswith(t) for w in words)))


SYMPTOMS = {
    "General Medicine": vocab("fever cough cold flu headache tired fatigue checkup sick stomach vomiting diarrhea general "
                              "حمى حرارة سخونة كحة سعال زكام انفلونزا صداع تعب ارهاق مغص معدة اسهال استفراغ ترجيع فحص باطنية"),
    "Pediatrics": vocab("child children baby kid kids son daughter infant newborn pediatric pediatrics "
                        "طفل أطفال طفلي ابني ولدي بنتي رضيع مولود"),
    "Cardiology": vocab("heart chest palpitation palpitations cardiac cardiology pressure hypertension قلب خفقان ضغط صدر"),
    "Dermatology": vocab("skin rash acne itch itching itchy hair eczema allergy dermatology جلد جلدية حكة طفح اكزيما حساسية تساقط"),
    "Orthopedics": vocab("bone bones joint joints back knee shoulder fracture neck sprain orthopedic orthopedics "
                         "عظم عظام مفصل مفاصل ظهري ركبة ركبتي كتف كسر كسور رقبة رقبتي التواء"),
    "Dental": vocab("tooth teeth toothache dental dentist gum gums سن أسنان ضرس ضروس لثة لثتي تسوس"),
    "Ophthalmology": vocab("eye eyes vision sight blurry glasses ophthalmology عين عيون عيني نظر رؤية نظارة نظارات"),
}
EMERGENCY = vocab("emergency urgent bleeding unconscious fainted faint accident stroke seizure suicide overdose "
                  "طوارئ طارئ طارئة نزيف ينزف إغماء مغمى حادث جلطة تشنج انتحار اختناق")
EMERGENCY_PHRASES = [normalize(p) for p in ("can't breathe", "cannot breathe", "ما أقدر أتنفس", "لا أستطيع التنفس", "مو قادر أتنفس")]
CANCEL = vocab("cancel reschedule postpone change move إلغاء الغي ألغي ألغيه كنسل تغيير اغير تأجيل")
MY_EN, APPOINTMENT_EN = vocab("my mine"), vocab("appointment booking visit")
MY_AR = vocab("مواعيدي موعدي حجوزاتي حجزي")
BOOK = vocab("book booking available slot free earliest soon appointment حجز احجز موعد مواعيد متاح فاضي أقرب دكتور طبيب")
HOURS = vocab("hour open opening close closing timing time when working دوام ساعات أوقات تفتحون تفتح يفتح مفتوح")
CONTACT = vocab("contact phone call number address location where email find رقم هاتف تلفون جوال اتصال تواصل عنوان موقع وين ايميل بريد")
DEPARTMENTS = vocab("department service specialty specialties clinic doctor list أقسام قسم تخصصات تخصص عيادات عيادة أطباء دكاترة")
GREETINGS = vocab("hi hello hey salam salaam marhaba morning evening مرحبا هلا أهلا السلام سلام صباح مساء هاي")
THANKS = vocab("thank thanks thx shukran شكرا مشكور يعطيك تسلم")


def bot_reply(text):
    """Rule-based NLP in Arabic and English: intent keywords, symptom-to-department mapping, live slot lookup."""
    words, norm = tokens(text), normalize(text)
    has = lambda terms: hits(words, terms) > 0
    ltr = lambda s: f"\u2066{s}\u2069"  # keeps phone numbers readable inside Arabic text

    if has(EMERGENCY) or any(p in norm for p in EMERGENCY_PHRASES):
        return {"reply": _("This sounds urgent. Please call {emergency} or go to the nearest emergency department now. Our emergency department is open 24/7.").format(emergency=HOSPITAL["emergency"])}
    if has(CANCEL):
        return {"reply": _("To cancel or reschedule: log in, open My appointments, then press Cancel or Reschedule next to the visit. Rescheduling keeps the same doctor and lets you pick a new free time.")}
    if (has(MY_EN) and has(APPOINTMENT_EN)) or has(MY_AR):
        if session.get("role") != "patient":
            return {"reply": _("Please log in as a patient and I will show your upcoming appointments.")}
        rows = q("""SELECT a.day, a.time, d.name FROM appointments a JOIN users d ON d.id=a.doctor_id
                    WHERE a.patient_id=? AND a.status='booked' AND a.day>=? ORDER BY a.day, a.time""",
                 (session["uid"], date.today().isoformat()))
        if not rows:
            return {"reply": _("You have no upcoming appointments. Would you like me to find a free slot?")}
        line = _("- {date} at {time} with {doctor}")
        return {"reply": _("Your upcoming appointments:") + "\n" + "\n".join(
            line.format(date=nice_date(r["day"]), time=r["time"], doctor=_(r["name"])) for r in rows)}

    docs = doctors()
    named = [d for d in docs if words & {p for p in vocab(d["name"] + " " + AR.get(d["name"], "")) if len(p) > 3}]
    dept = max(SYMPTOMS, key=lambda k: hits(words, SYMPTOMS[k]))
    dept = dept if hits(words, SYMPTOMS[dept]) else None
    if named or dept or has(BOOK):
        pool = named or [d for d in docs if d["department"] == dept] or docs
        slots = earliest_slots(pool)
        if named:
            intro = _("Here are the earliest free times with {doctor}:").format(doctor=_(named[0]["name"]))
        elif dept:
            intro = _("Based on what you described, the {dept} department is the right place to start (this is guidance, not a diagnosis). Earliest free times:").format(dept=_(dept))
        else:
            intro = _("Here are the earliest free appointments across the hospital:")
        if not slots:
            return {"reply": intro + "\n" + _("No free slots in the next two weeks, sorry. Please call us at {phone}").format(phone=ltr(HOSPITAL["phone"]))}
        return {"reply": intro, "slots": [
            {"doctor": _(doc["name"]), "label": f"{_(doc['department'])} - {nice_date(d.isoformat())} {s}",
             "url": url_for("book", doctor=doc["id"], day=d.isoformat(), time=s)} for d, s, doc in slots]}

    if has(HOURS):
        return {"reply": _(HOSPITAL["hours"])}
    if has(CONTACT):
        return {"reply": _("Phone: {phone}\nEmail: {email}\nAddress: {address}").format(
            phone=ltr(HOSPITAL["phone"]), email=ltr(HOSPITAL["email"]), address=_(HOSPITAL["address"]))}
    if has(DEPARTMENTS):
        return {"reply": _("Our departments and doctors:") + "\n" + "\n".join(f"- {_(d['department'])}: {_(d['name'])}" for d in docs)}
    if has(GREETINGS):
        return {"reply": _("Hello! I'm the SmartCare assistant. Tell me your symptoms or a department and I'll find you a free appointment.")}
    if has(THANKS):
        return {"reply": _("You're welcome! Get well soon.")}
    return {"reply": _("I can help you:\n- find a free appointment (e.g. \"I have a toothache\")\n- show your appointments\n- explain how to cancel or reschedule\n- give opening hours and contact details")}


@app.post("/chat")
def chat():
    message = ((request.get_json(silent=True) or {}).get("message") or "").strip()[:500]
    if not message:
        return jsonify(reply=_("Please type a question."))
    return jsonify(bot_reply(message))


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
