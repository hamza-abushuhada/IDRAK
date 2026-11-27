'use strict';
document.getElementById('login').addEventListener('submit', async event => {
  event.preventDefault();
  const input = document.getElementById('credential');
  const token = input.value;
  input.value = '';
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})});
    if (!response.ok) throw new Error('تعذّر الدخول. تحقق من رمز المحل وحاول مجددًا.');
    location.replace('/pos');
  } catch (error) {
    document.getElementById('error').textContent = error.message;
  } finally { button.disabled = false; }
});
