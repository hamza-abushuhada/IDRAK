'use strict';
const page = document.body.dataset.page;
const $ = (id) => document.getElementById(id);
let products = [];
let cart = {};
const sourceOrigin = 'http://127.0.0.1:8765';
const fmt = (value) => `${Number(value).toFixed(3)} JOD`;
const money = (value) => Number(value).toFixed(3);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labelStatus = (s) => ({completed:'مكتملة',pending:'بانتظار الدفع',cancelled:'ملغاة',refunded:'مرتجعة'})[s] || s;
const labelChannel = (c) => c === 'pos' ? 'الكاشير POS' : 'المتجر الإلكتروني';
function toast(message,error=false){const old=document.querySelector('.toast');if(old)old.remove();const el=document.createElement('div');el.className='toast'+(error?' error':'');el.textContent=message;document.body.append(el);setTimeout(()=>el.remove(),3800)}
async function api(path,options={}){
  const prefix=page==='inbox' && location.pathname.startsWith('/simulator') ? '/simulator' : '';
  const r=await fetch(prefix+path,{headers:{'Content-Type':'application/json'},...options});
  if(r.status===401){location.replace('/login');throw new Error('انتهت جلسة الدخول');}
  const data=await r.json();
  if(!r.ok)throw new Error(data.error||`HTTP ${r.status}`);
  return data;
}
// The server chooses the shop. No credentials or shop selector are persisted here.
fetch('/auth/session').then(r=>r.ok?r.json():null).then(session=>{
  if(!session)return;
  const nav=document.querySelector('.nav');
  // Fail closed: owner controls need BOTH the server-rendered role and the
  // session to say owner. Owner-only markup is already stripped server-side
  // for cashiers and hidden by default in CSS; the server enforces every action.
  const owner=document.documentElement.dataset.role==='owner'&&session.role==='owner';
  if(!owner)document.querySelectorAll('[data-owner]').forEach(el=>el.remove());
  if(session.shops&&session.shops.length>1){
    const select=document.createElement('select');select.className='shop-switch';select.setAttribute('aria-label','المحل الحالي');
    session.shops.forEach(s=>{const o=document.createElement('option');o.value=s.shop_id;o.textContent=s.name+(s.role==='cashier'?' (كاشير)':'');o.selected=s.shop_id===session.shop_id;select.append(o);});
    select.onchange=async()=>{const r=await fetch('/auth/switch-shop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shop_id:select.value})});if(r.ok)location.replace(owner||page==='pos'?location.pathname:'/pos');else toast('تعذّر تبديل المحل',true);};
    nav?.append(select);
  }else{
    const label=document.createElement('span');label.className='pill';label.textContent=session.name;nav?.append(label);
  }
  if(session.email){const who=document.createElement('span');who.className='pill who';who.dir='ltr';who.textContent=session.email+' · '+(owner?'صاحب المحل':'كاشير');nav?.append(who);}
  if(session.kind==='shop'){
    if(owner){setupPairing(session, nav);if(session.via==='password')setupTeam(nav);}
    const button=document.createElement('button');button.className='btn secondary small';button.textContent='تسجيل الخروج';
    button.onclick=async()=>{await fetch('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});location.replace('/login');};
    nav?.append(button);
  }
}).catch(()=>{});

function setupTeam(nav){
  const open=document.createElement('button');open.type='button';open.className='btn secondary small';open.textContent='الفريق';nav?.append(open);
  const dialog=document.createElement('dialog');dialog.className='pairing-dialog';dialog.setAttribute('aria-labelledby','team-title');document.body.append(dialog);
  async function draw(){
    dialog.innerHTML=`<div class="row"><h2 id="team-title">فريق المحل</h2><button class="btn secondary small" type="button" id="team-close">إغلاق</button></div>
      <p class="muted">أضف موظف كاشير ببريده. سيحصل على رابط دعوة لمرة واحدة صالح 48 ساعة ليختار كلمة مروره بنفسه.</p>
      <form id="team-form"><label for="team-email">بريد موظف الكاشير</label><input id="team-email" type="email" dir="ltr" required maxlength="254" autocomplete="off"><button class="btn" type="submit">إنشاء رابط دعوة</button></form>
      <div id="team-link" hidden><label for="team-url">رابط الدعوة (يظهر مرة واحدة)</label><input id="team-url" dir="ltr" readonly><button class="btn secondary" type="button" id="team-copy">نسخ الرابط</button></div>
      <p id="team-error" role="alert"></p><h3>الأعضاء</h3><div id="team-list" class="list"></div>`;
    dialog.querySelector('#team-close').onclick=()=>dialog.close();
    dialog.querySelector('#team-form').onsubmit=async e=>{
      e.preventDefault();const input=dialog.querySelector('#team-email');dialog.querySelector('#team-error').textContent='';
      try{const r=await api('/api/team/invite',{method:'POST',body:JSON.stringify({email:input.value.trim(),role:'cashier'})});
        input.value='';const url=dialog.querySelector('#team-url');url.value=location.origin+'/activate#token='+encodeURIComponent(r.token);
        dialog.querySelector('#team-link').hidden=false;url.focus();url.select();await list();}
      catch(err){dialog.querySelector('#team-error').textContent=err.message;}
    };
    dialog.querySelector('#team-copy').onclick=async()=>{const url=dialog.querySelector('#team-url');try{await navigator.clipboard.writeText(url.value);toast('نُسخ رابط الدعوة');}catch{url.select();}};
    await list();
  }
  async function list(){
    const node=dialog.querySelector('#team-list');
    try{const t=await api('/api/team');
      node.innerHTML=t.members.map(m=>`<div class="order"><div><h3 dir="ltr">${esc(m.email)}</h3><p>${m.role==='owner'?'صاحب المحل':'كاشير'}</p></div>${m.role==='cashier'?`<button class="btn secondary small" data-remove="${esc(m.user_id)}">إزالة</button>`:''}</div>`).join('')
        +t.pending_invites.map(i=>`<div class="order"><div><h3 dir="ltr">${esc(i.email)}</h3><p>دعوة بانتظار التفعيل</p></div></div>`).join('')||'<div class="empty">لا يوجد أعضاء بعد</div>';
      node.querySelectorAll('[data-remove]').forEach(b=>b.onclick=async()=>{try{await api('/api/team/remove',{method:'POST',body:JSON.stringify({user_id:b.dataset.remove})});await list();}catch(err){toast(err.message,true);}});
    }catch(err){node.textContent=err.message;}
  }
  dialog.addEventListener('close',()=>dialog.replaceChildren());
  open.onclick=()=>{dialog.showModal();draw();};
}

function setupPairing(session, nav){
  const open=document.createElement('button');open.type='button';open.className='btn small';open.textContent='ربط مع IDRAK';
  nav?.append(open);
  const dialog=document.createElement('dialog');dialog.className='pairing-dialog';dialog.setAttribute('aria-labelledby','pairing-title');
  document.body.append(dialog);
  let english=false, timer=null, abort=null;
  const text=(ar,en)=>english?en:ar;
  function clear(){
    if(timer)clearInterval(timer);timer=null;
    abort?.abort();abort=null;
    dialog.querySelectorAll('input,textarea').forEach(el=>{el.value='';});
  }
  function draw(){
    clear();dialog.dir=english?'ltr':'rtl';dialog.lang=english?'en':'ar';
    dialog.innerHTML=`<div class="row"><h2 id="pairing-title">${text('ربط مع IDRAK','Connect to IDRAK')}</h2><div><button class="btn secondary small" type="button" id="pairing-language">${english?'العربية':'English'}</button> <button class="btn secondary small" type="button" id="pairing-close">${text('إغلاق','Close')}</button></div></div>
      <p id="pairing-shop" class="pill"></p>
      <p>${text('من صفحة IDRAK Connect، أنشئ طلب ربط للمؤسسة المطلوبة أولًا، ثم الصقه هنا. أبقِ صفحة إدراك مفتوحة.','First create a connection request in IDRAK Connect for your chosen business, then paste it here. Keep IDRAK open.')}</p>
      <form id="pairing-form"><label for="pairing-intent">${text('طلب الربط المنسوخ من إدراك','Connection request copied from IDRAK')}</label><textarea id="pairing-intent" dir="ltr" rows="4" maxlength="2048" required autocomplete="off" spellcheck="false"></textarea>
      <button class="btn" id="pairing-create" type="submit">${text('إنشاء رمز الاقتران','Create pairing code')}</button></form>
      <p id="pairing-error" role="alert"></p><div id="pairing-result" hidden><p>${text('عُد إلى نفس صفحة إدراك وأدخل هذا الرمز مرة واحدة. الرمز خاص بهذا المحل والطلب.','Return to the same IDRAK page and enter this code once. It is bound to this shop and request.')}</p>
      <label for="pairing-code">${text('رمز الاقتران المؤقت','Temporary pairing code')}</label><input id="pairing-code" dir="ltr" readonly autocomplete="off" spellcheck="false"><p id="pairing-expiry" role="timer"></p>
      <button type="button" class="btn secondary" id="pairing-copy">${text('نسخ الرمز','Copy code')}</button><p id="pairing-notice" role="status"></p></div>`;
    dialog.querySelector('#pairing-shop').textContent=session.name+' · '+session.shop_id;
    dialog.querySelector('#pairing-close').onclick=()=>dialog.close();
    dialog.querySelector('#pairing-language').onclick=drawLanguage;
    dialog.querySelector('#pairing-form').onsubmit=async event=>{
      event.preventDefault();
      const input=dialog.querySelector('#pairing-intent'), button=dialog.querySelector('#pairing-create');
      const intent=input.value.trim();input.value='';
      dialog.querySelector('#pairing-result').hidden=true;dialog.querySelector('#pairing-code').value='';
      dialog.querySelector('#pairing-error').textContent='';
      if(timer)clearInterval(timer);timer=null;
      button.disabled=true;abort=new AbortController();const pending=abort;
      try{
        const r=await fetch('/api/pairing-codes',{method:'POST',cache:'no-store',signal:pending.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({intent})});
        if(!r.ok){
          const errors={
            400:text('طلب الربط غير صالح أو انتهت صلاحيته. أنشئ طلبًا جديدًا في إدراك.','The request is invalid or expired. Create a new request in IDRAK.'),
            401:text('انتهت جلسة محلك. سجّل الدخول مجددًا.','Your shop session expired. Sign in again.'),
            403:text('سجّل الدخول برمز محلك، وليس بحساب المشغّل العام.','Sign in with your shop credential, not the shared operator account.'),
            409:text('هذا المحل مرتبط بمؤسسة أخرى. استخدم المؤسسة المرتبطة به أو محلًا مختلفًا.','This shop is linked to another business. Use its linked business or a different shop.'),
            503:text('خدمة الربط غير جاهزة. تواصل مع المسؤول.','Pairing is not configured. Contact your administrator.')
          };
          throw new Error(errors[r.status]||text('تعذّر إنشاء الرمز. تحقق من الاتصال وحاول بطلب جديد.','Could not create a code. Check your connection and try a new request.'));
        }
        const result=await r.json();if(pending.signal.aborted)return;
        const code=dialog.querySelector('#pairing-code'), copy=dialog.querySelector('#pairing-copy');
        code.value=result.code;copy.disabled=false;dialog.querySelector('#pairing-result').hidden=false;
        const tick=()=>{
          const seconds=Math.max(0,Math.ceil(result.expires_at-Date.now()/1000));
          dialog.querySelector('#pairing-expiry').textContent=seconds?text('ينتهي خلال ','Expires in ')+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0'):text('انتهت الصلاحية. أنشئ طلبًا ورمزًا جديدين.','Expired. Create a new request and code.');
          if(!seconds){code.value='';copy.disabled=true;clearInterval(timer);timer=null;}
        };
        tick();timer=setInterval(tick,1000);code.focus();
      }catch(error){if(error.name!=='AbortError')dialog.querySelector('#pairing-error').textContent=error instanceof TypeError?text('تعذّر الوصول إلى الخادم. تحقق من الاتصال وحاول مجددًا.','Cannot reach the server. Check your connection and try again.'):error.message;}
      finally{if(!pending.signal.aborted)button.disabled=false;}
    };
    dialog.querySelector('#pairing-copy').onclick=async()=>{
      const code=dialog.querySelector('#pairing-code');
      if(!code.value)return;
      try{await navigator.clipboard.writeText(code.value);dialog.querySelector('#pairing-notice').textContent=text('نُسخ الرمز. الصقه في نفس طلب الربط داخل إدراك.','Code copied. Paste it into the same IDRAK request.');}
      catch{code.focus();code.select();dialog.querySelector('#pairing-notice').textContent=text('انسخ الرمز المحدد يدويًا.','Copy the selected code manually.');}
    };
  }
  function drawLanguage(){english=!english;draw();}
  dialog.addEventListener('close',()=>{clear();dialog.replaceChildren();});
  open.onclick=()=>{draw();dialog.showModal();};
}
function renderProducts(){
  const node=$('products');if(!node)return;
  node.innerHTML=products.map(p=>`<article class="product"><div class="emoji">${p.emoji}</div><span class="name">${esc(p.name_ar)}</span><span class="stock">متوفر: ${p.stock} قطعة</span><div class="footer"><strong class="price">${fmt(p.price)}</strong><button class="btn small" data-add="${p.sku}" ${p.stock<=0?'disabled':''}>إضافة +</button></div></article>`).join('');
}
function renderCart(){
  const n=$('cart');if(!n)return;
  const active=products.filter(p=>(cart[p.sku]||0)>0);
  if(!active.length)n.innerHTML='<div class="empty">لم تختر منتجات بعد</div>';
  else n.innerHTML=active.map(p=>`<div class="cart-row"><div><strong>${esc(p.name_ar)}</strong><div class="muted" dir="ltr">${fmt(p.price)}</div></div><div class="qty"><button data-minus="${p.sku}">−</button><strong>${cart[p.sku]}</strong><button data-add="${p.sku}">+</button></div></div>`).join('');
  const total=active.reduce((sum,p)=>sum+Number(p.price)*cart[p.sku],0);
  $('total').textContent=fmt(total);
  $('checkout').disabled=active.length===0;
}
async function loadCatalog(){const res=await api('/api/products');products=res.products;renderProducts();renderCart()}
async function loadRecentOrders(channel){
  const res=await api('/api/orders?channel='+channel);
  $('orders').innerHTML=res.orders.length ? res.orders.slice(0,10).map(o=>`<div class="order"><div><h3 dir="ltr">${esc(o.external_id)}</h3><p>${o.items.map(i=>`${esc(i.name)} × ${i.quantity}`).join('، ')}</p></div><div class="row"><span class="tag ${o.status}">${labelStatus(o.status)}</span><strong dir="ltr">${fmt(o.total)}</strong></div></div>`).join('') : '<div class="empty">ما في فواتير بعد. جرّب تعمل أول عملية بيع!</div>';
}
async function checkout(channel){
  const items=Object.entries(cart).filter(([,q])=>q>0).map(([sku,quantity])=>({sku,quantity}));
  if(!items.length)return;
  const button=$('checkout');button.disabled=true;button.textContent='جاري إصدار الفاتورة...';
  try{
    const data=await api(channel==='pos'?'/api/pos/sales':'/api/web/orders',{
      method:'POST',body:JSON.stringify({items,payment_method:$('pay-method').value,...(channel==='web'?{customer:$('customer').value}:{})})
    });
    toast(`تم إنشاء ${data.order_id} · ${fmt(data.total)} · أُرسل إلى المحاكي`);
    cart={};await Promise.all([loadCatalog(),loadRecentOrders(channel)]);
  }catch(e){toast(e.message,true)}finally{button.textContent=channel==='pos'?'إصدار الفاتورة':'إرسال الطلب التجريبي';renderCart()}
}
async function setupSeller(){
  const channel=page;
  document.addEventListener('click',e=>{
    const a=e.target.closest('[data-add]');
    const m=e.target.closest('[data-minus]');
    if(a){const sku=a.dataset.add;const p=products.find(p=>p.sku===sku);if(!p)return; if((cart[sku]||0)>=p.stock){toast('الكمية المطلوبة أكبر من المخزون',true);return}cart[sku]=(cart[sku]||0)+1;renderCart()}
    if(m){const sku=m.dataset.minus;cart[sku]=Math.max(0,(cart[sku]||0)-1);renderCart()}
  });
  $('checkout').addEventListener('click',()=>checkout(channel));
  try{await Promise.all([loadCatalog(),loadRecentOrders(channel)])}catch(e){toast(e.message,true)}
}
function renderOrderActions(o){
  if(o.status==='pending')return `<button class="btn small" data-order="${esc(o.external_id)}" data-status="completed">تأكيد الدفع</button><button class="btn secondary small" data-order="${esc(o.external_id)}" data-status="cancelled">إلغاء</button>`;
  if(o.status==='completed')return `<button class="btn secondary small" data-order="${esc(o.external_id)}" data-status="refunded">تسجيل مرتجع</button>`;
  return '';
}
async function loadAdmin(){
  const [r,ev,cat]=await Promise.all([api('/api/orders'),api('/api/events'),api('/api/products')]);
  const total=r.orders.filter(o=>o.status==='completed').reduce((sum,o)=>sum+Number(o.total),0);
  $('stats').innerHTML=`<div class="stat"><div class="txt">جميع الفواتير</div><div class="big">${r.orders.length}</div></div><div class="stat"><div class="txt">المبيعات المكتملة</div><div class="big">${fmt(total)}</div></div><div class="stat"><div class="txt">أحداث تم إرسالها</div><div class="big">${ev.events.filter(e=>e.delivered).length}</div></div>`;
  $('orders').innerHTML=r.orders.length?r.orders.map(o=>`<div class="order"><div><h3 dir="ltr">${esc(o.external_id)} · ${labelChannel(o.channel)}</h3><p>${o.items.map(i=>`${esc(i.name)} × ${i.quantity}`).join('، ')}</p></div><div class="row"><span class="tag ${o.status}">${labelStatus(o.status)}</span><strong dir="ltr">${fmt(o.total)}</strong>${renderOrderActions(o)}</div></div>`).join(''):'<div class="empty">لا يوجد طلبات بعد</div>';
  $('events').innerHTML=ev.events.length?ev.events.slice(0,15).map(x=>`<div class="event"><div class="row"><code>${esc(x.event_id)}</code><span class="tag ${x.delivered?'':'pending'}">${x.delivered?'وصل':'بانتظار الإرسال'}</span></div><small>${x.event_type} · ${x.channel} · ${x.attempts} محاولة${x.last_error?' · '+esc(x.last_error):''}</small><button class="linklike" data-redeliver="${x.seq}">إعادة إرسال الحدث (اختبار التكرار)</button></div>`).join(''):'<div class="empty">لا أحداث بعد</div>';
}
async function setupAdmin(){
  document.addEventListener('click',async e=>{
    const b=e.target.closest('[data-order]');
    const d=e.target.closest('[data-redeliver]');
    if(b){
      b.disabled=true;
      try{const r=await api(`/api/orders/${encodeURIComponent(b.dataset.order)}/status`,{method:'POST',body:JSON.stringify({status:b.dataset.status})});toast(`تم تحديث ${r.order_id} إلى ${labelStatus(r.status)}`);await loadAdmin()}
      catch(x){toast(x.message,true);b.disabled=false}
    }
    if(d){try{const r=await api('/api/redeliver',{method:'POST',body:JSON.stringify({seq:Number(d.dataset.redeliver)})});toast('تمت إعادة الإرسال. المحاكي يمنع تكرار الحدث');await loadAdmin()}catch(x){toast(x.message,true)}}
  });
  $('retry').addEventListener('click',async()=>{try{await api('/api/retry',{method:'POST',body:'{}'});toast('تمت محاولة إعادة الإرسال');await loadAdmin()}catch(e){toast(e.message,true)}});
  $('refresh').addEventListener('click',loadAdmin);
  try{await loadAdmin()}catch(e){toast(e.message,true)}
}
async function loadInbox(){
 const [s,r,e]=await Promise.all([api('/api/summary'),api('/api/synced-orders'),api('/api/received-events')]);
 $('stats').innerHTML=`<div class="stat"><div class="txt">الفواتير الفريدة</div><div class="big">${s.invoices}</div></div><div class="stat"><div class="txt">الإيرادات المكتملة</div><div class="big">${fmt(s.revenue)}</div></div><div class="stat"><div class="txt">أحداث مستلمة</div><div class="big">${s.events}</div></div>`;
 $('orders').innerHTML=r.orders.length?r.orders.map(o=>`<tr><td>${labelChannel(o.channel)}</td><td dir="ltr">${esc(o.external_id)}</td><td><span class="tag ${o.status}">${labelStatus(o.status)}</span></td><td dir="ltr">${fmt(o.total)}</td><td>${o.revision}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">لا توجد بيانات بعد. أنشئ فاتورة من الكاشير أو المتجر.</td></tr>';
 $('events').innerHTML=e.events.length?e.events.slice(0,25).map(v=>`<div class="event"><div class="row"><code>${esc(v.event_id)}</code><span class="tag">مستلم</span></div><small>${esc(v.event_type)} · ${esc(v.received_at)}</small></div>`).join(''):'<div class="empty">الاستقبال بانتظار أول حدث</div>';
}
function setupInbox(){
  $('refresh').addEventListener('click',()=>loadInbox().catch(e=>toast(e.message,true)));
  loadInbox().catch(e=>toast(e.message,true));setInterval(()=>loadInbox().catch(()=>{}),2500);
}
if(page==='pos'||page==='shop')setupSeller();
else if(page==='admin')setupAdmin();
else if(page==='inbox')setupInbox();
