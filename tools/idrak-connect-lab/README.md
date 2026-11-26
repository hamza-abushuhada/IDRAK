# IDRAK Connect Lab (test simulator)

A **standalone, local-only** sample POS + online store used to exercise **IDRAK
Connect** end to end. It is a developer **test tool**, completely independent of the
production IDRAK app: it shares **no** code, imports nothing from `api/` or `web/`,
and keeps its own isolated SQLite database. It never connects to any production
system and needs none of your personal data.

- No third-party dependencies — **Python 3.10+ only**.
- Listens on `127.0.0.1` only (not the network/internet).
- No real payments, no real customer data, not production-ready as-is.

---

## English

### 1. Run on Windows
From this folder (`tools/idrak-connect-lab/`):

- **Easiest:** double-click `START_WINDOWS.bat`, **or** in a terminal:
  ```powershell
  py -3 demo_server.py
  ```
  (If `py` is unknown, use `python demo_server.py`.)

It starts two local servers and prints their URLs. Stop with `Ctrl+C`.

### 2. Local URLs
| Screen | URL |
|---|---|
| POS cashier | http://127.0.0.1:8765/pos |
| Online store | http://127.0.0.1:8765/shop |
| Orders & refunds admin | http://127.0.0.1:8765/admin |
| Standalone receiver simulator | http://127.0.0.1:8766/ |

> The receiver on `:8766` is the Lab's **own** simulator, not IDRAK. To see data in
> the **real** local IDRAK dashboard, connect it to IDRAK as in section 4.

### 3. Configuration (`env.example`)
Copy `env.example` to `.env` only if you want to override defaults (the server also
reads these as environment variables). All values are **non-secret, local-test**:

| Variable | Default | Meaning |
|---|---|---|
| `IDRAK_LAB_SOURCE_PORT` | `8765` | POS/store + API port |
| `IDRAK_LAB_RECEIVER_PORT` | `8766` | the Lab's own receiver simulator |
| `IDRAK_LAB_DATA_DIR` | `./data` | isolated SQLite test data (created on first run) |
| `IDRAK_LAB_WEBHOOK_SECRET` | `idrak-local-demo-only-secret` | demo HMAC key for signed webhooks |

`.env`, `data/` and `*.sqlite3` are git-ignored — never commit real secrets or data.

### 4. Connect it to a LOCAL IDRAK (test DB only)
1. Run the IDRAK API + web **locally against a separate test database** (e.g. a local
   Docker Postgres). **Never point IDRAK at production** for this.
2. Apply IDRAK's POS migrations (`api/db/migrations/007`–`010`) to that test DB.
3. In IDRAK → **IDRAK Connect** (ربط أنظمة نقاط البيع), connect **"IDRAK Lab — POS
   (test)"** and **"IDRAK Lab — Online store (test)"**. IDRAK's `lab_pos` / `lab_web`
   connectors pull from this simulator's event APIs
   (`/api/pos/events`, `/api/web/events`) and also accept its **signed webhook**.
4. Keep the same `IDRAK_LAB_WEBHOOK_SECRET` on both sides if you test webhooks.

### 5. Test: a POS invoice reaches IDRAK automatically
1. Open the **POS** (`/pos`), add items, take payment (cash/card).
2. Within a few seconds IDRAK **auto-syncs** it (or press **"Sync now"** in IDRAK
   Connect). Open IDRAK → **Sales**: the invoice is there, channel **In-store POS**.

### 6. Test: an online order reaches IDRAK automatically
1. Open the **store** (`/shop`), order with **demo card** → completes immediately and
   appears in IDRAK as an **Online** sale.
2. Order with **cash on delivery** → shows **pending** and is **not** counted as
   revenue; confirm it in **/admin** → it becomes a completed sale after sync.
3. Register a **refund** in `/admin` → the IDRAK invoice flips to *returned* and stock
   is restored. Re-sending the same event is de-duplicated (no double counting).

### 7. Isolation & safety
- The simulator uses its **own** SQLite under `data/` — never a production DB.
- Services bind to `127.0.0.1` only. No real payment gateway, no real credentials.
- Do **not** put real `.env`, passwords, API keys, JWTs or session files here.

---

## العربية

### ١. التشغيل على Windows
من هذا المجلّد (`tools/idrak-connect-lab/`):

- **الأسهل:** دوبل-كليك على `START_WINDOWS.bat`، **أو** من الطرفية:
  ```powershell
  py -3 demo_server.py
  ```
  (إذا `py` غير معروف، استخدم `python demo_server.py`.) يبدأ خادمين محليين ويطبع
  روابطهما. الإيقاف بـ `Ctrl+C`.

### ٢. الروابط المحلية
| الشاشة | الرابط |
|---|---|
| كاشير POS | http://127.0.0.1:8765/pos |
| المتجر الإلكتروني | http://127.0.0.1:8765/shop |
| إدارة الطلبات والمرتجعات | http://127.0.0.1:8765/admin |
| محاكي الاستقبال المستقل | http://127.0.0.1:8766/ |

> الاستقبال على `:8766` هو محاكي **المختبر نفسه**، وليس إدراك. لرؤية البيانات في لوحة
> **إدراك المحلية الحقيقية**، اربطه بإدراك كما في القسم ٤.

### ٣. الإعدادات (`env.example`)
انسخ `env.example` إلى `.env` فقط إن أردت تغيير الافتراضات (يقرأها الخادم كمتغيّرات
بيئة أيضًا). كل القيم **غير سرّية وللاختبار المحلّي**:

| المتغيّر | الافتراضي | المعنى |
|---|---|---|
| `IDRAK_LAB_SOURCE_PORT` | `8765` | منفذ الكاشير/المتجر + الواجهة |
| `IDRAK_LAB_RECEIVER_PORT` | `8766` | محاكي الاستقبال الخاص بالمختبر |
| `IDRAK_LAB_DATA_DIR` | `./data` | بيانات SQLite معزولة (تُنشأ أول تشغيل) |
| `IDRAK_LAB_WEBHOOK_SECRET` | `idrak-local-demo-only-secret` | مفتاح HMAC تجريبي للـ webhook |

`.env` و`data/` و`*.sqlite3` متجاهَلة في git — لا ترفع أي أسرار أو بيانات حقيقية.

### ٤. ربطه بإدراك محلي (قاعدة اختبار فقط)
1. شغّل واجهة وخادم إدراك **محليًا على قاعدة بيانات اختبار منفصلة** (مثلًا Postgres على
   Docker). **لا توجّه إدراك للإنتاج** في هذه التجربة.
2. طبّق هجرات POS (`api/db/migrations/007`–`010`) على قاعدة الاختبار.
3. في إدراك → **ربط أنظمة نقاط البيع**، اربط **«IDRAK Lab — POS (test)»** و**«IDRAK Lab
   — Online store (test)»**. موصّلا `lab_pos`/`lab_web` في إدراك يسحبان من واجهات أحداث
   المحاكي (`/api/pos/events`, `/api/web/events`) ويقبلان **webhook موقّعًا**.
4. أبقِ نفس `IDRAK_LAB_WEBHOOK_SECRET` على الطرفين عند اختبار الـ webhook.

### ٥. اختبار: فاتورة كاشير تصل إدراك تلقائيًا
1. افتح **الكاشير** (`/pos`)، أضف أصنافًا، وحصّل الدفع (نقدًا/بطاقة).
2. خلال ثوانٍ تتزامن إدراك تلقائيًا (أو اضغط **«زامن الآن»**). افتح إدراك → **المبيعات**:
   الفاتورة موجودة، وقناتها **كاشير المحل**.

### ٦. اختبار: طلب أونلاين يصل إدراك تلقائيًا
1. افتح **المتجر** (`/shop`)، اطلب بـ**بطاقة تجريبية** → يكتمل فورًا ويظهر في إدراك كبيع
   **أونلاين**.
2. اطلب بـ**الدفع عند الاستلام** → يظهر **معلّقًا** ولا يُحتسب إيرادًا؛ أكّده من **/admin**
   → يصير بيعًا مكتملًا بعد المزامنة.
3. سجّل **مرتجعًا** من `/admin` → تتحوّل الفاتورة في إدراك إلى *مرتجع* ويعود المخزون.
   إعادة إرسال نفس الحدث تُتخطّى (بلا احتساب مزدوج).

### ٧. العزل والأمان
- يستخدم المحاكي قاعدة **SQLite خاصّة به** تحت `data/` — لا قاعدة إنتاج أبدًا.
- الخدمات تستمع على `127.0.0.1` فقط. لا بوابة دفع حقيقية ولا اعتمادات حقيقية.
- لا تضع `.env` حقيقيًا أو كلمات مرور أو مفاتيح API أو JWT أو ملفات جلسات هنا.
