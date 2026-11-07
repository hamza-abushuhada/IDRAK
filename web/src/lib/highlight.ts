"use client";
export function highlight(target: string, message?: string, timeoutMs = 6000) {
  const started = Date.now();
  const tryFind = () => {
    const el = document.querySelector<HTMLElement>(`[data-basira="${CSS.escape(target)}"]`);
    if (!el) {
      if (Date.now() - started < timeoutMs) setTimeout(tryFind, 250);
      return;
    }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("basira-highlight");
    document.querySelectorAll(".basira-tip").forEach((t) => t.remove());
    if (message) {
      const tip = document.createElement("div");
      tip.className = "basira-tip";
      tip.setAttribute("role", "status");
      tip.style.cssText = "position:absolute;z-index:60;max-width:300px;background:#2B211B;color:#FAF6EF;padding:10px 12px;border-radius:10px;font-size:13px;line-height:1.5;box-shadow:0 12px 30px -12px rgba(0,0,0,.45);pointer-events:none;transition:opacity .3s";
      tip.innerHTML = `<div style="display:flex;gap:8px;align-items:flex-start"><span style="margin-top:6px;width:7px;height:7px;border-radius:50%;background:#D99A2B;flex:none"></span><span></span></div>`;
      (tip.querySelector("span:last-child") as HTMLElement).textContent = message;
      document.body.appendChild(tip);
      const place = () => {
        const r = el.getBoundingClientRect();
        const top = window.scrollY + r.bottom + 12;
        const rtl = document.documentElement.dir === "rtl";
        const left = rtl ? Math.max(12, window.scrollX + r.right - 300) : Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - 312);
        tip.style.top = `${top}px`;
        tip.style.left = `${Math.max(12, left)}px`;
      };
      place();
      setTimeout(place, 600);
      setTimeout(() => { tip.style.opacity = "0"; setTimeout(() => tip.remove(), 400); }, 7000);
    }
    setTimeout(() => el.classList.remove("basira-highlight"), 7000);
  };
  tryFind();
}

export function visibleElements(): string[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-basira]")).map((e) => e.dataset.basira!).filter(Boolean).slice(0, 60);
}
