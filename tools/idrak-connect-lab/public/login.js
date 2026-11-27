'use strict';
const AFTER_LOGIN = new URLSearchParams(location.search).get('next') === 'connect' ? '/connect' : '/pos';
if (AFTER_LOGIN === '/connect') document.getElementById('connect-hint').hidden = false;
// Credentials are sent once over HTTPS and never stored in the page or browser storage.
async function signIn(body, errorEl, button, fields) {
  errorEl.textContent = '';
  button.disabled = true;
  try {
    const response = await fetch('/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (response.status === 429) throw new Error('محاولات كثيرة. انتظر قليلًا ثم حاول مجددًا.');
    if (response.status === 403) throw new Error('هذه الطريقة غير مفعّلة.');
    if (!response.ok) throw new Error(body.token ? 'تعذّر الدخول. تحقق من رمز المحل.' : 'البريد أو كلمة المرور غير صحيحة.');
    fields.forEach(f => { f.value = ''; });
    location.replace(AFTER_LOGIN);
  } catch (error) {
    errorEl.textContent = error.message;
  } finally { button.disabled = false; }
}
document.getElementById('login').addEventListener('submit', event => {
  event.preventDefault();
  const email = document.getElementById('email'), password = document.getElementById('password');
  if (!email.value.trim() || !password.value) { document.getElementById('error').textContent = 'أدخل البريد وكلمة المرور.'; return; }
  const body = {email: email.value.trim(), password: password.value};
  password.value = '';
  signIn(body, document.getElementById('error'), event.target.querySelector('button'), [password]);
});
document.getElementById('token-login').addEventListener('submit', event => {
  event.preventDefault();
  const input = document.getElementById('credential');
  const body = {token: input.value};
  input.value = '';
  signIn(body, document.getElementById('token-error'), event.target.querySelector('button'), [input]);
});
