'use strict';
// Consent screen for linking a shop to IDRAK. The request arrives in the URL
// fragment (never sent to any server or log), is moved to this tab's
// sessionStorage so it survives signing in, and is removed once used.
// Everything that matters is decided on the server: ownership of the chosen
// shop, the single-use request and the fixed address IDRAK is reached at.
const KEY = 'idrak_connect';
const $ = (id) => document.getElementById(id);
let lang = 'ar', ctx = null, pending = null, timer = null;
const t = (ar, en) => (lang === 'en' ? en : ar);

function readPending() {
  if (location.hash.length > 1) {
    const params = new URLSearchParams(location.hash.slice(1));
    history.replaceState(null, '', location.pathname);
    const request = params.get('request') || '', state = params.get('state') || '';
    if (request && request.length <= 2048 && /^[A-Za-z0-9_-]{43}$/.test(state)) sessionStorage.setItem(KEY, JSON.stringify({ request, state }));
  }
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch { return null; }
}

async function post(path, body) {
  const response = await fetch(path, { method: 'POST', cache: 'no-store', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  let data = {};
  try { data = await response.json(); } catch { /* empty */ }
  return { status: response.status, data };
}

function show(section) {
  $('problem').hidden = section !== 'problem';
  $('consent').hidden = section !== 'consent';
}

function problem(title, text, link) {
  clearInterval(timer);
  $('intro').textContent = '';
  $('problem-title').textContent = title;
  $('problem-text').textContent = text;
  const a = $('problem-link');
  a.hidden = !link;
  if (link) { a.textContent = link.label; a.href = link.href; }
  show('problem');
}

const RESTART = () => t('ارجع إلى صفحة IDRAK Connect في إدراك وابدأ الربط من جديد.', 'Go back to IDRAK Connect in IDRAK and start linking again.');

function retryLink() {
  return ctx && typeof ctx.retry_url === 'string' && ctx.retry_url.startsWith(ctx.idrak_origin + '/')
    ? { label: t('ابدأ من جديد في إدراك', 'Start again in IDRAK'), href: ctx.retry_url } : null;
}

function failure(status) {
  if (status === 401) { location.replace('/login?next=connect'); return; }
  sessionStorage.removeItem(KEY);
  if (status === 409) return problem(t('تعذّر إكمال الربط', 'Linking could not be completed'),
    t('هذا الطلب استُخدم مسبقًا، أو أن المحل مرتبط بمؤسسة أخرى في إدراك. ', 'This request was already used, or the shop is linked to another IDRAK business. ') + RESTART(), retryLink());
  if (status === 403) return problem(t('الموافقة لصاحب المحل فقط', 'Only the shop owner can approve'),
    t('يجب أن يوافق مالك المحل على الربط بحسابه. حساب الكاشير لا يستطيع منح هذه الموافقة.', 'The shop owner must approve with their own account. Cashier accounts cannot grant this.'));
  if (status === 503) return problem(t('الربط غير متاح الآن', 'Linking is unavailable'), t('حاول لاحقًا.', 'Please try again later.'));
  return problem(t('انتهت صلاحية طلب الربط', 'This link request has expired'), t('طلبات الربط صالحة لدقائق قليلة ولمرة واحدة. ', 'Link requests are valid once, for a few minutes. ') + RESTART(), retryLink());
}

function applyLanguage() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'en' ? 'ltr' : 'rtl';
  const copy = {
    eyebrow: t('طلب ربط من إدراك', 'Link request from IDRAK'), title: t('ربط محلك مع إدراك', 'Link your shop with IDRAK'),
    'shops-legend': t('اختر المحل الذي تريد ربطه', 'Choose the shop to link'), 'scope-title': t('ما الذي سيصل إليه إدراك؟', 'What IDRAK will be able to access'),
    'scope-pos': t('قراءة فواتير المبيعات من الكاشير', 'Read sales invoices from the cashier'),
    'scope-web': t('قراءة طلبات المتجر الإلكتروني للمحل نفسه', "Read the same shop's online store orders"),
    'scope-no-edit': t('لا يستطيع إدراك تعديل المبيعات أو الأسعار أو المخزون', 'IDRAK cannot change sales, prices or stock'),
    'scope-no-password': t('لن يحصل إدراك على كلمة مرورك أو حسابات موظفيك', "IDRAK never gets your password or your staff's accounts"),
    'revoke-note': t('يمكنك إلغاء الربط في أي وقت من صفحة IDRAK Connect في إدراك.', 'You can disconnect at any time from IDRAK Connect in IDRAK.'),
    allow: t('السماح بالربط', 'Allow linking'), deny: t('رفض', 'Deny'), switch: t('لست أنت؟ تسجيل الخروج', 'Not you? Sign out'),
  };
  for (const [id, text] of Object.entries(copy)) $(id).textContent = text;
}

function shopNote(shop) {
  if (shop.linked_elsewhere) return t('مرتبط بمؤسسة أخرى في إدراك', 'Linked to another IDRAK business');
  if (shop.role !== 'owner') return t('دورك كاشير — يلزم موافقة المالك', 'You are a cashier here — the owner must approve');
  if (shop.linked_here) return t('مرتبط مسبقًا بهذه المؤسسة — سيُجدَّد الربط', 'Already linked to this business — the link will be renewed');
  return t('أنت مالك هذا المحل', 'You own this shop');
}

function render() {
  lang = ctx.lang === 'en' ? 'en' : 'ar';
  applyLanguage();
  $('intro').textContent = t('راجع الطلب ثم اختر المحل ووافق. ستعود إلى إدراك تلقائيًا.', "Review the request, choose the shop and approve. You'll return to IDRAK automatically.");
  $('business').textContent = ctx.business ? `«${ctx.business}»` : t('مؤسستك في إدراك', 'Your IDRAK business');
  $('business-asks').textContent = t('تطلب ربط محلك لقراءة بيانات المبيعات المصرح بها.', 'is asking to link your shop and read the sales data you authorize.');
  $('who').textContent = t('أنت مسجّل باسم ', 'Signed in as ') + ctx.email;
  const list = $('shops');
  list.replaceChildren();
  const eligible = ctx.shops.filter((s) => s.can_approve);
  for (const shop of ctx.shops) {
    const label = document.createElement('label');
    label.className = 'connect-shop' + (shop.can_approve ? '' : ' disabled');
    const input = document.createElement('input');
    input.type = 'radio'; input.name = 'shop'; input.value = shop.shop_id; input.disabled = !shop.can_approve;
    input.checked = eligible.length === 1 && shop.can_approve;
    input.onchange = () => { $('allow').disabled = false; };
    const text = document.createElement('span');
    const name = document.createElement('strong'); name.textContent = shop.name;
    const note = document.createElement('small'); note.textContent = shopNote(shop);
    text.append(name, note); label.append(input, text); list.append(label);
  }
  if (!eligible.length) {
    $('error').textContent = t('لا تملك صلاحية المالك على أي محل متاح للربط. اطلب من مالك المحل تسجيل الدخول والموافقة.', "You don't own any shop that can be linked. Ask the shop owner to sign in and approve.");
  }
  $('allow').disabled = eligible.length !== 1;
  show('consent');
  const tick = () => {
    const left = Math.max(0, Math.ceil(ctx.expires_at - Date.now() / 1000));
    $('expiry').textContent = t('ينتهي الطلب خلال ', 'Request expires in ') + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
    if (!left) failure(400);
  };
  tick(); timer = setInterval(tick, 1000);
}

function leave(url) {
  // Only ever to the IDRAK address the server is configured with.
  if (typeof url !== 'string' || !url.startsWith(ctx.idrak_origin + '/')) return failure(503);
  sessionStorage.removeItem(KEY);
  clearInterval(timer);
  location.replace(url);
}

$('consent').addEventListener('submit', async (event) => {
  event.preventDefault();
  const chosen = document.querySelector('input[name="shop"]:checked');
  if (!chosen) { $('error').textContent = t('اختر المحل أولًا.', 'Choose a shop first.'); return; }
  $('allow').disabled = true; $('deny').disabled = true; $('error').textContent = '';
  try {
    const { status, data } = await post('/api/connect/approve', { intent: pending.request, state: pending.state, shop_id: chosen.value });
    if (status === 200) return leave(data.redirect);
    failure(status);
  } catch {
    $('error').textContent = t('تعذّر الوصول إلى الخادم. تحقق من الاتصال وحاول مجددًا.', 'Cannot reach the server. Check your connection and try again.');
  } finally { $('allow').disabled = false; $('deny').disabled = false; }
});

$('deny').addEventListener('click', () => leave(ctx.cancel_url));

$('switch').addEventListener('click', async () => {
  await fetch('/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {});
  location.replace('/login?next=connect');
});

(async () => {
  pending = readPending();
  if (!pending) return problem(t('لا يوجد طلب ربط', 'No link request'), t('ابدأ الربط من صفحة IDRAK Connect في إدراك بالضغط على «ربط نظام جديد».', 'Start from IDRAK Connect in IDRAK with “Connect a new system”.'));
  try {
    const { status, data } = await post('/api/connect/context', { intent: pending.request, state: pending.state });
    if (status !== 200) return failure(status);
    ctx = data;
    render();
  } catch {
    problem(t('تعذّر الوصول إلى الخادم', 'Cannot reach the server'), t('تحقق من الاتصال ثم أعد تحميل الصفحة.', 'Check your connection, then reload the page.'));
  }
})();
