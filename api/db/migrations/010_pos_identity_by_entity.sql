-- IDRAK Connect — هوية المصدر على مستوى الكيان لا نوع الحدث.
--
-- المشكلة: فاتورة واحدة تمرّ بدورة حياة (بيع ثم مرتجع/إلغاء) تصل بأنواع أحداث
-- مختلفة (sale ثم refund) لكن بنفس external_id. حين كانت الهوية تشمل event_type
-- كان المرتجع يُعدّ سجلّاً جديداً فيُنشئ فاتورة ثانية بنفس الرقم (ازدواج).
-- الحل: الهوية تميّز بالكيان (entity: sales/products/inventory_levels) لا بنوع
-- الحدث — فبيع الفاتورة ومرتجعها وإلغاؤها تشترك في سجلّ منطقي واحد (المرتجع
-- يُحدّث البيع)، بينما يبقى صنف/مخزون بنفس المعرّف مستقلّاً (كيان مختلف).
--
-- idempotent، نفس أعراف 001–009. لا يُنفَّذ على الإنتاج.

-- إزالة ازدواج قديم تحت الهوية الجديدة (نُبقي الأحدث لكل هوية) حتى يُبنى الفهرس.
delete from pos_source_records a
 using pos_source_records b
 where a.org_id = b.org_id and a.provider_code = b.provider_code
   and a.account_ref = b.account_ref and a.entity = b.entity
   and a.external_id = b.external_id
   and (a.updated_at, a.id) < (b.updated_at, b.id);

drop index if exists pos_source_records_identity_key;
create unique index if not exists pos_source_records_identity_key
  on pos_source_records (org_id, provider_code, account_ref, entity, external_id);
