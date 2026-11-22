"""Smoke test: python test_app.py  (uses a throwaway database)."""
import os
import tempfile
from datetime import date, timedelta

os.environ["HOSPITAL_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import app as hospital  # noqa: E402

c = hospital.app.test_client()


def login(email, pw):
    c.get("/logout")
    return c.post("/login", data={"email": email, "password": pw}, follow_redirects=True)


# Pages render for every role.
assert c.get("/").status_code == 200 and c.get("/about").status_code == 200
assert login("patient@smartcare.test", "patient123").status_code == 200
assert b"Reminder" in c.get("/patient").data  # seeded visit tomorrow

# Find the next working day for doctor #2 and book its first free slot.
with hospital.app.app_context():
    doc = hospital.q("SELECT * FROM users WHERE id=2", one=True)
    day = next(date.today() + timedelta(days=i) for i in range(1, 9) if hospital.free_slots(doc, date.today() + timedelta(days=i)))
    slot = hospital.free_slots(doc, day)[0]
form = {"doctor": 2, "day": day.isoformat(), "time": slot}
assert b"booked with" in c.post("/book", data=form, follow_redirects=True).data
assert b"not available" in c.post("/book", data=form, follow_redirects=True).data  # no double booking
assert slot not in c.get(f"/api/slots?doctor=2&day={day}").get_json()["slots"]

# Patients cannot reach staff pages.
assert c.get("/admin").status_code == 403 and c.get("/doctor").status_code == 403

# Assistant intents.
ask = lambda m: c.post("/chat", json={"message": m}).get_json()
assert "9999" in ask("my father is bleeding, emergency")["reply"]
assert "Dental" in ask("I have a toothache")["reply"] and ask("I have a toothache")["slots"]
assert "upcoming" in ask("show my appointments")["reply"].lower()
assert "Sunday" in ask("what are your opening hours")["reply"]

for email, pw, page in [("ahmed@smartcare.test", "doctor123", "/doctor"),
                        ("admin@smartcare.test", "admin123", "/admin"),
                        ("admin@smartcare.test", "admin123", "/admin/reports")]:
    login(email, pw)
    assert c.get(page).status_code == 200, page

print("all checks passed")
