import { ArrowRight, Undo2 } from "lucide-react";
import type { Locale } from "@/i18n/config";
import { getCopy } from "../copy";
import { Arrow, monoAr } from "../primitives";

export function HeroStill({ locale }: { locale: Locale }) {
  const s = getCopy(locale).hero.still;
  return (
    <figure className="relative mx-auto w-full max-w-[520px] lg:ms-auto" aria-label={s.app}>
      <div className="flex items-end justify-between gap-3 ps-4">
        <span dir="ltr" className="truncate rounded-t-[10px] border border-b-0 border-line bg-sand px-3.5 pb-1.5 pt-2 font-mono text-[11.5px] text-ink-2">
          {s.file}
        </span>
        <span className="pb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3 rtl:font-sans rtl:text-[12px] rtl:tracking-normal">{s.app}</span>
      </div>

      <div className="relative rounded-[14px] rounded-ss-none border border-line bg-[#FFFCF7] shadow-[var(--shadow-lift)]">
        <div className="flex items-center gap-5 border-b border-line px-5 py-4 sm:px-6">
          <div className="min-w-0 flex-1">
            <p className="text-[12.5px] text-ink-3">{s.scoreLabel}</p>
            <div className="mt-1 flex items-baseline gap-3" dir="ltr">
              <span className="num text-[22px] text-terra line-through decoration-1">42</span>
              <ArrowRight size={14} className="self-center text-ink-3" aria-hidden />
              <span className="num text-[38px] font-medium leading-none text-olive">97</span>
              <span className="num text-[12px] text-ink-3">/100</span>
            </div>
          </div>
          <div className="w-[42%] max-w-[180px]" aria-hidden>
            <div className="relative h-2 rounded-full bg-sand">
              <div className="absolute inset-y-0 start-0 rounded-full bg-olive/80" style={{ width: "96%" }} />
              <div className="absolute inset-y-0 start-0 rounded-full bg-terra" style={{ width: "34%" }} />
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] text-ink-3">
              <span>{s.before}</span>
              <span>{s.after}</span>
            </div>
          </div>
        </div>

        <ul className="divide-y divide-line/70">
          {s.rows.map((r, i) => (
            <li key={i} className="px-5 py-3 sm:px-6">
              <div className="flex items-center justify-between gap-3 text-[11.5px]">
                <span className="font-mono uppercase tracking-[0.12em] text-ink-3 rtl:font-sans rtl:text-[12px] rtl:tracking-normal">{r.col}</span>
                <span className="text-ink-3">{r.why}</span>
              </div>
              <div className="mt-1.5 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                <span className={`truncate rounded-md bg-terra-soft/70 px-2 py-1 ${monoAr} text-[13px] text-terra-2 line-through decoration-terra/50`}><bdi>{r.before}</bdi></span>
                <Arrow size={13} className="text-ink-3" />
                <span className={`truncate rounded-md bg-olive-soft px-2 py-1 ${monoAr} text-[13px] font-medium text-ink`}><bdi>{r.after}</bdi></span>
              </div>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3.5 sm:px-6">
          <span className="text-[12.5px] text-ink-2">{s.footer}</span>
          <div className="flex items-center gap-2" aria-hidden>
            <span className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[12.5px] text-ink-2">
              <Undo2 size={13} className="rtl:-scale-x-100" /> {s.undo}
            </span>
            <span className="inline-flex h-8 items-center rounded-full bg-ink px-3.5 text-[12.5px] text-paper">{s.approve}</span>
          </div>
        </div>
      </div>

      <figcaption className="relative z-10 mx-4 -mt-2 rotate-[-1.2deg] rounded-[10px] border border-saffron/30 bg-saffron-soft px-4 py-3 shadow-[var(--shadow-paper)] sm:mx-0 sm:-ms-6 sm:w-[310px] lg:-ms-14">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-[#8a5d0e] rtl:font-sans rtl:text-[12px] rtl:font-semibold rtl:tracking-normal">{s.memoryLabel}</p>
        <p className="mt-1 text-[14px] leading-snug text-ink">{s.memory}</p>
        <p className="mt-1 text-[12px] text-ink-2">{s.memoryMeta}</p>
      </figcaption>
    </figure>
  );
}
