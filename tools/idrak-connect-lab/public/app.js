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
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});
  const data=await r.json();
  if(!r.ok)throw new Error(data.error||`HTTP ${r.status}`);
  return data;
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
