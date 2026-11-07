import clsx from "clsx";
import type { Copy } from "./copy";

type Dash = Copy["solutions"]["items"]["minimarkets"]["dash"];

const SPARK: Record<string, number[]> = {
  minimarkets: [42, 48, 45, 52, 50, 58, 55, 61, 66, 63, 70, 74],
  pharmacies: [60, 58, 62, 64, 61, 66, 68, 65, 70, 72, 71, 75],
  restaurants: [38, 44, 52, 49, 57, 63, 60, 68, 72, 70, 78, 82],
  fashion: [70, 64, 58, 55, 60, 52, 48, 56, 62, 66, 72, 69],
};

export function SolutionDash({ d, slug, title, jd, note }: { d: Dash; slug: string; title: string; jd: string; note: string }) {
  const spark = SPARK[slug] ?? SPARK.minimarkets;
  return (
    <figure className="rounded-[16px] border border-line bg-[#FFFCF7] shadow-[var(--shadow-lift)]" aria-label={`${title} — ${d.shop}`}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <span className="truncate text-[13.5px] font-medium text-ink">{d.shop}</span>
        <span className="shrink-0 rounded-full bg-sand px-2.5 py-0.5 text-[11.5px] text-ink-2">{title}</span>
      </div>
      <dl className="grid grid-cols-3 divide-x divide-line border-b border-line">
        {d.kpis.map((k) => (
          <div key={k.label} className="px-4 py-4">
            <dt className="truncate text-[11.5px] text-ink-3">{k.label}</dt>
            <dd className="num mt-1 truncate text-[19px] text-ink"><bdi>{k.value}</bdi></dd>
            <dd className={clsx("num mt-0.5 text-[11.5px]", k.delta.startsWith("−") ? "text-terra-2" : "text-olive")}><bdi>{k.delta}</bdi></dd>
          </div>
        ))}
      </dl>
      <div className="flex h-[64px] items-end gap-[5px] border-b border-line px-5 pb-3 pt-4" aria-hidden>
        {spark.map((v, i) => (
          <span key={i} className={clsx("flex-1 rounded-t-[2px]", i === spark.length - 1 ? "bg-terra" : "bg-ink/15")} style={{ height: `${v}%` }} />
        ))}
      </div>
      <div className="px-5 pb-2 pt-4">
        <p className="text-[12px] text-ink-3">{d.listTitle}</p>
        <ul className="mt-2">
          {d.rows.map((r) => (
            <li key={r.name} className="flex items-center gap-3 border-b border-line/70 py-2.5 last:border-0">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] text-ink"><bdi>{r.name}</bdi></p>
                <p className="truncate text-[12px] text-ink-3">{r.meta}</p>
              </div>
              {"flag" in r && r.flag && <span className="hidden shrink-0 rounded-full bg-terra-soft px-2 py-0.5 text-[11px] text-terra-2 sm:inline">{r.flag}</span>}
              <span className="num shrink-0 text-[13.5px] text-ink">{r.value} <span className="text-[10.5px] text-ink-3">{jd}</span></span>
            </li>
          ))}
        </ul>
      </div>
      <figcaption className="border-t border-dashed border-line px-5 py-2.5 text-[11.5px] text-ink-3">{note}</figcaption>
    </figure>
  );
}
