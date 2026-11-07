"use client";
import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { useCopy } from "../use-copy";
import { Container, Kicker } from "../primitives";

export function AssistantShowcase() {
  const { c, locale } = useCopy();
  const a = c.assistant;
  const T = a.terminal;
  const S = a.screen;
  const total = T.lines.length;

  const ref = useRef<HTMLDivElement>(null);
  const [typed, setTyped] = useState(T.question.length);
  const [shown, setShown] = useState(total);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const el = ref.current;
    if (reduce || !el) return;
    setTyped(0);
    setShown(0);
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setStarted(true);
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!started) return;
    let cancelled = false;
    const timers: number[] = [];
    const q = T.question;
    for (let i = 1; i <= q.length; i++) timers.push(window.setTimeout(() => !cancelled && setTyped(i), 380 + i * 38));
    let t = 380 + q.length * 38 + 450;
    T.lines.forEach((l, i) => {
      t += l.t === "tool" ? 420 : 720;
      timers.push(window.setTimeout(() => !cancelled && setShown(i + 1), t));
    });
    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, [started, T]);

  const done = shown >= total;

  return (
    <section id="assistant" aria-labelledby="assistant-title" className="scroll-mt-20 border-b border-line">
      <Container className="grid grid-cols-1 gap-14 py-20 sm:py-28 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-5 lg:pt-6">
          <Kicker className="mb-4">{a.kicker}</Kicker>
          <h2 id="assistant-title" className="font-serif text-[32px] font-[400] leading-[1.1] tracking-[-0.018em] text-ink text-balance sm:text-[44px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{a.title}</h2>
          <p className="mt-6 max-w-[44ch] text-[17px] leading-[1.65] text-ink-2">{a.body}</p>
          <ul className="mt-8 space-y-3 border-t border-line pt-6">
            {a.bullets.map((b) => (
              <li key={b} className="flex gap-3 text-[15.5px] text-ink-2">
                <span aria-hidden className="mt-[7px] size-2 shrink-0 rounded-full bg-saffron" />
                {b}
              </li>
            ))}
          </ul>
        </div>

        <div ref={ref} className="lg:col-span-7">
          <div className="overflow-hidden rounded-[14px] border border-cocoa bg-cocoa text-paper shadow-[var(--shadow-lift)]" role="img" aria-label={`${T.question} — ${T.lines.filter((l) => l.t !== "tool").map((l) => l.text).join(" ")}`}>
            <div className="flex items-center justify-between border-b border-paper/10 px-5 py-3 font-mono text-[11.5px] text-paper/50" dir="ltr">
              <span>{T.title}</span>
              <span className="rounded-full border border-paper/15 px-2.5 py-0.5 text-paper/70"><bdi>{T.branch}</bdi></span>
            </div>
            <div className="min-h-[392px] px-5 py-5 font-mono text-[13.5px] leading-[1.75] sm:px-6 sm:pb-14" aria-hidden>
              <p className="flex gap-3 text-paper">
                <span className="text-terra">›</span>
                <span dir="rtl" className="font-sans text-[15px]">
                  {T.question.slice(0, typed)}
                  {typed < T.question.length && <span className="caret" />}
                </span>
              </p>
              {T.gloss && typed >= T.question.length && <p className="ms-6 font-sans text-[13px] text-paper/45">{T.gloss}</p>}
              <div className="mt-4 space-y-1">
                {T.lines.slice(0, shown).map((l, i) => (
                  <p
                    key={i}

                    className={clsx(
                      "flex gap-3 animate-[fadeUp_.35s_ease-out_both]",
                      l.t === "tool" && "text-[12.5px] text-paper/45",
                      l.t === "bullet" && "mt-3 text-paper first:mt-0",
                      l.t === "plain" && "text-paper/85",
                    )}
                  >
                    <span className={clsx("w-4 shrink-0 text-center", l.t === "bullet" ? "text-saffron" : l.t === "tool" ? "text-paper/35" : "")}>
                      {l.t === "bullet" ? "●" : l.t === "tool" ? "⎿" : ""}
                    </span>
                    <span dir={l.t === "tool" ? "ltr" : undefined} className={clsx(locale === "ar" && l.t !== "tool" && "font-sans text-[14.5px]")}>{l.text}</span>
                  </p>
                ))}
              </div>
              <div className="mt-6 flex items-center gap-3 border-t border-paper/10 pt-4 text-paper/35">
                <span className="text-terra/70">›</span>
                <span className={clsx(locale === "ar" && "font-sans")}>{T.inputPlaceholder}</span>
                {done && <span className="caret" />}
              </div>
            </div>
          </div>

          <div className="relative z-10 mx-3 -mt-10 rounded-[14px] border border-line bg-[#FFFCF7] p-5 shadow-[var(--shadow-lift)] sm:ms-auto sm:me-[-12px] sm:w-[82%] sm:p-6" aria-label={S.crumbs}>
            <p className="text-[12px] text-ink-3">{S.crumbs}</p>
            <p className="mt-1 font-serif text-[21px] text-ink rtl:font-semibold">
              {S.product} <span className="font-sans text-[14px] text-ink-3">· <bdi>{S.productAlt}</bdi></span>
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-3">
              {[
                { k: S.cost, v: "1.200", hl: false },
                { k: S.price, v: "0.850", hl: true },
                { k: S.units, v: "175", hl: false },
                { k: S.lost, v: "61.250", hl: false, terra: true },
              ].map((f) => (
                <div
                  key={f.k}
                  className={clsx("relative rounded-[10px] border border-line bg-paper px-3.5 py-3 transition-shadow", f.hl && done && "basira-highlight")}
                >
                  <dt className="text-[12px] text-ink-3">{f.k}</dt>
                  <dd className={clsx("num mt-1 text-[20px]", f.terra ? "text-terra-2" : "text-ink")}>
                    {f.v} {f.k !== S.units && <span className="text-[11px] text-ink-3">{c.common.jd}</span>}
                  </dd>
                  {f.hl && done && (
                    <span className="absolute -top-3 end-3 rounded-full bg-saffron px-2 py-0.5 text-[10.5px] font-medium text-ink">{S.highlight}</span>
                  )}
                </div>
              ))}
            </dl>
            <p className="mt-4 border-t border-line pt-3 text-[13.5px] text-ink-2">{S.fix}</p>
          </div>
        </div>
      </Container>
      <style>{`@keyframes fadeUp{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}@media (prefers-reduced-motion: reduce){.animate-\\[fadeUp_\\.35s_ease-out_both\\]{animation:none}}`}</style>
    </section>
  );
}
