# SmartCare: AI Hospital Appointment & Patient Support System

**[العربية](#العربية) | [English](#english)**

نظام ويب لحجز مواعيد المستشفى مع مساعد ذكي لدعم المرضى.

A web system for booking hospital appointments, with an AI patient assistant.

---

## العربية

### نبذة عن البرنامج

موقع ويب يعمل على جهاز الكمبيوتر، يتيح للمرضى حجز مواعيد المستشفى وتغييرها وإلغاءها، ويحتوي على مساعد ذكي يقترح القسم المناسب حسب الأعراض ويعرض أقرب المواعيد المتاحة. في البرنامج ثلاثة أنواع من المستخدمين: المريض والطبيب والمدير.

### المزايا

- **المريض:** إنشاء حساب، وحجز موعد في الأوقات المتاحة فقط (لا يمكن حجز نفس الموعد مرتين)، وتغيير الموعد أو إلغاؤه، وتذكير بالمواعيد خلال 48 ساعة، وسجل بالمواعيد السابقة.
- **المساعد الذكي:** موجود في كل صفحات الموقع. يقترح القسم المناسب حسب وصف الأعراض مع أقرب المواعيد المتاحة والحجز بضغطة واحدة، ويعرض مواعيد المريض وأوقات الدوام ومعلومات التواصل، ويوجّه الحالات الطارئة إلى رقم الطوارئ 9999.
- **الطبيب:** عرض مواعيد اليوم والمواعيد القادمة والسابقة، وتحديد حالة كل موعد: تم، أو لم يحضر، أو ملغي.
- **المدير:** إدارة جميع المواعيد وتغيير حالتها، وتحديد أيام وساعات دوام كل طبيب، وإضافة أطباء جدد، وعرض قائمة المرضى، وتقارير قابلة للطباعة.

### المتطلبات

- جهاز يعمل بنظام Windows 10 أو أحدث (طريقة التشغيل على Mac و Linux في الأسفل).
- برنامج Python الإصدار 3.9 أو أحدث.
- اتصال بالإنترنت في أول تشغيل فقط، لتنزيل مكتبة Flask.

### التثبيت والتشغيل على Windows

1. تثبيت Python من الموقع الرسمي https://www.python.org/downloads/ مع تفعيل خيار **Add python.exe to PATH** في أول شاشة من التثبيت.
2. تنزيل البرنامج من هذه الصفحة: الزر الأخضر **Code** ثم **Download ZIP**.
3. فك ضغط الملف: زر الفأرة الأيمن على الملف ثم **Extract All**. البرنامج لا يعمل من داخل ملف ZIP مباشرة.
4. فتح المجلد الناتج والنقر مرتين على الملف **run.bat**.
5. أول تشغيل يحتاج دقيقة تقريباً للتجهيز، بعدها يفتح الموقع تلقائياً في المتصفح على العنوان http://127.0.0.1:5000
6. يجب إبقاء النافذة السوداء مفتوحة طوال استخدام الموقع، وإغلاقها يوقف البرنامج.

في المرات التالية يكفي النقر مرتين على **run.bat**.

### حسابات التجربة

| الدور | البريد الإلكتروني | كلمة المرور |
|---|---|---|
| مريض | patient@smartcare.test | patient123 |
| طبيب | ahmed@smartcare.test | doctor123 |
| مدير | admin@smartcare.test | admin123 |

يوجد ستة أطباء آخرون، والبريد لكل منهم هو اسمه الأول بالإنجليزية متبوعاً بـ `@smartcare.test` (مثل `fatma@smartcare.test`)، وكلمة المرور `doctor123`. ويمكن إنشاء حساب مريض جديد من زر **Register**.

### جولة سريعة

1. فتح المساعد الذكي من زر **Ask the AI assistant** أسفل الصفحة، وكتابة: `I have a toothache`
2. اختيار أحد المواعيد المقترحة، ثم تسجيل الدخول بحساب المريض، ثم الضغط على **Book appointment**.
3. في صفحة **My appointments** يظهر الموعد مع التذكير وأزرار التغيير والإلغاء.
4. تسجيل الدخول بحساب الطبيب لإدارة مواعيده، وبحساب المدير لإدارة جداول الأطباء وعرض التقارير.

### حل المشاكل

- عند ظهور الرسالة `Python 3 is not installed`: تثبيت Python (الخطوة 1) ثم تشغيل run.bat مرة أخرى.
- عند ظهور تحذير أمان من Windows: الضغط على **Run**، أو على **More info** ثم **Run anyway**.
- عند ظهور الرسالة `Could not install Flask`: التأكد من الاتصال بالإنترنت ثم تشغيل run.bat مرة أخرى.
- إذا لم يفتح الموقع: التأكد من أن النافذة السوداء ما زالت مفتوحة، ثم فتح العنوان http://127.0.0.1:5000 يدوياً في المتصفح.
- لإرجاع البرنامج لحالته الأولى وحذف كل الحجوزات: إغلاق البرنامج ثم حذف الملف `hospital.db`، وسيُنشأ من جديد بالبيانات التجريبية.

### التشغيل على Mac أو Linux

من داخل مجلد البرنامج في الطرفية (Terminal):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
python app.py
```

ثم فتح العنوان http://127.0.0.1:5000 في المتصفح. وفي المرات التالية يكفي الأمر `source .venv/bin/activate` ثم `python app.py`.

على أجهزة Mac قد يكون المنفذ 5000 مشغولاً بخدمة AirPlay. الحل تشغيل البرنامج بالأمر التالي ثم فتح http://127.0.0.1:5001

```bash
flask --app app run --port 5001
```

### تخصيص البرنامج

- اسم المستشفى ورقم الهاتف والعنوان وأوقات الدوام موجودة في المتغير `HOSPITAL` أعلى الملف `app.py`.
- الحسابات والمواعيد محفوظة في الملف `hospital.db` (قاعدة بيانات SQLite) الذي يُنشأ تلقائياً عند أول تشغيل.

### ملاحظات مهمة

- واجهة الموقع باللغة الإنجليزية.
- المساعد الذكي يعمل بالكلمات المفتاحية وقواعد محددة، بدون إنترنت أو اشتراك، ويفهم اللغة الإنجليزية فقط.
- اقتراحات المساعد إرشادية وليست تشخيصاً طبياً.
- التذكير يظهر داخل الموقع فقط، بدون رسائل SMS أو بريد إلكتروني.
- البرنامج نسخة تجريبية تعمل على جهاز واحد، وغير مُعدّ للنشر على الإنترنت بوضعه الحالي.

### ملفات المشروع

| الملف | الوصف |
|---|---|
| `run.bat` | تشغيل البرنامج على Windows |
| `app.py` | الخادم: الحسابات والحجز والمساعد الذكي والتقارير |
| `templates/` | صفحات الموقع |
| `static/` | التصميم ونافذة المساعد الذكي |
| `test_app.py` | اختبار سريع للتأكد من عمل البرنامج: `python test_app.py` |

### عن المشروع

مشروع تخرج في علوم الحاسب بعنوان *AI-Based Hospital Appointment and Patient Support System*.

- إعداد: Hayat Salim Humaid AL-butini
- إشراف: Abubuckr Samsudeen Shaffi
- الكلية: Gulf College

التقنيات المستخدمة: Python (Flask) و SQLite و HTML و CSS و JavaScript.

---

## English

### About

A web application that runs on your computer and lets patients book, reschedule and cancel hospital appointments. An AI assistant suggests the right department from the patient's symptoms and shows the earliest free appointments. There are three types of users: patient, doctor and admin.

### Features

- **Patient:** create an account, book only free time slots (a slot can never be booked twice), reschedule or cancel, get reminders for visits in the next 48 hours, and see past visits.
- **AI assistant:** available on every page. Suggests a department from described symptoms with the earliest free slots and one-click booking, shows the patient's appointments, opening hours and contact details, and directs emergencies to 9999.
- **Doctor:** see today's, upcoming and past appointments, and mark each one completed, no-show or cancelled.
- **Admin:** manage all appointments and their status, set each doctor's working days and hours, add doctors, view patients, and print reports.

### Requirements

- Windows 10 or newer (Mac and Linux steps are below)
- Python 3.9 or newer
- An internet connection on the first run only, to download Flask

### Install and run on Windows

1. Install Python from https://www.python.org/downloads/ and tick **Add python.exe to PATH** on the first installer screen.
2. On this page, click the green **Code** button, then **Download ZIP**.
3. Right-click the downloaded file and choose **Extract All**. The program does not run from inside the ZIP.
4. Open the extracted folder and double-click **run.bat**.
5. The first run takes about a minute to set up. Then the site opens in your browser at http://127.0.0.1:5000
6. Keep the black window open while you use the site. Closing it stops the program.

Next time, just double-click **run.bat**.

### Demo accounts

| Role | Email | Password |
|---|---|---|
| Patient | patient@smartcare.test | patient123 |
| Doctor | ahmed@smartcare.test | doctor123 |
| Admin | admin@smartcare.test | admin123 |

Six more doctors log in with their first name followed by `@smartcare.test` (for example `fatma@smartcare.test`) and the password `doctor123`. New patients can sign up with **Register**.

### Quick tour

1. Click **Ask the AI assistant** at the bottom of the page and type `I have a toothache`.
2. Pick one of the suggested times, log in with the patient account, then click **Book appointment**.
3. **My appointments** shows the visit with a reminder and the Reschedule and Cancel buttons.
4. Log in as the doctor to manage their appointments, or as the admin to manage doctor schedules and view reports.

### Troubleshooting

- **"Python 3 is not installed"**: install Python (step 1), then run `run.bat` again.
- **Windows security warning**: click **Run**, or **More info** then **Run anyway**.
- **"Could not install Flask"**: check the internet connection and run `run.bat` again.
- **The site does not open**: make sure the black window is still open, then go to http://127.0.0.1:5000 in your browser.
- **Start over with fresh demo data**: close the program and delete `hospital.db`. It is created again on the next run.

### Run on Mac or Linux

In a terminal, inside the program folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
python app.py
```

Then open http://127.0.0.1:5000 in your browser. Next time, run `source .venv/bin/activate` and then `python app.py`.

On a Mac, port 5000 may be taken by AirPlay Receiver. If so, start the program with this command and open http://127.0.0.1:5001

```bash
flask --app app run --port 5001
```

### Customize

- The hospital name, phone, address and opening hours are in `HOSPITAL` at the top of `app.py`.
- Accounts and appointments are stored in `hospital.db` (SQLite), which is created automatically on the first run.

### Good to know

- The site's interface is in English.
- The AI assistant works with keyword rules. It runs offline with no subscription and understands English only.
- Its department suggestions are guidance, not a medical diagnosis.
- Reminders appear inside the site only, with no SMS or email.
- This is a prototype for running on one computer. It is not set up for public internet hosting as it is.

### Project files

| File | Purpose |
|---|---|
| `run.bat` | Starts the program on Windows |
| `app.py` | Server: accounts, booking, AI assistant and reports |
| `templates/` | Site pages |
| `static/` | Styles and the assistant chat window |
| `test_app.py` | Quick self-check: `python test_app.py` |

### About the project

Computer Science dissertation project, *AI-Based Hospital Appointment and Patient Support System*.

- Prepared by: Hayat Salim Humaid AL-butini
- Supervisor: Abubuckr Samsudeen Shaffi
- College: Gulf College

Built with Python (Flask), SQLite, HTML, CSS and JavaScript.
