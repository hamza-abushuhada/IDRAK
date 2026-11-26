"""بروتوكول الموصّل (adapter) — الواجهة المشتركة التي يبنى حولها كل موصّل POS.

منطق نقيّ (لا قاعدة بيانات/شبكة هنا). الموصّل مسؤول فقط عن إنتاج أحداث
بالنموذج الموحّد (model.Event)؛ التطبيع والكتابة في قاعدة البيانات
مسؤوليّة الخطّ (pipeline.py) — ما يُبقي كل موصّل جديد صغيراً.

فئات الموصّلات (كلّها تُصدِر نفس Event):
- CloudAdapter      : API/Webhook سحابي (مدعوم معماريّاً، غير منفَّذ).
- LocalAgentAdapter : وكيل محلّي يرسل تغييرات موقّعة (مدعوم معماريّاً، غير منفَّذ).
- FileExportAdapter : ملفّات مصدَّرة تلقائيّاً (يعيد استخدام خطّ الاستيراد؛ غير منفَّذ).
- DemoPOSAdapter    : موصّل مرجعي يعمل بالكامل (demo.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator


@dataclass
class Capabilities:
    initial_import: bool = False
    incremental: bool = False
    webhook: bool = False
    refunds: bool = False
    inventory: bool = False
    secure_submit: bool = False
    file_import: bool = False

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class AdapterContext:
    """سياق التشغيل المُمرَّر للموصّل. لا يحمل أيّ سرّ: الأسرار تُحقَن عبر
    مرجع credential_ref في طبقة أعلى عند تنفيذ موصّلات حقيقية."""
    org_id: str
    config: dict = field(default_factory=dict)
    cursor: dict = field(default_factory=dict)


class POSAdapter:
    """الواجهة الأساسية. الموصّل الحقيقي يرث منها ويملأ الطرق المدعومة.

    لا يصل الموصّل أبداً إلى مؤسسة أخرى: يتلقّى org_id في السياق فقط،
    وكل كتابة في قاعدة البيانات تمرّ عبر الخطّ المعزول بالمؤسسة.
    """

    provider_code: str = "base"
    display_name: str = "POS adapter"
    capabilities: Capabilities = Capabilities()
    implemented: bool = False

    def initial_events(self, ctx: AdapterContext) -> Iterable:
        """الاستيراد التاريخي الأول. يُرجِع تسلسل model.Event."""
        raise NotImplementedError

    def fetch_changes(self, ctx: AdapterContext) -> tuple[list, dict]:
        """المزامنة التزايدية: يُرجِع (أحداث جديدة/محدَّثة، المؤشّر التالي).
        يعتمد على ctx.cursor لجلب ما بعد آخر نقطة فقط (لا إعادة التاريخ كلّه).
        """
        raise NotImplementedError

    def verify_webhook(self, headers: dict, body: bytes, secret: str) -> bool:
        """تحقّق توقيع الـ webhook + حماية إعادة التشغيل. لا يُوجد مستقبِل
        عامّ بلا تحقّق: أيّ موصّل حقيقي يجب أن يملأ هذه قبل الإنتاج."""
        raise NotImplementedError("webhook verification must be implemented per vendor")
