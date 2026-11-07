"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useRouter } from "@/lib/router";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import { ChevronRight, History, Mic, MicOff, Plus, X, CornerDownLeft, ArrowUpRight, ShieldAlert } from "lucide-react";
import { useLocale, useTx } from "@/i18n";
import { streamApi, api, ApiError } from "@/lib/api";
import { highlight, visibleElements } from "@/lib/highlight";
import { useSession } from "@/components/app/session";
import Chart, { PALETTE, axisStyle } from "@/components/app/Chart";
import { useAssistant, type Block, type ChartSpec, type Msg } from "./store";

const SPIN = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"];
const COMMANDS = [
  { cmd: "/help", en: "Show commands", ar: "اعرض الأوامر" },
  { cmd: "/report", en: "This week's summary", ar: "ملخص الأسبوع" },
  { cmd: "/leaks", en: "Where am I losing money?", ar: "وين عم أخسر مصاري؟" },
  { cmd: "/forecast ", en: "Forecast a product", ar: "توقّع طلب صنف" },
  { cmd: "/reorder", en: "What should I order now?", ar: "شو لازم أطلب هلأ؟" },
  { cmd: "/clean", en: "Upload & clean a file", ar: "ارفع ملف ونظّفه" },
  { cmd: "/goto ", en: "Open a screen", ar: "افتح شاشة" },
];

const uid = () => Math.random().toString(36).slice(2);

export default function AssistantPanel() {
  const tx = useTx();
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const { me, org } = useSession();
  const { open, msgs, sessionId, setOpen, set, reset, takePending, pending } = useAssistant();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [spin, setSpin] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const [listening, setListening] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recRef = useRef<any>(null);

  useEffect(() => {
    if (!busy) return;
    const t0 = Date.now();
    const a = setInterval(() => setSpin((s) => (s + 1) % SPIN.length), 120);
    const b = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 500);
    return () => { clearInterval(a); clearInterval(b); setElapsed(0); };
  }, [busy]);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 50); }, [open]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, status]);
  useEffect(() => {
    if (open && pending && !busy) { const q = takePending(); if (q) send(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && busy) stop(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const updateLast = (fn: (m: Msg) => Msg) => set((s) => ({ msgs: s.msgs.map((m, i) => (i === s.msgs.length - 1 ? fn(m) : m)) }));
  const pushBlock = (b: Block) => updateLast((m) => ({ ...m, blocks: [...m.blocks, b] }));

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setStatus(tx("Thinking", "عم يفكّر"));
    set((s) => ({ msgs: [...s.msgs, { id: uid(), role: "user", text: q, blocks: [] }, { id: uid(), role: "assistant", blocks: [], streaming: true }] }));
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const rel = pathname.replace(/^\/(ar|en)/, "") || "/app";
    try {
      await streamApi("/assistant/chat", { message: q, session_id: useAssistant.getState().sessionId, locale, page: { path: rel, elements: visibleElements() } }, (e: any) => {
        switch (e.type) {
          case "session": set(() => ({ sessionId: e.id })); break;
          case "status": setStatus(e.text); break;
          case "text":
            setStatus(null);
            updateLast((m) => {
              const blocks = [...m.blocks];
              const last = blocks[blocks.length - 1];
              if (last && last.kind === "text") blocks[blocks.length - 1] = { kind: "text", text: last.text + e.delta };
              else blocks.push({ kind: "text", text: e.delta });
              return { ...m, blocks };
            });
            break;
          case "tool_start": setStatus(e.label); pushBlock({ kind: "tool", tool: { id: e.id, name: e.name, label: e.label, args: e.args, sql: e.sql } }); break;
          case "tool_end":
            updateLast((m) => ({ ...m, blocks: m.blocks.map((b) => (b.kind === "tool" && b.tool.id === e.id ? { kind: "tool", tool: { ...b.tool, summary: e.summary, ok: e.ok, done: true } } : b)) }));
            setStatus(tx("Thinking", "عم يفكّر"));
            break;
          case "navigate": router.push(`/${locale}${e.path}`); pushBlock({ kind: "nav", path: e.path }); break;
          case "highlight": if (window.innerWidth < 1280) setTimeout(() => setOpen(false), 300); setTimeout(() => highlight(e.target, e.message), 650); pushBlock({ kind: "highlight", target: e.target, message: e.message }); break;
          case "chart": pushBlock({ kind: "chart", spec: e.spec }); break;
          case "email_draft": pushBlock({ kind: "draft", draft: e.draft }); break;
          case "refused": pushBlock({ kind: "refused" }); break;
          case "error": pushBlock({ kind: "error", text: e.text }); break;
        }
      }, ctrl.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        pushBlock({ kind: "error", text: err instanceof ApiError && err.message === "network" ? tx("Can't reach the Idrak server.", "ما قدرنا نوصل لسيرفر إدراك.") : String((err as Error).message) });
      }
    } finally {
      updateLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
      setStatus(null);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    pushBlock({ kind: "error", text: tx("Interrupted by user", "تم الإيقاف") });
  }

  function toggleVoice() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { pushBlockOrAlert(); return; }
    if (listening) { recRef.current?.stop(); return; }
    const rec = new SR();
    rec.lang = locale === "ar" ? "ar-JO" : "en-US";
    rec.interimResults = true;
    rec.onresult = (ev: any) => setInput(Array.from(ev.results).map((r: any) => r[0].transcript).join(""));
    rec.onend = () => setListening(false);
    rec.start();
    recRef.current = rec;
    setListening(true);
  }
  function pushBlockOrAlert() { alert(tx("Voice input isn't supported in this browser (try Chrome or Edge).", "الإدخال الصوتي مش مدعوم بهالمتصفح (جرّب كروم أو إيدج).")); }

  async function loadSession(id: string) {
    setShowHistory(false);
    const rows = await api<{ role: "user" | "assistant"; content: string; events: any[] | null }[]>(`/assistant/sessions/${id}`);
    const out: Msg[] = rows.map((r) => {
      if (r.role === "user") return { id: uid(), role: "user", text: r.content, blocks: [] };
      const blocks: Block[] = [];
      const tools: Record<string, any> = {};
      for (const e of r.events || []) {
        if (e.type === "tool_start") { tools[e.id] = { id: e.id, name: e.name, label: e.label, args: e.args, sql: e.sql }; blocks.push({ kind: "tool", tool: tools[e.id] }); }
        if (e.type === "tool_end" && tools[e.id]) Object.assign(tools[e.id], { summary: e.summary, ok: e.ok, done: true });
        if (e.type === "chart") blocks.push({ kind: "chart", spec: e.spec });
        if (e.type === "navigate") blocks.push({ kind: "nav", path: e.path });
        if (e.type === "refused") blocks.push({ kind: "refused" });
      }
      blocks.push({ kind: "text", text: r.content });
      return { id: uid(), role: "assistant", blocks };
    });
    set(() => ({ msgs: out, sessionId: id }));
  }

  const showCmds = input.startsWith("/") && !input.includes(" ");
  const cmds = COMMANDS.filter((c) => c.cmd.startsWith(input.trim() || "/"));
  const firstName = (me?.full_name || "").split(" ")[0];
  const orgName = org ? (locale === "ar" ? org.name_ar || org.name : org.name) : "";

  if (!open) return null;
  return (
    <aside className={clsx("no-print fixed inset-0 z-40 flex flex-col bg-cocoa text-[#EDE3D4] xl:sticky xl:top-16 xl:z-20 xl:h-[calc(100dvh-4rem)] xl:w-[440px] xl:shrink-0 xl:border-s xl:border-[#3a2f27]")}
      style={{ fontFamily: "var(--font-plex-mono), var(--font-plex-ar), ui-monospace, monospace" }} dir={locale === "ar" ? "rtl" : "ltr"}>
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-[#3a2f27] px-4 text-[12.5px]">
        <span className="text-saffron">✻</span>
        <span className="font-semibold tracking-tight text-[#F6EEE2]">{tx("Idrak", "إدراك")}</span>
        <span className="truncate text-[#8f7f70]">· {orgName}</span>
        <div className="ms-auto flex items-center gap-1">
          <IconBtn title={tx("History", "السجل")} onClick={() => setShowHistory((v) => !v)}><History size={15} /></IconBtn>
          <IconBtn title={tx("New chat", "محادثة جديدة")} onClick={() => { reset(); setShowHistory(false); }}><Plus size={15} /></IconBtn>
          <IconBtn title={tx("Close", "إغلاق")} onClick={() => setOpen(false)}><X size={15} /></IconBtn>
        </div>
      </div>
      {showHistory && <HistoryList onPick={loadSession} />}

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4 text-[13px] leading-[1.65]">
        {msgs.length === 0 && (
          <div>
            <div className="rounded-lg border border-[#5a4636] px-4 py-3">
              <p><span className="text-saffron">✻</span> {tx("Welcome to Idrak!", "أهلاً فيك بإدراك!")}</p>
              <p className="mt-2 text-[#a8988a]">{tx("/help for commands · Ctrl K to toggle · Esc to stop", "‎/help للأوامر · Ctrl K للفتح والإغلاق · Esc للإيقاف")}</p>
              <p className="mt-1 text-[#a8988a]">{tx("business", "المحل")}: <span className="text-[#EDE3D4]">{orgName}</span></p>
            </div>
            <p className="mt-4 text-[#cfc2b3]">{tx(`Hi ${firstName} — ask me anything about your shop. I can also take you to any screen and point at the exact field.`, `أهلين ${firstName} — اسألني أي إشي عن محلّك. وبقدر آخذك لأي شاشة وأأشّرلك عالمكان بالزبط.`)}</p>
            <p className="mt-4 text-[11.5px] uppercase tracking-wider text-[#8f7f70]">{tx("Try", "جرّب")}</p>
            <div className="mt-2 space-y-1.5">
              {(locale === "ar"
                ? ["شو أكثر صنف بيخسرني هالشهر؟", "قارن بين فروعي آخر أسبوع وارسم مخطط", "وين بغيّر حد إعادة الطلب لبيبسي؟", "شو لازم أجهّز لرمضان؟"]
                : ["Which product loses me the most money this month?", "Compare my branches last week with a chart", "Where do I change the reorder level for Pepsi?", "What should I stock up on before Ramadan?"]
              ).map((s) => (
                <button key={s} onClick={() => send(s)} className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-start text-[#e9dccb] hover:bg-[#2a211b]">
                  <ChevronRight size={14} className="mt-[3px] shrink-0 text-terra rtl:rotate-180" />{s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m) => (m.role === "user" ? <UserLine key={m.id} text={m.text!} /> : <AssistantMsg key={m.id} m={m} locale={locale} />))}
        {busy && (
          <p className="mt-3 flex items-center gap-2 text-[#d6a24a]">
            <span className="inline-block w-3 text-center">{SPIN[spin]}</span>
            <span>{status || tx("Thinking", "عم يفكّر")}…</span>
            <span className="text-[#8f7f70]">({elapsed}s · {tx("esc to interrupt", "Esc للإيقاف")})</span>
          </p>
        )}
      </div>

      <div className="relative shrink-0 px-3 pb-3">
        {showCmds && cmds.length > 0 && (
          <div className="absolute bottom-full start-3 end-3 mb-1 overflow-hidden rounded-lg border border-[#5a4636] bg-[#241c17] py-1 text-[12.5px] shadow-xl">
            {cmds.map((c) => (
              <button key={c.cmd} onClick={() => { setInput(c.cmd); inputRef.current?.focus(); }}
                className="flex w-full items-center gap-3 px-3 py-1.5 text-start hover:bg-[#3a2f27]">
                <span className="w-24 text-saffron" dir="ltr">{c.cmd.trim()}</span><span className="text-[#bfb1a2]">{tx(c.en, c.ar)}</span>
              </button>
            ))}
          </div>
        )}
        <div className={clsx("flex items-end gap-2 rounded-lg border px-3 py-2.5 transition", busy ? "border-[#5a4636]" : "border-[#7a6150] focus-within:border-saffron/70")}>
          <span className="pb-[3px] text-[#a8988a]">&gt;</span>
          <textarea ref={inputRef} value={input} rows={1} disabled={busy}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (showCmds && cmds[0] && input.trim() !== cmds[0].cmd.trim()) { setInput(cmds[0].cmd); return; } send(input); }
              if (e.key === "Tab" && showCmds && cmds[0]) { e.preventDefault(); setInput(cmds[0].cmd); }
            }}
            placeholder={listening ? tx("Listening…", "عم يسمعك…") : tx("Ask about your business… (/ for commands)", "اسأل عن شغلك… (/ للأوامر)")}
            className="max-h-36 min-h-[22px] flex-1 resize-none bg-transparent text-[13px] text-[#F6EEE2] outline-none placeholder:text-[#7d6d60]"
            style={{ fieldSizing: "content" } as React.CSSProperties} />
          <button onClick={toggleVoice} title={tx("Speak", "تحدّث")} className={clsx("rounded p-1", listening ? "text-terra" : "text-[#8f7f70] hover:text-[#EDE3D4]")}>
            {listening ? <MicOff size={15} /> : <Mic size={15} />}
          </button>
          {busy
            ? <button onClick={stop} className="rounded border border-[#7a6150] px-2 py-0.5 text-[11.5px] text-[#EDE3D4] hover:bg-[#3a2f27]">{tx("Stop", "إيقاف")}</button>
            : <button onClick={() => send(input)} className="rounded p-1 text-[#8f7f70] hover:text-saffron" title="Enter"><CornerDownLeft size={15} className="rtl:-scale-x-100" /></button>}
        </div>
        <p className="mt-1.5 flex items-center gap-1.5 px-1 text-[11px] text-[#7d6d60]">
          <ShieldAlert size={11} />{tx("Answers only about your business · read-only access to your data", "بيجاوب بس عن شغلك · وصول للقراءة فقط لبياناتك")}
        </p>
      </div>
    </aside>
  );
}

function IconBtn({ children, onClick, title }: { children: React.ReactNode; onClick: () => void; title: string }) {
  return <button onClick={onClick} title={title} className="grid size-7 place-items-center rounded text-[#a8988a] hover:bg-[#2f2620] hover:text-[#F6EEE2]">{children}</button>;
}

function UserLine({ text }: { text: string }) {
  return (
    <div className="mt-4 flex gap-2 rounded-md bg-[#2a211b] px-2.5 py-2 text-[#d9ccbd] first:mt-0">
      <span className="text-[#8f7f70]">&gt;</span><span className="whitespace-pre-wrap">{text}</span>
    </div>
  );
}

function AssistantMsg({ m, locale }: { m: Msg; locale: string }) {
  return (
    <div className="mt-3 space-y-2">
      {m.blocks.map((b, i) => <BlockView key={i} b={b} locale={locale} />)}
    </div>
  );
}

function BlockView({ b, locale }: { b: Block; locale: string }) {
  const tx = useTx();
  const router = useRouter();
  const [openSql, setOpenSql] = useState(false);
  if (b.kind === "text") {
    return (
      <div className="flex gap-2">
        <span className="mt-[1px] text-[#EDE3D4]">●</span>
        <div className="basira-md min-w-0 flex-1 text-[#EDE3D4]">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{b.text}</ReactMarkdown>
        </div>
      </div>
    );
  }
  if (b.kind === "tool") {
    const t = b.tool;
    const arg = t.args ? Object.values(t.args).filter((v) => typeof v === "string" || typeof v === "number").slice(0, 2).join(", ") : "";
    return (
      <div className="text-[12.5px]">
        <button onClick={() => t.sql && setOpenSql((v) => !v)} className={clsx("flex gap-2 text-start", t.sql && "cursor-pointer")}>
          <span className={clsx(t.done ? (t.ok ? "text-olive" : "text-danger") : "animate-pulse text-saffron")}>●</span>
          <span><span className="font-semibold text-[#F6EEE2]">{t.label}</span>{arg && <span className="text-[#a8988a]">({String(arg).slice(0, 70)})</span>}</span>
        </button>
        {t.done && <p className="ms-5 flex gap-2 text-[#a8988a]"><span>⎿</span><span className="min-w-0 break-words">{t.summary}</span></p>}
        {openSql && t.sql && <pre className="ms-5 mt-1 max-h-48 overflow-auto rounded border border-[#3a2f27] bg-[#16110e] p-2 text-[11px] text-[#cbbca9]" dir="ltr">{t.sql}</pre>}
      </div>
    );
  }
  if (b.kind === "chart") return <InlineChart spec={b.spec} />;
  if (b.kind === "nav") {
    return <p className="ms-5 flex items-center gap-1.5 text-[12px] text-[#9fb07a]"><ArrowUpRight size={13} className="rtl:-scale-x-100" />{tx("Opened", "فتحت")} <span dir="ltr" className="text-[#cbd7a8]">{b.path}</span></p>;
  }
  if (b.kind === "highlight") {
    return <p className="ms-5 text-[12px] text-[#d6a24a]">◎ {b.message}</p>;
  }
  if (b.kind === "draft") {
    const d = b.draft;
    return (
      <div className="ms-5 rounded-lg border border-[#5a4636] bg-[#241c17] p-3 text-[12.5px]">
        <p className="text-[#F6EEE2]">✉ {tx("Draft purchase order", "مسودة طلبية")} — {d.supplier}</p>
        <ul className="mt-2 space-y-0.5 text-[#cfc2b3]">{d.items.map((it) => <li key={it.product_id}>· {locale === "ar" ? it.product_ar || it.product : it.product} × <span className="num">{it.quantity}</span></li>)}</ul>
        {d.note && <p className="mt-2 text-[#a8988a]">{d.note}</p>}
        <button onClick={() => router.push(`/${locale}/app/insights/reorder`)} className="mt-3 rounded border border-[#7a6150] px-2.5 py-1 text-[#F6EEE2] hover:bg-[#3a2f27]">
          {tx("Review & send in reorder planner →", "راجعها وابعثها من مخطط الطلبيات ←")}
        </button>
      </div>
    );
  }
  if (b.kind === "refused") return <p className="ms-5 text-[11.5px] text-[#8f7f70]">⎿ {tx("outside Idrak's scope", "خارج نطاق إدراك")}</p>;
  return <p className="ms-5 text-[12px] text-[#e08a72]">⎿ {b.text}</p>;
}

function InlineChart({ spec }: { spec: ChartSpec }) {
  const option = useMemo(() => {
    if (spec.type === "pie") {
      return { tooltip: { trigger: "item" }, legend: { bottom: 0, textStyle: { color: "#5A4A3F" } },
        series: [{ type: "pie", radius: ["45%", "70%"], data: spec.labels.map((l, i) => ({ name: l, value: spec.series[0]?.values[i] ?? 0 })), label: { show: false } }] };
    }
    return {
      legend: { show: spec.series.length > 1 },
      xAxis: { type: "category", data: spec.labels, ...axisStyle, axisLabel: { ...axisStyle.axisLabel, interval: 0, rotate: spec.labels.length > 5 ? 30 : 0 } },
      yAxis: { type: "value", ...axisStyle },
      series: spec.series.map((s, i) => ({ name: s.name, type: spec.type, data: s.values, smooth: true, barMaxWidth: 26, itemStyle: { color: PALETTE[i], borderRadius: spec.type === "bar" ? [4, 4, 0, 0] : 0 } })),
    };
  }, [spec]);
  return (
    <div className="ms-5 rounded-lg bg-[#FAF6EF] p-3 text-ink" style={{ fontFamily: "var(--font-plex), var(--font-plex-ar), sans-serif" }}>
      <p className="mb-1 text-[12.5px] font-medium">{spec.title}</p>
      <Chart option={option} height={200} />
    </div>
  );
}

function HistoryList({ onPick }: { onPick: (id: string) => void }) {
  const tx = useTx();
  const [rows, setRows] = useState<{ id: string; title: string; updated_at: string }[] | null>(null);
  useEffect(() => { api<typeof rows>("/assistant/sessions").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div className="max-h-64 shrink-0 overflow-y-auto border-b border-[#3a2f27] bg-[#241c17] py-1 text-[12.5px]">
      {!rows && <p className="px-4 py-2 text-[#8f7f70]">…</p>}
      {rows?.length === 0 && <p className="px-4 py-2 text-[#8f7f70]">{tx("No previous chats", "ما في محادثات سابقة")}</p>}
      {rows?.map((r) => (
        <button key={r.id} onClick={() => onPick(r.id)} className="block w-full truncate px-4 py-1.5 text-start text-[#d9ccbd] hover:bg-[#3a2f27]">{r.title}</button>
      ))}
    </div>
  );
}
