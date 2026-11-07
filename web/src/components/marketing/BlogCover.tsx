import clsx from "clsx";
import { monoAr } from "./primitives";

export function BlogCover({ slug, className }: { slug: string; className?: string }) {
  const base = clsx("relative flex overflow-hidden rounded-[14px] border border-line", className);
  if (slug === "why-your-pos-reports-lie") {
    return (
      <div className={clsx(base, "flex-col justify-center gap-2 bg-terra-soft/70 p-6")} aria-hidden>
        {["بيبسي 330", "ببسي ٣٣٠", "PEPSI 330ML", "Pepsi can"].map((v, i) => (
          <span key={v} dir="auto" className={clsx(monoAr, "w-fit rounded-md border border-terra/25 bg-[#FFFCF7] px-2.5 py-1 text-[14px] text-ink", i % 2 ? "ms-8" : "ms-0")} style={{ transform: `rotate(${i % 2 ? 1.5 : -1.2}deg)` }}>
            {v}
          </span>
        ))}
        <span dir="ltr" className="absolute bottom-4 end-5 font-serif text-[46px] leading-none text-terra-2">=1</span>
      </div>
    );
  }
  if (slug === "ramadan-stock-planning") {
    const bars = [30, 34, 31, 36, 58, 72, 80, 94, 66, 40];
    return (
      <div className={clsx(base, "flex-col justify-end bg-saffron-soft/80 p-6")} aria-hidden>
        <span className="absolute start-6 top-5 font-serif text-[46px] leading-none text-[#8a5d0e]">1448</span>
        <div className="flex h-[55%] items-end gap-1.5">
          {bars.map((v, i) => <span key={i} className={clsx("flex-1 rounded-t-[3px]", i >= 4 && i <= 7 ? "bg-saffron" : "bg-ink/15")} style={{ height: `${v}%` }} />)}
        </div>
        <span className="mt-1 h-px bg-ink/40" />
      </div>
    );
  }
  return (
    <div className={clsx(base, "items-center justify-center gap-6 bg-olive-soft/80 p-6")} aria-hidden>
      <div className="grid grid-cols-7 gap-[3px]">
        {Array.from({ length: 49 }).map((_, i) => (
          <span key={i} className={clsx("size-[9px] rounded-[1px]", (i * 7 + (i % 5) * 3) % 3 === 0 || [0, 1, 2, 7, 14, 15, 16, 4, 5, 6, 13, 20, 18, 19, 28, 29, 30, 35, 42, 43, 44].includes(i) ? "bg-ink" : "bg-transparent")} />
        ))}
      </div>
      <div className="space-y-2">
        {["✓", "✓", "!"].map((m, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={clsx("flex size-5 items-center justify-center rounded-full text-[11px] font-semibold", m === "!" ? "bg-terra-soft text-terra-2" : "bg-paper text-olive")}>{m}</span>
            <span className="h-2 rounded-full bg-ink/20" style={{ width: [72, 56, 64][i] }} />
          </div>
        ))}
      </div>
    </div>
  );
}
