"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import clsx from "clsx";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useCopy } from "../use-copy";
import type { Copy } from "../copy";
import { Container, Kicker, monoAr } from "../primitives";

type Kind = "dup" | "fmt" | "ar" | "fils" | "sp" | "miss";
const MESSY: { v: string; k: Kind; x: number; y: number; r: number }[] = [
  { v: "ببسي ٣٣٠", k: "dup", x: 2, y: 2, r: -2 },
  { v: "PEPSI 330ML", k: "dup", x: 38, y: 6, r: 1.5 },
  { v: "Pepsi can", k: "dup", x: 70, y: 0, r: -1 },
  { v: "07 9555 1234", k: "fmt", x: 0, y: 22, r: 1 },
  { v: "00962781204471", k: "fmt", x: 44, y: 25, r: -1.5 },
  { v: "١٥/٠٣/٢٠٢٦", k: "ar", x: 6, y: 42, r: -1 },
  { v: "3/12/26", k: "fmt", x: 46, y: 44, r: 2 },
  { v: "15 رمضان 1447", k: "ar", x: 72, y: 40, r: -2 },
  { v: "350", k: "fils", x: 0, y: 62, r: 1.5 },
  { v: "4650", k: "fils", x: 26, y: 64, r: -1 },
  { v: "1.25 JD", k: "fmt", x: 52, y: 61, r: 1 },
  { v: "حليب المراعى", k: "sp", x: 74, y: 66, r: -1.5 },
  { v: "لبنه الطيبه", k: "sp", x: 4, y: 82, r: -1 },
  { v: "٠٧٧٩٠٣٢٢١٠", k: "ar", x: 38, y: 84, r: 1.5 },
  { v: "—", k: "miss", x: 76, y: 86, r: 0 },
];
const CLEAN = [
  { item: "Pepsi 330ml", jd: "0.350", date: "2026-03-15", phone: "+962 79 555 1234" },
  { item: "حليب المراعي 1L", jd: "0.950", date: "2026-03-05", phone: "+962 78 120 4471" },
  { item: "Nescafé Gold 200g", jd: "4.650", date: "2026-03-12", phone: "+962 77 903 2210" },
  { item: "لبنة الطيبة 1kg", jd: "2.900", date: "2026-03-18", phone: null },
  { item: "Kinder Joy", jd: "1.250", date: "2026-03-20", phone: "+962 79 640 0918" },
];

const kindCls: Record<Kind, string> = {
  dup: "border-terra/35 bg-terra-soft/60",
  fmt: "border-line bg-[#FFFCF7]",
  ar: "border-saffron/40 bg-saffron-soft/70",
  fils: "border-line bg-[#FFFCF7]",
  sp: "border-saffron/40 bg-saffron-soft/70",
  miss: "border-dashed border-ink-3/50 bg-transparent",
};

function MessyCell({ v, k, className, style }: { v: string; k: Kind; className?: string; style?: React.CSSProperties }) {
  return (
    <span
      className={clsx("lens-cell inline-block whitespace-nowrap rounded-[6px] border px-2.5 py-1.5 text-[13px]", monoAr, " leading-none text-ink shadow-[0_1px_0_rgba(43,33,27,.05)]", kindCls[k], className)}
      style={style}
    >
      <bdi>{v}</bdi>
    </span>
  );
}

function CleanTable({ l, compact }: { l: Copy["lens"]; compact?: boolean }) {
  return (
    <div className="lens-table w-full overflow-hidden rounded-[12px] border border-line bg-[#FFFCF7] shadow-[var(--shadow-paper)]">
      <div className="lens-row grid grid-cols-[1.5fr_.7fr_1fr] gap-3 border-b border-line bg-paper-2 px-4 py-2.5 text-[11px] text-ink-3 sm:grid-cols-[1.5fr_.7fr_1fr_1.35fr]">
        {l.cleanHead.map((h, i) => (
          <span key={h} className={clsx("font-mono uppercase tracking-[0.12em] rtl:font-sans rtl:text-[12px] rtl:tracking-normal", i === 3 && "hidden sm:block", i === 1 && "text-end")}>{h}</span>
        ))}
      </div>
      {CLEAN.map((r) => (
        <div key={r.item} className="lens-row grid grid-cols-[1.5fr_.7fr_1fr] items-center gap-3 border-b border-line/60 px-4 py-2.5 last:border-0 sm:grid-cols-[1.5fr_.7fr_1fr_1.35fr]">
          <span className={clsx("truncate text-[13.5px] text-ink", compact && "text-[13px]")}><bdi>{r.item}</bdi></span>
          <span className="num text-end text-[13px] text-ink">{r.jd}</span>
          <span className="num text-[12.5px] text-ink-2" dir="ltr">{r.date}</span>
          <span className="num hidden truncate text-[12.5px] text-ink-2 sm:block" dir="ltr">
            {r.phone ?? <span className="rounded bg-terra-soft px-1.5 py-0.5 font-sans text-[11px] text-terra-2">{l.missing}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function Chart({ l }: { l: Copy["lens"] }) {
  const max = Math.max(...l.chart.map((d) => d.value));
  const total = l.chart.reduce((a, d) => a + d.value, 0);
  return (
    <figure className="lens-chart w-full rounded-[14px] border border-line bg-[#FFFCF7] p-5 shadow-[var(--shadow-paper)] sm:p-6">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-serif text-[19px] text-ink rtl:font-semibold">{l.chartTitle}</span>
        <span className="text-[12.5px] text-ink-3">{l.chartPlace}</span>
      </figcaption>
      <ul className="mt-5 space-y-3">
        {l.chart.map((d, i) => (
          <li key={d.name} className="grid grid-cols-[minmax(0,9.5rem)_1fr_auto] items-center gap-3 sm:grid-cols-[11rem_1fr_auto]">
            <span className="truncate text-[13.5px] text-ink-2"><bdi>{d.name}</bdi></span>
            <span className="h-[14px] overflow-hidden rounded-[3px] bg-sand/70">
              <span
                className={clsx("lens-bar block h-full origin-left rounded-[3px] rtl:origin-right", i === 0 ? "bg-terra" : "bg-terra/55")}
                style={{ width: `${(d.value / max) * 100}%` }}
              />
            </span>
            <span className="num w-[4.5rem] text-end text-[13px] text-ink">{d.value.toFixed(3)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex items-baseline justify-between border-t border-ink/80 pt-3">
        <span className="text-[13.5px] font-medium text-ink">{l.chartTotal}</span>
        <span className="num text-[15px] font-medium text-terra-2">
          {total.toFixed(3)} <span className="text-[12px] text-ink-3">{l.chartUnit}</span>
        </span>
      </div>
    </figure>
  );
}

function Sentence({ l, big }: { l: Copy["lens"]; big?: boolean }) {
  return (
    <div className="lens-sentence text-center">
      <p className={clsx(
        "mx-auto max-w-[18ch] font-serif font-[360] leading-[1.08] tracking-[-0.025em] text-ink text-balance rtl:max-w-[20ch] rtl:font-semibold rtl:leading-[1.45] rtl:tracking-normal",
        big ? "text-[58px] xl:text-[68px]" : "text-[34px] sm:text-[44px]")}>
        {l.sentencePre} <span className="scribble whitespace-nowrap text-terra-2">{l.sentenceAmount}</span> {l.sentencePost}
      </p>
      <p className="mx-auto mt-6 max-w-[52ch] text-[16px] leading-relaxed text-ink-2 sm:text-[17px]">{l.action}</p>
    </div>
  );
}

function LensRing({ label, fixes }: { label: string; fixes: string }) {
  return (
    <div className="lens-ring relative flex size-[200px] items-center justify-center rounded-full border-[1.5px] border-ink bg-paper xl:size-[220px]">
      <span className="absolute inset-[10px] rounded-full border border-line" aria-hidden />
      <span className="absolute -top-7 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{label}</span>
      <div className="relative flex flex-col items-center">
        <span className="size-3 rounded-full bg-terra" />
        <span className="mt-3 flex items-baseline gap-1.5">
          <span className="lens-count num text-[26px] text-ink">0</span>
          <span className="text-[12px] text-ink-3">{fixes}</span>
        </span>
      </div>
    </div>
  );
}

function StaticStory({ l }: { l: Copy["lens"] }) {
  const visuals = [
    <div key="m" className="flex flex-wrap gap-2.5 py-2">
      {MESSY.map((m) => <MessyCell key={m.v} v={m.v} k={m.k} style={{ transform: `rotate(${m.r}deg)` }} />)}
    </div>,
    <CleanTable key="c" l={l} compact />,
    <Chart key="ch" l={l} />,
    <div key="s" className="rounded-[14px] border border-line bg-paper-2 px-5 py-10 sm:px-10"><Sentence l={l} /></div>,
  ];
  return (
    <section aria-labelledby="lens-title" className="border-b border-line py-20 sm:py-28">
      <Container>
        <Kicker className="mb-4">{l.kicker}</Kicker>
        <h2 id="lens-title" className="sr-only">{l.steps[0].title}</h2>
        <ol className="space-y-16 sm:space-y-20">
          {l.steps.map((s, i) => (
            <li key={i} className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-12">
              <div className="lg:col-span-5">
                <span className="num text-[13px] text-terra">0{i + 1}</span>
                <h3 className="mt-2 font-serif text-[28px] font-[400] leading-[1.12] tracking-[-0.015em] text-ink sm:text-[34px] rtl:font-semibold rtl:leading-[1.45] rtl:tracking-normal">{s.title}</h3>
                <p className="mt-3 max-w-[46ch] text-[16.5px] leading-relaxed text-ink-2">{s.body}</p>
              </div>
              <div className="lg:col-span-7">
                {i === 1 && (
                  <div className="mb-4 flex items-center gap-3 text-[12px] text-ink-3" aria-hidden>
                    <span className="flex size-7 items-center justify-center rounded-full border-[1.5px] border-ink"><span className="size-1.5 rounded-full bg-terra" /></span>
                    <span className="h-px flex-1 bg-ink/70" />
                    <span>{l.cleanLabel}</span>
                  </div>
                )}
                {visuals[i]}
              </div>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

function centerIn(el: HTMLElement, stage: HTMLElement) {
  let x = el.offsetWidth / 2;
  let y = el.offsetHeight / 2;
  let n: HTMLElement | null = el;
  while (n && n !== stage) {
    x += n.offsetLeft;
    y += n.offsetTop;
    n = n.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

function AnimatedStory({ l }: { l: Copy["lens"] }) {
  const root = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);

  useIsoLayoutEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const el = root.current;
    if (!el) return;
    const ctx = gsap.context(() => {
      const q = gsap.utils.selector(el);
      const stage = q(".lens-stage")[0] as HTMLElement;
      const ring = q(".lens-ring")[0] as HTMLElement;
      const counter = q(".lens-count")[0] as HTMLElement;
      const cells = q(".lens-cell") as HTMLElement[];
      const rows = q(".lens-clean .lens-row") as HTMLElement[];
      const titles = q(".lens-step") as HTMLElement[];
      const lensC = () => centerIn(ring, stage);
      const dx = (n: HTMLElement) => () => lensC().x - centerIn(n, stage).x;
      const dy = (n: HTMLElement) => () => lensC().y - centerIn(n, stage).y;

      gsap.set(titles.slice(1), { autoAlpha: 0, y: 14 });
      gsap.set(q(".lens-clean"), { autoAlpha: 0 });
      gsap.set(rows, { autoAlpha: 0 });
      gsap.set(q(".lens-chart-wrap, .lens-sentence-wrap"), { autoAlpha: 0 });
      gsap.set(q(".lens-bar"), { scaleX: 0 });

      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: el,
          start: "top 68px",
          end: () => "+=" + Math.round(window.innerHeight * 3.4),
          pin: true,
          scrub: 0.7,
          invalidateOnRefresh: true,
          onUpdate: (self) => {
            const p = self.progress;
            setStep(p < 0.1 ? 0 : p < 0.46 ? 1 : p < 0.74 ? 2 : 3);
          },
        },
      });

      const swap = (from: number, to: number, at: number) => {
        tl.to(titles[from], { autoAlpha: 0, y: -14, duration: 0.35 }, at);
        tl.fromTo(titles[to], { autoAlpha: 0, y: 14 }, { autoAlpha: 1, y: 0, duration: 0.35, immediateRender: false }, at + 0.25);
      };

      cells.forEach((c, i) => {
        const at = 0.5 + i * 0.17;
        tl.to(c, { x: dx(c), y: dy(c), rotate: 0, scale: 0.35, duration: 1.1, ease: "power1.in" }, at);
        tl.to(c, { autoAlpha: 0, duration: 0.35 }, at + 0.8);
      });
      const count = { v: 0 };
      tl.to(count, { v: 212, duration: 3.2, onUpdate: () => { counter.textContent = String(Math.round(count.v)); } }, 0.6);
      tl.to(q(".lens-clean"), { autoAlpha: 1, duration: 0.4 }, 1.1);
      rows.forEach((r, i) => {
        tl.fromTo(r, { x: dx(r), y: dy(r), scale: 0.4, autoAlpha: 0 }, { x: 0, y: 0, scale: 1, autoAlpha: 1, duration: 1, ease: "power2.out", immediateRender: false }, 1.2 + i * 0.42);
      });
      tl.to(q(".lens-messy-label"), { autoAlpha: 0, duration: 0.4 }, 3.4);
      swap(0, 1, 0.9);

      tl.to(q(".lens-clean"), { autoAlpha: 0, y: -16, duration: 0.5 }, 4.7);
      tl.to(ring, { autoAlpha: 0, scale: 0.85, duration: 0.5 }, 4.7);
      tl.to(q(".lens-axis"), { scaleX: 0, duration: 0.5 }, 4.7);
      tl.fromTo(q(".lens-chart-wrap"), { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.5, immediateRender: false }, 5.0);
      tl.to(q(".lens-bar"), { scaleX: 1, duration: 0.7, stagger: 0.18, ease: "power2.out" }, 5.3);
      swap(1, 2, 4.8);

      tl.to(q(".lens-chart-wrap"), { autoAlpha: 0, y: -18, duration: 0.5 }, 7.6);
      tl.fromTo(q(".lens-sentence-wrap"), { autoAlpha: 0, y: 20 }, { autoAlpha: 1, y: 0, duration: 0.6, immediateRender: false }, 7.95);
      swap(2, 3, 7.6);
      tl.to({}, { duration: 1.2 }, 8.6);
      ScrollTrigger.refresh();
    }, el);
    let alive = true;
    document.fonts?.ready.then(() => alive && ScrollTrigger.refresh());
    return () => {
      alive = false;
      ctx.revert();
    };
  }, [l]);

  return (
    <section ref={root} aria-labelledby="lens-title" className="relative h-[calc(100svh-68px)] overflow-hidden border-b border-line bg-paper">
      <Container className="flex h-full max-h-[940px] flex-col py-10 xl:py-14">
        <div className="grid grid-cols-12 items-start gap-8">
          <div className="col-span-7">
            <Kicker className="mb-4">{l.kicker}</Kicker>
            <div className="relative min-h-[150px]">
              {l.steps.map((s, i) => (
                <div key={i} className="lens-step absolute inset-x-0 top-0" aria-hidden={i !== step}>
                  {i === 0 ? (
                    <h2 id="lens-title" className="font-serif text-[40px] font-[380] leading-[1.06] tracking-[-0.02em] text-ink xl:text-[46px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{s.title}</h2>
                  ) : (
                    <p className="font-serif text-[40px] font-[380] leading-[1.06] tracking-[-0.02em] text-ink xl:text-[46px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{s.title}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div className="relative col-span-5 min-h-[150px] pt-9">
            {l.steps.map((s, i) => (
              <p key={i} className={clsx("absolute inset-x-0 max-w-[44ch] text-[16px] leading-relaxed text-ink-2 transition-opacity duration-500", i === step ? "opacity-100" : "opacity-0")} aria-hidden={i !== step}>
                {s.body}
              </p>
            ))}
          </div>
        </div>

        <div className="lens-stage relative mt-6 flex-1">
          <span className="lens-axis absolute inset-x-0 top-1/2 h-px origin-center bg-ink/25" aria-hidden />

          <div className="absolute inset-y-[6%] start-0 w-[36%]" aria-hidden>
            <span className="lens-messy-label absolute -top-6 start-0 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{l.messyLabel}</span>
            {MESSY.map((m) => (
              <MessyCell key={m.v} v={m.v} k={m.k} className="absolute" style={{ insetInlineStart: `${m.x}%`, top: `${m.y}%`, transform: `rotate(${m.r}deg)` }} />
            ))}
          </div>

          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            <LensRing label={l.lensLabel} fixes={l.fixesLabel} />
          </div>

          <div className="absolute inset-y-0 end-0 flex w-[38%] flex-col justify-center">
            <div className="lens-clean relative">
              <span className="absolute -top-7 start-0 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{l.cleanLabel}</span>
              <CleanTable l={l} />
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="lens-chart-wrap w-full max-w-[680px]">
              <Chart l={l} />
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="lens-sentence-wrap w-full">
              <Sentence l={l} big />
            </div>
          </div>
        </div>

        <ol className="mt-6 flex items-center gap-3" aria-hidden>
          {l.steps.map((_, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className={clsx("num text-[11px] transition-colors", i <= step ? "text-ink" : "text-ink-3/60")}>0{i + 1}</span>
              <span className={clsx("h-[2px] w-10 rounded-full transition-colors duration-300", i <= step ? "bg-terra" : "bg-line")} />
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

export function LensStory() {
  const { c } = useCopy();
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px) and (min-height: 680px) and (prefers-reduced-motion: no-preference)");
    const forceStatic = new URLSearchParams(window.location.search).get("lens") === "static";
    const update = () => setAnimated(mq.matches && !forceStatic);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return animated ? <AnimatedStory l={c.lens} /> : <StaticStory l={c.lens} />;
}
