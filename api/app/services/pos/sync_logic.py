"""منطق القرار النقيّ لخطّ المزامنة: idempotency، الأحداث خارج الترتيب،
والمطابقة (reconciliation). لا يلمس قاعدة البيانات ولا الشبكة — قابل
للاختبار بـ `python -I` وحده.

الخطّ الفعلي (pipeline.py) يقرأ حالة السجلّ الموجود من pos_source_records،
يستدعي decide()، ثم ينفّذ الإجراء في قاعدة البيانات داخل معاملة.
"""

from __future__ import annotations

from dataclasses import dataclass

# الإجراءات الممكنة لكل حدث وارد.
INSERT = "insert"              # سجلّ جديد — يُدرَج
UPDATE = "update"             # محتوى مختلف وأحدث — يُحدَّث
SKIP_DUPLICATE = "skip_duplicate"  # نفس البصمة — تكرار يُتخطّى (idempotency)
SKIP_STALE = "skip_stale"     # إصدار أقدم من المخزَّن — حدث متأخّر يُتجاهَل


@dataclass(frozen=True)
class ExistingRecord:
    """لقطة الحالة المخزَّنة في pos_source_records لحدث سبق استقباله."""
    content_hash: str
    source_version: str = ""


def _version_lt(incoming: str, existing: str) -> bool:
    """هل الإصدار الوارد أقدم من المخزَّن؟ يقارن رقميّاً إن كان الطرفان عدّادين
    صحيحين (فلا تكسر "12" < "8" الترتيب)، وإلا نصّيّاً (ISO timestamps مبطّنة
    تترتّب معجميّاً بشكل صحيح)."""
    if incoming.isdigit() and existing.isdigit():
        return int(incoming) < int(existing)
    return incoming < existing


def decide(existing: ExistingRecord | None, incoming_hash: str, incoming_version: str = "") -> str:
    """القرار المركزي للـ idempotency ومعالجة خارج الترتيب.

    - لا سجلّ سابق            → INSERT
    - نفس البصمة             → SKIP_DUPLICATE (إعادة تسليم حرفيّة)
    - بصمة مختلفة وإصدار أحدث → UPDATE
    - بصمة مختلفة وإصدار أقدم → SKIP_STALE (حدث متأخّر؛ المخزَّن أحدث)
    - بصمة مختلفة وإصدار مساوٍ/غير معروف → UPDATE (آخر كتابة تفوز)

    مقارنة الإصدارات نصّية؛ ISO timestamps وأرقام العدّادات المبطّنة بالأصفار
    تترتّب معجميّاً بشكل صحيح.
    """
    if existing is None:
        return INSERT
    if existing.content_hash == incoming_hash:
        return SKIP_DUPLICATE
    ev, iv = (existing.source_version or ""), (incoming_version or "")
    if ev and iv and _version_lt(iv, ev):
        return SKIP_STALE
    return UPDATE


@dataclass
class SyncCounts:
    """حصيلة محاولة مزامنة — تُسجَّل في pos_sync_jobs.counts."""
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0

    def record(self, action: str) -> None:
        if action == INSERT:
            self.imported += 1
        elif action == UPDATE:
            self.updated += 1
        elif action in (SKIP_DUPLICATE, SKIP_STALE):
            self.skipped += 1

    def as_dict(self) -> dict:
        return {"imported": self.imported, "updated": self.updated,
                "skipped": self.skipped, "failed": self.failed}

    def status(self) -> str:
        """حالة المهمّة الكلّية: partial إن نجح بعضها وفشل بعض، success/failed غير ذلك."""
        if self.failed and (self.imported or self.updated or self.skipped):
            return "partial"
        if self.failed:
            return "failed"
        return "success"


def reconcile(expected: int | None, present: int) -> dict:
    """مطابقة بسيطة لاكتشاف الفجوات: يقارن ما يُفترَض وجوده (من المصدر) بما
    هو موجود فعلاً، ويُبلّغ عن العجز إن وُجد. تُستدعى بعد المزامنة لرصد
    الأحداث المفقودة والتعافي منها.
    """
    if expected is None:
        return {"expected": None, "present": present, "missing": 0, "ok": True}
    missing = max(0, expected - present)
    return {"expected": expected, "present": present, "missing": missing, "ok": missing == 0}
