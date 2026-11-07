"use client";
import { useState } from "react";
import clsx from "clsx";
import { Check, Minus } from "lucide-react";
import { Button } from "@/components/ui";
import { useCopy } from "./use-copy";
import { lh } from "./copy";
import { Arrow, Container } from "./primitives";

export function PricingPlans() {
  const { c, locale } = useCopy();
  const P = c.pricing;
  const [yearly, setYearly] = useState(false);

  return (
    <>
      <Container className="-mt-4">
        <div role="radiogroup" aria-label={`${P.monthly} / ${P.yearly}`} className="inline-flex items-center rounded-full border border-line bg-[#FFFCF7] p-1">
          {[false, true].map((y) => (
            <button
              key={String(y)}
              role="radio"
              aria-checked={yearly === y}
              onClick={() => setYearly(y)}
              className={clsx(
                "inline-flex h-10 items-center gap-2 rounded-full px-5 text-[14px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-terra",
                yearly === y ? "bg-ink text-paper" : "text-ink-2 hover:text-ink",
              )}
            >
              {y ? P.yearly : P.monthly}
              {y && <span className={clsx("rounded-full px-2 py-0.5 text-[11.5px] font-medium", yearly ? "bg-paper/15 text-paper" : "bg-olive-soft text-olive")}>{P.save}</span>}
            </button>
          ))}
        </div>

        <ul className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-3">
          {c.plans.items.map((p) => {
            const pop = p.key === "growth";
            const price = yearly ? p.monthly * 10 : p.monthly;
            const eq = (Math.round(((p.monthly * 10) / 12) * 10) / 10).toFixed(1);
            return (
              <li
                key={p.key}
                className={clsx(
                  "relative flex flex-col rounded-[18px] border p-7 sm:p-8",
                  pop ? "border-ink bg-[#FFFCF7] shadow-[var(--shadow-lift)]" : "border-line bg-paper",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <h2 className="font-serif text-[26px] text-ink rtl:font-semibold">{p.name}</h2>
                  {pop && <span className="rounded-full bg-terra px-3 py-1 text-[12px] font-medium text-paper">{c.plans.popular}</span>}
                </div>
                <p className="mt-2 min-h-[3em] text-[15px] leading-snug text-ink-2">{p.tagline}</p>
                <p className="mt-6 flex items-baseline gap-2">
                  <span className="num text-[52px] leading-none tracking-tight text-ink">{price}</span>
                  <span className="text-[15px] text-ink-2">{c.common.jd} {yearly ? P.perYear : P.perMonth}</span>
                </p>
                <p className="mt-2 h-5 text-[13px] text-ink-3">{yearly ? P.equivalent.replace("{price}", eq) : P.billedMonthly}</p>
                <Button href={lh(locale, `/signup?plan=${p.key}${yearly ? "&billing=yearly" : ""}`)} variant={pop ? "primary" : "secondary"} size="lg" className="mt-7 w-full">
                  {P.cta} <Arrow size={15} />
                </Button>
                <ul className="mt-8 space-y-3 border-t border-line pt-6">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-3 text-[15px] text-ink-2">
                      <Check size={16} className="mt-[3px] shrink-0 text-olive" aria-hidden />
                      {f}
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      </Container>

      <Container className="py-20 sm:py-28">
        <h2 id="compare" className="font-serif text-[32px] font-[400] tracking-[-0.018em] text-ink sm:text-[40px] rtl:font-semibold rtl:tracking-normal">{P.compareTitle}</h2>
        <div className="relative mt-8 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-start">
            <caption className="sr-only">{P.compareTitle}</caption>
            <thead>
              <tr className="border-b border-ink/80">
                <th scope="col" className="w-[40%] py-4 pe-4 text-start text-[13px] font-normal text-ink-3">{P.feature}</th>
                {c.plans.items.map((p) => (
                  <th key={p.key} scope="col" className={clsx("px-4 py-4 text-start", p.key === "growth" && "bg-paper-2")}>
                    <span className="block font-serif text-[19px] font-normal text-ink rtl:font-semibold">{p.name}</span>
                    <span className="num text-[13px] font-normal text-ink-3">{yearly ? p.monthly * 10 : p.monthly} {c.common.jd}</span>
                  </th>
                ))}
              </tr>
            </thead>
            {P.groups.map((g) => (
              <tbody key={g.name}>
                <tr>
                  <th colSpan={4} scope="colgroup" className="pb-2 pt-8 text-start font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-terra rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{g.name}</th>
                </tr>
                {g.rows.map((r) => (
                  <tr key={r.label} className="border-b border-line">
                    <th scope="row" className="py-3.5 pe-4 text-start text-[15px] font-normal text-ink">{r.label}</th>
                    {r.values.map((v, i) => (
                      <td key={i} className={clsx("px-4 py-3.5 text-[14.5px] text-ink-2", i === 1 && "bg-paper-2")}>
                        {v === true ? (
                          <><Check size={17} className="text-olive" aria-hidden /><span className="sr-only">{P.yes}</span></>
                        ) : v === false ? (
                          <><Minus size={17} className="text-ink-3/50" aria-hidden /><span className="sr-only">{P.no}</span></>
                        ) : (
                          <span className={/^[\d,]+$/.test(String(v)) ? "num text-ink" : ""}>{v}</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-6 rounded-[18px] border border-line bg-paper-2 p-7 sm:p-10 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-8">
            <h2 className="font-serif text-[26px] leading-snug text-ink sm:text-[30px] rtl:font-semibold">{P.enterprise.title}</h2>
            <p className="mt-3 max-w-[56ch] text-[16px] leading-relaxed text-ink-2">{P.enterprise.body}</p>
          </div>
          <div className="lg:col-span-4 lg:text-end">
            <Button href={lh(locale, "/contact")} size="lg" variant="secondary">{P.enterprise.cta} <Arrow size={15} /></Button>
          </div>
        </div>
      </Container>
    </>
  );
}
