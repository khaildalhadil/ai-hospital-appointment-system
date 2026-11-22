"""Smoke test: python test_app.py  (uses a throwaway database)."""
import ast
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from jinja2 import nodes

os.environ["HOSPITAL_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import app as hospital  # noqa: E402
from translations import AR  # noqa: E402

c = hospital.app.test_client()


def login(email, pw):
    c.get("/logout")
    return c.post("/login", data={"email": email, "password": pw}, follow_redirects=True)


def ask(message):
    return c.post("/chat", json={"message": message}).get_json()


# Every text passed to _() in app.py and the templates, plus the demo data, has an Arabic translation.
def python_texts(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_" and n.args and isinstance(n.args[0], ast.Constant)}


def template_texts():
    env, found = hospital.app.jinja_env, set()
    for name in env.list_templates():
        for call in env.parse(env.loader.get_source(env, name)[0]).find_all(nodes.Call):
            if isinstance(call.node, nodes.Name) and call.node.name == "_" and call.args and isinstance(call.args[0], nodes.Const):
                found.add(call.args[0].value)
    return found


demo_data = (set(hospital.STATUSES) | {name for key, name in hospital.DAY_NAMES} | {"Hospital Admin", "Demo Patient"}
             | {hospital.HOSPITAL[k] for k in ("name", "address", "hours")}
             | {name for name, key, dept in hospital.DEMO_DOCTORS} | {dept for name, key, dept in hospital.DEMO_DOCTORS})
missing = (python_texts(hospital.__file__) | template_texts() | demo_data) - AR.keys()
assert not missing, f"missing Arabic text: {missing}"

# Pages render for every role.
assert c.get("/").status_code == 200 and c.get("/about").status_code == 200
assert login("patient@smartcare.test", "patient123").status_code == 200
assert b"Reminder" in c.get("/patient").data  # seeded visit tomorrow

# Find the next working day for doctor #2 and book its first free slot.
with hospital.app.test_request_context():
    doc = hospital.q("SELECT * FROM users WHERE id=2", one=True)
    day = next(date.today() + timedelta(days=i) for i in range(1, 9) if hospital.free_slots(doc, date.today() + timedelta(days=i)))
    slot = hospital.free_slots(doc, day)[0]
form = {"doctor": 2, "day": day.isoformat(), "time": slot}
assert b"booked with" in c.post("/book", data=form, follow_redirects=True).data
assert b"not available" in c.post("/book", data=form, follow_redirects=True).data  # no double booking
assert slot not in c.get(f"/api/slots?doctor=2&day={day}").get_json()["slots"]

# Patients cannot reach staff pages.
assert c.get("/admin").status_code == 403 and c.get("/doctor").status_code == 403

# Assistant intents in English.
assert "9999" in ask("my father is bleeding, emergency")["reply"]
assert "Dental" in ask("I have a toothache")["reply"] and ask("I have a toothache")["slots"]
assert "upcoming" in ask("show my appointments")["reply"].lower()
assert "Sunday" in ask("what are your opening hours")["reply"]

# Arabic: the switch flips the page to right-to-left and the assistant understands Arabic.
c.get("/lang/ar?next=/")
home = c.get("/").get_data(as_text=True)
assert 'dir="rtl"' in home and "حجز موعد" in home and "طب الأسنان" in home
reply = ask("عندي ألم في الأسنان")
assert "طب الأسنان" in reply["reply"] and reply["slots"]
assert "9999" in ask("أبوي ينزف")["reply"]
assert "مواعيدك القادمة" in ask("عرض مواعيدي")["reply"]
assert "العيادات" in ask("ما هي أوقات الدوام؟")["reply"]
assert "أحمد البلوشي" in ask("أبي موعد مع الدكتور أحمد")["reply"]
assert "تذكير" in c.get("/patient").get_data(as_text=True)
c.get("/lang/en?next=/")
assert 'dir="ltr"' in c.get("/").get_data(as_text=True)

for email, pw, page in [("ahmed@smartcare.test", "doctor123", "/doctor"),
                        ("admin@smartcare.test", "admin123", "/admin"),
                        ("admin@smartcare.test", "admin123", "/admin/reports")]:
    login(email, pw)
    for lang in ("en", "ar"):
        c.get(f"/lang/{lang}")
        assert c.get(page).status_code == 200, (page, lang)

print("all checks passed")
