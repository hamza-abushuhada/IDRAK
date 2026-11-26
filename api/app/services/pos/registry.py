"""سجلّ المزوّدين: يربط provider_code بصنف الموصّل المنفَّذ.

منطق نقيّ (لا قاعدة بيانات). كتالوج العرض نفسه يُقرأ من جدول pos_providers،
لكن ربط الكود بالتنفيذ الفعلي يعيش هنا — فالموصّل غير المنفَّذ لا يملك صنفاً
هنا، وبذلك تميّز الواجهة والخطّ بوضوح بين «منفَّذ» و«مدعوم معماريّاً فقط».
"""

from __future__ import annotations

try:
    from . import demo, lab
except ImportError:  # pragma: no cover
    import demo  # type: ignore
    import lab  # type: ignore

# provider_code → صنف الموصّل. تُضاف الموصّلات الحقيقية هنا عند تنفيذها.
REGISTRY: dict[str, type] = {
    "demo": demo.DemoPOSAdapter,
    "lab_pos": lab.LabPOSAdapter,
    "lab_web": lab.LabWebAdapter,
}


def get_adapter_class(provider_code: str) -> type | None:
    return REGISTRY.get(provider_code)


def is_implemented(provider_code: str) -> bool:
    return provider_code in REGISTRY
