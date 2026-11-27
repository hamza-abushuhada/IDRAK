'use strict';
// The invite token travels in the URL fragment (never sent to servers or logs)
// and is removed from the address bar immediately.
const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
history.replaceState(null, '', location.pathname);
const $ = id => document.getElementById(id);
const roleLabel = r => r === 'owner' ? 'صاحب المحل' : 'موظف كاشير';
let existing = false;
async function post(path, body) {
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  let data = {}; try { data = await r.json(); } catch {}
  return {ok: r.ok, status: r.status, data};
}
(async () => {
  if (!token) { $('intro').textContent = 'رابط الدعوة غير مكتمل. اطلب رابطًا جديدًا.'; return; }
  const {ok, data} = await post('/auth/invite', {token});
  if (!ok) { $('intro').textContent = 'رابط الدعوة غير صالح أو منتهي أو مستخدم. اطلب رابطًا جديدًا.'; return; }
  existing = data.has_account;
  $('invite-for').textContent = `${data.email} · ${roleLabel(data.role)} · ${data.shop_name}`;
  if (existing) {
    $('title').textContent = 'قبول الدعوة';
    $('intro').textContent = 'لديك حساب بالفعل. أدخل كلمة مرورك الحالية لإضافة هذا المحل إلى حسابك.';
    $('password-label').textContent = 'كلمة المرور الحالية';
    $('password').autocomplete = 'current-password';
    $('confirm-field').hidden = true; $('hint').hidden = true;
    $('submit').textContent = 'قبول الدعوة والدخول';
  } else {
    $('intro').textContent = 'اختر كلمة مرور لحسابك في نظام الكاشير. ستستخدمها مع بريدك لتسجيل الدخول.';
  }
  $('activate').hidden = false;
})();
$('activate').addEventListener('submit', async event => {
  event.preventDefault();
  const password = $('password').value, confirm = $('confirm').value;
  $('error').textContent = '';
  if (!existing) {
    if (password.length < 10) { $('error').textContent = 'كلمة المرور يجب أن تكون 10 أحرف على الأقل.'; return; }
    if (password !== confirm) { $('error').textContent = 'كلمتا المرور غير متطابقتين.'; return; }
  }
  $('submit').disabled = true;
  const {ok, status} = await post('/auth/activate', {token, password});
  $('password').value = ''; $('confirm').value = '';
  if (ok) { location.replace(sessionStorage.getItem('idrak_connect') ? '/connect' : '/pos'); return; }
  $('submit').disabled = false;
  $('error').textContent = status === 429 ? 'محاولات كثيرة. انتظر قليلًا ثم حاول مجددًا.'
    : status === 401 ? 'كلمة المرور الحالية غير صحيحة.'
    : status === 400 && !existing ? 'تعذّر التفعيل. اختر كلمة مرور أقوى أو اطلب رابطًا جديدًا.'
    : 'تعذّر قبول الدعوة. اطلب رابطًا جديدًا.';
});
