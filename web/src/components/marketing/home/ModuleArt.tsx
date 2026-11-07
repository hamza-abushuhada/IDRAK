import clsx from "clsx";
import type { Copy } from "../copy";
import { Arrow, monoAr } from "../primitives";

export function ModuleArt({ k, a, jd }: { k: string; a: Copy["modules"]["art"]; jd: string }) {
  const shell = "relative h-[150px] overflow-hidden rounded-[12px] border p-4";
  const box = `${shell} border-line bg-paper-2`;
  switch (k) {
    case "cleaning":
      return (
        <div className={box} aria-hidden>
          <div className="flex items-center gap-2 font-mono text-[13px]" dir="rtl">
            {["أ", "إ", "آ", "ا"].map((ch) => (
              <span key={ch} className="flex size-8 items-center justify-center rounded-md border border-line bg-[#FFFCF7] font-sans text-[16px] text-ink">{ch}</span>
            ))}
            <span className="px-1 text-ink-3">←</span>
            <span className="flex size-8 items-center justify-center rounded-md bg-olive-soft font-sans text-[16px] text-ink">ا</span>
          </div>
          <div className="mt-3 space-y-1.5 font-mono text-[12.5px]">
            <div className="flex items-center gap-2"><bdi className="rounded bg-terra-soft/70 px-1.5 text-terra-2 line-through decoration-terra/40">٠٧٩٥٥٥١٢٣٤</bdi><Arrow size={12} className="text-ink-3" /><bdi className="rounded bg-olive-soft px-1.5 text-ink">+962 79 555 1234</bdi></div>
            <div className="flex items-center gap-2"><bdi className="rounded bg-terra-soft/70 px-1.5 text-terra-2 line-through decoration-terra/40">350</bdi><Arrow size={12} className="text-ink-3" /><bdi className="rounded bg-olive-soft px-1.5 text-ink">0.350</bdi></div>
          </div>
        </div>
      );
    case "leaks":
      return (
        <div className={clsx(box, "py-3")} aria-hidden>
          <ul className="divide-y divide-line/80">
            {a.leaks.map((l, i) => (
              <li key={l.name} className="flex items-center justify-between py-[5px] text-[12.5px]">
                <span className={i === 0 ? "font-medium text-ink" : "text-ink-2"}>{l.name}</span>
                <span className={clsx("num", i === 0 ? "text-terra-2" : "text-ink-2")}>{l.value} <span className="text-[10.5px] text-ink-3">{jd}</span></span>
              </li>
            ))}
          </ul>
        </div>
      );
    case "forecast": {
      const bars = [34, 38, 36, 41, 39, 62, 78, 84, 71, 92, 58, 40];
      return (
        <div className={clsx(box, "flex flex-col justify-end")} aria-hidden>
          <div className="absolute inset-y-3 start-[39%] w-[34%] rounded-md bg-saffron-soft" />
          <span className="absolute start-[41%] top-4 text-[11px] font-medium text-[#8a5d0e]">{a.ramadan}</span>
          <span className="absolute end-[15%] top-4 text-[11px] font-medium text-olive">{a.eid}</span>
          <div className="relative flex h-[96px] items-end gap-[5px]">
            {bars.map((h, i) => (
              <span key={i} className={clsx("flex-1 rounded-t-[3px]", i === 9 ? "bg-olive" : i >= 5 && i <= 8 ? "bg-saffron" : "bg-ink/20")} style={{ height: `${h}%` }} />
            ))}
          </div>
          <div className="relative mt-1 h-px bg-ink/30" />
        </div>
      );
    }
    case "customers": {
      const cells = [0.9, 0.7, 0.45, 0.75, 0.55, 0.3, 0.4, 0.25, 0.12];
      return (
        <div className={clsx(box, "flex items-center gap-4")} aria-hidden>
          <div className="grid size-[110px] shrink-0 grid-cols-3 gap-1">
            {cells.map((o, i) => <span key={i} className="rounded-[4px] bg-olive" style={{ opacity: o }} />)}
          </div>
          <ul className="space-y-2 text-[12.5px]">
            {a.segments.map((s, i) => (
              <li key={s} className="flex items-center gap-2 text-ink-2">
                <span className={clsx("size-2 rounded-full", i === 0 ? "bg-olive" : i === 1 ? "bg-olive/55" : "bg-terra")} />
                {s}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "compliance":
      return (
        <div className={clsx(box, "flex flex-col justify-center gap-2.5")} aria-hidden>
          {a.checks.map((c) => (
            <div key={c.label} className="flex items-center gap-2.5 text-[12.5px]">
              <span className={clsx("flex size-[18px] shrink-0 items-center justify-center rounded-full text-[11px] font-semibold", c.ok ? "bg-olive-soft text-olive" : "bg-terra-soft text-terra-2")}>{c.ok ? "✓" : "!"}</span>
              <span className={c.ok ? "text-ink-2" : "font-medium text-ink"}>{c.label}</span>
              {"meta" in c && c.meta && <span className="ms-auto rounded-full bg-terra-soft px-2 py-0.5 text-[11px] text-terra-2">{c.meta}</span>}
            </div>
          ))}
        </div>
      );
    case "assistant":
      return (
        <div className={clsx(shell, "border-cocoa bg-cocoa font-mono text-[12.5px] leading-relaxed text-paper/90")} aria-hidden>
          <p dir="rtl" className="font-sans text-paper"><span className="me-2 font-mono text-terra">›</span>{a.ask}</p>
          <p className="mt-2 flex gap-2"><span className="text-saffron">●</span><span dir="auto" className={monoAr}>{a.answer}</span></p>
          <p className="mt-1 text-paper/45"><span className="me-2">⎿</span>query sales · Khalda · week 11</p>
          <span className="caret mt-1 inline-block text-paper/40" />
        </div>
      );
    default:
      return null;
  }
}
