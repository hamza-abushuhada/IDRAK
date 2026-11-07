"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Check, FileSpreadsheet, RotateCcw, Upload } from "lucide-react";
import { publicApi, ApiError } from "@/lib/api";
import { Button, Spinner } from "@/components/ui";
import { useCopy } from "./use-copy";
import { lh } from "./copy";
import { Arrow, Container, Kicker, monoAr } from "./primitives";
import { Gauge, scoreTone } from "./Gauge";

const DIMS = ["completeness", "validity", "uniqueness", "consistency", "timeliness"] as const;
type DimKey = (typeof DIMS)[number];
type Issue = { key: string; title_en?: string; title_ar?: string; count: number; category?: string; examples?: { before: unknown; after: unknown }[] };
type HealthResult = {
  file_name: string; rows: number; columns: number; score: number; projected_score: number;
  dimensions: Partial<Record<DimKey, number>>; issues: Issue[];
};

const MAX_BYTES = 5 * 1024 * 1024;
const OK_EXT = /\.(csv|xlsx|xls)$/i;
const ACCEPT = ".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel";
const fmt = (n: number) => new Intl.NumberFormat("en-US").format(n);
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function useCountUp(target: number, duration = 1100) {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = from.current;
    if (reduce) {
      from.current = target;
      setV(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const e = 1 - Math.pow(1 - p, 3);
      const cur = start + (target - start) * e;
      from.current = cur;
      setV(cur);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return v;
}

export function HealthCheck() {
  const { c, locale } = useCopy();
  const h = c.health;
  const [phase, setPhase] = useState<"idle" | "loading" | "result" | "error">("idle");
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<HealthResult | null>(null);
  const [isExample, setIsExample] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [step, setStep] = useState(0);
  const lastFile = useRef<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (phase !== "loading") return;
    setStep(0);
    const id = window.setInterval(() => setStep((s) => Math.min(s + 1, h.loading.steps.length - 1)), 650);
    return () => clearInterval(id);
  }, [phase, h.loading.steps.length]);

  useEffect(() => {
    if (phase === "result" || phase === "error") topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [phase]);

  const run = useCallback(async (file: File) => {
    lastFile.current = file;
    setFileName(file.name);
    if (!OK_EXT.test(file.name)) { setError(h.errors.type); setPhase("error"); return; }
    if (file.size > MAX_BYTES) { setError(h.errors.tooBig); setPhase("error"); return; }
    setPhase("loading");
    setIsExample(false);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const [res] = await Promise.all([publicApi<HealthResult>("/public/health-check", { method: "POST", body: fd }), wait(2200)]);
      setResult({ ...res, issues: Array.isArray(res.issues) ? res.issues : [], dimensions: res.dimensions ?? {} });
      setPhase("result");
    } catch (e) {
      const status = e instanceof ApiError ? e.status : -1;
      setError(status === 0 ? h.errors.network : status === 413 ? h.errors.tooBig : status === 415 ? h.errors.type : h.errors.generic);
      setPhase("error");
    }
  }, [h.errors]);

  async function runSample() {
    try {
      const r = await fetch("/samples/pos_export_messy.xlsx");
      if (!r.ok) throw new Error("missing");
      const blob = await r.blob();
      await run(new File([blob], "pos_export_messy.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    } catch {
      setFileName("pos_export_messy.xlsx");
      setError(h.errors.sampleMissing);
      setPhase("error");
    }
  }

  function showExample() {
    const ex = h.example;
    setResult({ ...ex, issues: ex.issues.map((i) => ({ ...i, title_en: i.title, title_ar: i.title })) });
    setIsExample(true);
    setPhase("result");
  }

  function reset() {
    setResult(null);
    setError("");
    setPhase("idle");
    if (inputRef.current) inputRef.current.value = "";
  }

  if (phase === "result" && result) {
    return (
      <div ref={topRef} className="scroll-mt-24">
        <Result r={result} example={isExample} onReset={reset} locale={locale} />
      </div>
    );
  }

  return (
    <div ref={topRef} className="scroll-mt-24">
      <Container className="grid grid-cols-1 gap-12 pb-24 pt-12 sm:pt-16 lg:grid-cols-12 lg:gap-14">
        <div className="lg:col-span-5">
          <Kicker tone="terra" className="mb-5">{h.kicker}</Kicker>
          <h1 className="font-serif text-[40px] font-[380] leading-[1.04] tracking-[-0.022em] text-ink text-balance sm:text-[54px] rtl:font-semibold rtl:leading-[1.35] rtl:tracking-normal">{h.title}</h1>
          <p className="mt-6 max-w-[44ch] text-[17px] leading-[1.65] text-ink-2">{h.sub}</p>
          <div className="mt-10 border-t border-ink/80">
            <p className="pb-2 pt-5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-3 rtl:font-sans rtl:text-[13px] rtl:tracking-normal">{h.checksTitle}</p>
            <ul>
              {DIMS.map((d) => (
                <li key={d} className="flex items-baseline gap-4 border-b border-line py-3">
                  <span className="w-[8.5rem] shrink-0 text-[15px] font-medium text-ink">{h.dims[d].name}</span>
                  <span className="text-[14.5px] text-ink-2">{h.dims[d].desc}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="lg:col-span-7">
          <div className="rounded-[18px] border border-line bg-[#FFFCF7] p-3 shadow-[var(--shadow-lift)] sm:p-4">
            {phase === "idle" && (
              <>
                <label
                  onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    const f = e.dataTransfer.files?.[0];
                    if (f) run(f);
                  }}
                  className={clsx(
                    "flex min-h-[340px] cursor-pointer flex-col items-center justify-center rounded-[14px] border-[1.5px] border-dashed px-6 py-12 text-center transition-colors focus-within:border-terra focus-within:bg-terra-soft/20",
                    drag ? "border-terra bg-terra-soft/30" : "border-ink-3/35 hover:border-ink-3/70 hover:bg-paper",
                  )}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPT}
                    className="sr-only"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f); }}
                  />
                  <span className="flex size-16 items-center justify-center rounded-full border-[1.5px] border-ink bg-paper">
                    {drag ? <Upload size={24} className="text-terra" aria-hidden /> : <FileSpreadsheet size={24} className="text-ink" aria-hidden />}
                  </span>
                  <span className="mt-6 font-serif text-[26px] text-ink rtl:font-semibold">{drag ? h.drop.dragging : h.drop.title}</span>
                  <span className="mt-2 text-[15px] text-ink-2">
                    {h.drop.or} <span className="font-medium text-terra-2 underline decoration-terra/40 underline-offset-4">{h.drop.browse}</span>
                  </span>
                  <span className="mt-5 text-[13px] text-ink-3">{h.drop.hint}</span>
                </label>
                <div className="flex flex-col items-start gap-3 px-3 pb-3 pt-5 sm:flex-row sm:items-center sm:justify-between sm:px-4">
                  <p className="max-w-[40ch] text-[13.5px] leading-snug text-ink-3">{h.drop.sampleHint}</p>
                  <Button variant="secondary" onClick={runSample}>
                    <FileSpreadsheet size={15} aria-hidden /> {h.drop.sample}
                  </Button>
                </div>
              </>
            )}

            {phase === "loading" && (
              <div className="flex min-h-[420px] flex-col justify-center px-6 py-12 sm:px-12" role="status" aria-live="polite">
                <div className="flex items-center gap-3">
                  <Spinner size={20} />
                  <p className="font-serif text-[24px] text-ink rtl:font-semibold">{h.loading.title}</p>
                </div>
                <p dir="ltr" className="mt-2 truncate font-mono text-[13px] text-ink-3 rtl:text-right">{fileName}</p>
                <ol className="mt-8 space-y-3">
                  {h.loading.steps.map((s, i) => (
                    <li key={s} className={clsx("flex items-center gap-3 text-[15px] transition-colors", i < step ? "text-ink-2" : i === step ? "text-ink" : "text-ink-3/60")}>
                      <span className={clsx("flex size-5 items-center justify-center rounded-full border", i < step ? "border-olive bg-olive text-paper" : i === step ? "border-terra" : "border-line")}>
                        {i < step ? <Check size={12} aria-hidden /> : i === step ? <span className="size-1.5 animate-pulse rounded-full bg-terra" /> : null}
                      </span>
                      {s}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {phase === "error" && (
              <div className="flex min-h-[420px] flex-col justify-center px-6 py-12 sm:px-12" role="alert">
                <span className="flex size-12 items-center justify-center rounded-full bg-terra-soft font-serif text-[22px] text-terra-2">!</span>
                <p className="mt-6 font-serif text-[26px] text-ink rtl:font-semibold">{h.errors.title}</p>
                {fileName && <p dir="ltr" className="mt-1 truncate font-mono text-[13px] text-ink-3 rtl:text-right">{fileName}</p>}
                <p className="mt-4 max-w-[48ch] text-[16px] leading-relaxed text-ink-2">{error}</p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <Button onClick={() => (lastFile.current && error !== h.errors.type && error !== h.errors.tooBig ? run(lastFile.current) : reset())}>
                    <RotateCcw size={15} className="rtl:-scale-x-100" aria-hidden /> {h.errors.retry}
                  </Button>
                  <Button variant="secondary" onClick={showExample}>{h.errors.example}</Button>
                </div>
              </div>
            )}
          </div>
          <p className="mt-4 flex items-center gap-2 px-1 text-[13px] text-ink-3">
            <span aria-hidden className="size-1.5 rounded-full bg-olive" /> {h.privacy}
          </p>
        </div>
      </Container>
    </div>
  );

}

function Result({ r, example, onReset, locale }: { r: HealthResult; example: boolean; onReset: () => void; locale: "ar" | "en" }) {
  const { c } = useCopy();
  const h = c.health;
  const R = h.result;
  const [after, setAfter] = useState(false);
  const target = after ? r.projected_score : r.score;
  const shown = useCountUp(target);
  const totalIssues = r.issues.reduce((a, i) => a + (Number(i.count) || 0), 0);
  const verdict = (v: number) => (v < 50 ? R.verdicts.low : v < 80 ? R.verdicts.mid : R.verdicts.high);
  const tone = scoreTone(target);
  const toneText = { terra: "text-terra-2", saffron: "text-[#8a5d0e]", olive: "text-olive" }[tone];
  const toneBg = { terra: "bg-terra-soft", saffron: "bg-saffron-soft", olive: "bg-olive-soft" }[tone];
  const catLabel = (k?: string) => (k ? ((h.categories as Record<string, string>)[k.toLowerCase()] ?? k) : "");

  return (
    <>
      <Container className="pb-16 pt-12 sm:pt-16">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Kicker tone="terra">{h.kicker}</Kicker>
            {example && <span className="rounded-full border border-dashed border-ink-3/50 px-2.5 py-0.5 text-[12px] text-ink-3">{R.exampleBadge}</span>}
          </div>
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw size={14} className="rtl:-scale-x-100" aria-hidden /> {R.again}
          </Button>
        </div>

        <div className="mt-8 grid grid-cols-1 gap-12 lg:grid-cols-12">
          <section aria-labelledby="score-title" className="rounded-[18px] border border-line bg-[#FFFCF7] p-6 shadow-[var(--shadow-paper)] sm:p-8 lg:col-span-5">
            <h1 id="score-title" className="font-serif text-[26px] text-ink rtl:font-semibold">{R.title}</h1>
            <p className="mt-1 truncate text-[13.5px] text-ink-3">
              <bdi dir="ltr" className="font-mono">{r.file_name}</bdi> · {R.meta.replace("{rows}", fmt(r.rows)).replace("{columns}", fmt(r.columns))}
            </p>
            <div className="mt-8 flex justify-center">
              <Gauge value={shown} ghost={after ? undefined : r.projected_score} size={300} label={`${Math.round(target)} ${R.outOf}`}>
                <span className={clsx("num text-[64px] leading-none", toneText)} aria-live="polite">{Math.round(shown)}</span>
                <span className="mt-1 text-[13px] text-ink-3">{R.outOf}</span>
              </Gauge>
            </div>
            <p className="mt-5 text-center">
              <span className={clsx("inline-block rounded-full px-3 py-1 text-[13px] font-medium", toneBg, toneText)}>{after ? R.afterIdrak : verdict(target)}</span>
            </p>
            <div className="mt-8 grid grid-cols-2 border-t border-line pt-5 text-center">
              <div>
                <p className="text-[12.5px] text-ink-3">{R.today}</p>
                <p className="num mt-1 text-[24px] text-terra-2">{Math.round(r.score)}</p>
              </div>
              <div className="border-s border-line">
                <p className="text-[12.5px] text-ink-3">{R.afterIdrak}</p>
                <p className="num mt-1 text-[24px] text-olive">{Math.round(r.projected_score)}</p>
              </div>
            </div>
            <Button variant={after ? "secondary" : "olive"} className="mt-6 w-full" onClick={() => setAfter((a) => !a)} aria-pressed={after}>
              {after ? R.showCurrent : R.preview}
            </Button>
          </section>

          <section aria-labelledby="dims-title" className="lg:col-span-7">
            <h2 id="dims-title" className="font-serif text-[26px] text-ink rtl:font-semibold">{R.dimensionsTitle}</h2>
            <ul className="mt-6 border-t border-ink/80">
              {DIMS.map((d) => {
                const v = Math.round(Number(r.dimensions[d] ?? 0));
                const t = scoreTone(v);
                return (
                  <li key={d} className="border-b border-line py-4">
                    <div className="flex items-baseline justify-between gap-4">
                      <p className="text-[15.5px] font-medium text-ink">{h.dims[d].name}</p>
                      <p className="num text-[18px] text-ink">{v}</p>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-sand">
                      <div className={clsx("h-full rounded-full transition-[width] duration-1000 ease-out", t === "terra" ? "bg-terra" : t === "saffron" ? "bg-saffron" : "bg-olive")} style={{ width: `${v}%` }} />
                    </div>
                    <p className="mt-1.5 text-[13px] text-ink-3">{h.dims[d].desc}</p>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>

        <section aria-labelledby="issues-title" className="mt-16">
          <h2 id="issues-title" className="font-serif text-[30px] text-ink rtl:font-semibold">{R.issuesTitle}</h2>
          {r.issues.length === 0 ? (
            <p className="mt-6 text-[16px] text-ink-2">{R.noIssues}</p>
          ) : (
            <ol className="mt-6 border-t border-ink/80">
              {r.issues.slice(0, 8).map((i, idx) => (
                <li key={i.key ?? idx} className="grid grid-cols-1 gap-4 border-b border-line py-6 lg:grid-cols-12 lg:gap-8">
                  <div className="flex gap-4 lg:col-span-5">
                    <span className="num pt-1 text-[13px] text-terra">{String(idx + 1).padStart(2, "0")}</span>
                    <div>
                      <p className="text-[17px] font-medium leading-snug text-ink">{(locale === "ar" ? i.title_ar : i.title_en) || i.title_en || i.title_ar || i.key}</p>
                      <p className="mt-2 flex flex-wrap items-center gap-2 text-[13px]">
                        <span className="num rounded-full bg-terra-soft px-2.5 py-0.5 text-terra-2">{R.cells.replace("{n}", fmt(Number(i.count) || 0))}</span>
                        {i.category && <span className="rounded-full bg-sand px-2.5 py-0.5 text-ink-2">{catLabel(i.category)}</span>}
                      </p>
                    </div>
                  </div>
                  {i.examples && i.examples.length > 0 && (
                    <div className="lg:col-span-7">
                      <div className="overflow-hidden rounded-[12px] border border-line bg-[#FFFCF7]">
                        <div className="grid grid-cols-[1fr_auto_1fr] gap-3 border-b border-line bg-paper-2 px-4 py-2 text-[11.5px] text-ink-3">
                          <span>{R.before}</span><span className="w-3" /><span>{R.after}</span>
                        </div>
                        {i.examples.slice(0, 3).map((ex, k) => (
                          <div key={k} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line/60 px-4 py-2.5 last:border-0">
                            <span className={`min-w-0 break-words text-[13.5px] text-terra-2 line-through decoration-terra/40 ${monoAr}`}><bdi>{String(ex.before ?? "—")}</bdi></span>
                            <Arrow size={13} className="text-ink-3" />
                            <span className={`min-w-0 break-words text-[13.5px] font-medium text-ink ${monoAr}`}><bdi>{String(ex.after ?? "—")}</bdi></span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
          {r.issues.length > 8 && <p className="mt-5 text-[14.5px] text-ink-3">{R.more.replace("{n}", String(r.issues.length - 8))}</p>}
        </section>
      </Container>

      <section className="bg-cocoa text-paper">
        <Container className="flex flex-col gap-8 py-16 sm:py-20 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="max-w-[20ch] font-serif text-[36px] font-[380] leading-[1.08] tracking-[-0.02em] sm:text-[48px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">
              {R.ctaTitle.replace("{n}", fmt(totalIssues))}
            </p>
            <p className="mt-5 max-w-[50ch] text-[17px] leading-relaxed text-paper/75">{R.ctaBody}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a href={lh(locale, "/signup")} className="inline-flex h-12 items-center gap-2 rounded-full bg-terra px-7 text-[15px] font-medium text-paper transition-colors hover:bg-terra-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper">
              {R.ctaButton} <Arrow size={16} />
            </a>
            <button onClick={onReset} className="inline-flex h-12 items-center rounded-full border border-paper/35 px-6 text-[15px] text-paper transition-colors hover:bg-paper/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper">
              {R.again}
            </button>
          </div>
        </Container>
      </section>
    </>
  );
}
