"use client";
import { useState } from "react";
import { publicApi } from "@/lib/api";
import { Spinner } from "@/components/ui";
import { useCopy } from "./use-copy";
import { Arrow } from "./primitives";

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function WaitlistMini() {
  const { c, locale } = useCopy();
  const w = c.waitlistMini;
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err" | "invalid">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim())) return setState("invalid");
    setState("busy");
    try {
      await publicApi("/public/waitlist", {
        method: "POST",
        json: { email: email.trim(), name: null, business_name: null, business_type: null, city: null, locale },
      });
      setState("ok");
    } catch {
      setState("err");
    }
  }

  if (state === "ok") {
    return <p role="status" className="rounded-xl border border-paper/15 px-4 py-3.5 text-[15px] text-paper">{w.success}</p>;
  }

  return (
    <form onSubmit={submit} noValidate className="w-full">
      <label htmlFor="footer-waitlist" className="sr-only">{w.label}</label>
      <div className="flex h-12 items-center rounded-full border border-paper/20 bg-paper/[0.04] pe-1.5 ps-5 focus-within:border-paper/50">
        <input
          id="footer-waitlist"
          type="email"
          inputMode="email"
          autoComplete="email"
          dir="ltr"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (state === "invalid" || state === "err") setState("idle");
          }}
          placeholder={w.placeholder}
          aria-invalid={state === "invalid" || undefined}
          aria-describedby="footer-waitlist-msg"
          className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-paper outline-none placeholder:text-paper/40 rtl:text-right"
        />
        <button
          type="submit"
          disabled={state === "busy"}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-paper px-4 text-[14px] font-medium text-ink transition-colors hover:bg-sand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-saffron disabled:opacity-70"
        >
          {state === "busy" && <Spinner size={14} />}
          {w.button}
          {state !== "busy" && <Arrow size={14} />}
        </button>
      </div>
      <p id="footer-waitlist-msg" role="alert" className="mt-2 min-h-[20px] text-[13px] text-saffron">
        {state === "invalid" ? w.invalid : state === "err" ? w.error : ""}
      </p>
    </form>
  );
}
