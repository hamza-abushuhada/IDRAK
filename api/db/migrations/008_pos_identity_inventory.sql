-- IDRAK Connect — إصلاح الهوية الثابتة للمصدر + الأرصدة الافتتاحية للمخزون.
--
-- المشكلة (1): التكرار عند إعادة الربط. كانت الـ idempotency مربوطة بـ
-- connection_id، فإعادة ربط نفس المصدر (connection_id جديد) تعيد استيراد كل شيء.
-- الحل: هوية ثابتة = (org_id, provider_code, account_ref, event_type, external_id)
-- مستقلّة تماماً عن connection_id — فتتحقّق الـ idempotency عبر الاتصالات المختلفة.
--
-- المشكلة (2): مخزون صفر. لم تكن هناك أرصدة افتتاحية. تُعالَج في الموصّل
-- (أحداث مخزون افتتاحية) والخطّ (تحريك المخزون عند البيع/المرتجع)، بلا تغيير سكيمة
-- إضافي هنا — inventory_levels الموجود يكفي (unique(branch_id,product_id)).
--
-- idempotent بالكامل (if exists / if not exists)، نفس أعراف 001–007.
-- تحذير: لا يُنفَّذ على قاعدة إنتاج قبل المراجعة.

-- حساب/تاجر المصدر: هوية ثابتة على الاتصال تبقى عبر قطع/إعادة الربط.
-- للموصّل التجريبي 'demo'؛ للمورّد الحقيقي يُشتقّ من إعدادات/اعتماد الاتصال.
alter table pos_connections add column if not exists account_ref text not null default 'default';

-- هوية المصدر على سجلّات المصدر: مستقلّة عن connection_id.
alter table pos_source_records add column if not exists provider_code text;
alter table pos_source_records add column if not exists account_ref text;

-- تعبئة رجعيّة من الاتصال المرتبط.
update pos_source_records sr
   set provider_code = c.provider_code, account_ref = c.account_ref
  from pos_connections c
 where sr.connection_id = c.id
   and (sr.provider_code is null or sr.account_ref is null);

-- أي سجلّات يتيمة (نادرة): قيم آمنة حتى يصحّ قيد NOT NULL.
update pos_source_records
   set provider_code = coalesce(provider_code, 'unknown'),
       account_ref   = coalesce(account_ref, 'default')
 where provider_code is null or account_ref is null;

alter table pos_source_records alter column provider_code set not null;
alter table pos_source_records alter column account_ref set default 'default';
alter table pos_source_records alter column account_ref set not null;

-- إزالة أي ازدواج قديم في خريطة المصدر (ناتج عن علّة الربط بـ connection_id)
-- حتى يُبنى الفهرس الفريد على قاعدة «متّسخة»: نُبقي الأحدث لكل هوية. خريطة
-- المصدر جدول ربط لا سجلّ ماليّ، فحذف المكرّر منها آمن.
-- ملاحظة: الفواتير المكرّرة في sales الناتجة عن العلّة القديمة تُنظَّف بعملية
-- منفصلة موثّقة (reconnect_cleanup) لا ضمن هجرة سكيمة.
delete from pos_source_records a
 using pos_source_records b
 where a.org_id = b.org_id and a.provider_code = b.provider_code
   and a.account_ref = b.account_ref and a.event_type = b.event_type
   and a.external_id = b.external_id
   and (a.updated_at, a.id) < (b.updated_at, b.id);

-- تبديل التفرّد من نطاق الاتصال إلى نطاق هوية المصدر.
alter table pos_source_records
  drop constraint if exists pos_source_records_connection_id_event_type_external_id_key;
create unique index if not exists pos_source_records_identity_key
  on pos_source_records (org_id, provider_code, account_ref, event_type, external_id);

-- بحث سريع عن اتصال موجود لنفس (مؤسسة، مزوّد، حساب) عند إعادة الربط.
create index if not exists pos_connections_account_idx
  on pos_connections (org_id, provider_code, account_ref);
