"use client";
import { useEffect, useState } from "react";

export default function HealthGauge({ from, to, size = 260, label, animate = true }: { from: number; to: number; size?: number; label?: string; animate?: boolean }) {
  const [v, setV] = useState(animate ? from : to);
  useEffect(() => {
    if (!animate) { setV(to); return; }
    setV(from);
    let raf = 0;
    const t0 = performance.now() + 500;
    const dur = 1800;
    const tick = (t: number) => {
      const p = Math.min(1, Math.max(0, (t - t0) / dur));
      const e = 1 - Math.pow(1 - p, 3);
      setV(from + (to - from) * e);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [from, to, animate]);
  const r = 100, cx = 120, cy = 120;
  const arc = Math.PI * r;
  const color = v < 50 ? "#B3412E" : v < 75 ? "#D99A2B" : "#6B7A3A";
  return (
    <div className="relative" style={{ width: size, height: size * 0.62 }} dir="ltr">
      <svg viewBox="0 0 240 145" width={size} height={size * 0.62}>
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#EFE6D8" strokeWidth="16" strokeLinecap="round" />
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke={color} strokeWidth="16" strokeLinecap="round"
          strokeDasharray={arc} strokeDashoffset={arc * (1 - v / 100)} style={{ transition: "stroke .4s" }} />
        {[0, 25, 50, 75, 100].map((t) => {
          const a = Math.PI * (1 - t / 100);
          return <line key={t} x1={cx + Math.cos(a) * (r - 14)} y1={cy - Math.sin(a) * (r - 14)} x2={cx + Math.cos(a) * (r - 20)} y2={cy - Math.sin(a) * (r - 20)} stroke="#C9B9A3" strokeWidth="1.5" />;
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-1 text-center">
        <p className="num text-[44px] font-semibold leading-none" style={{ color }}>{v.toFixed(0)}</p>
        {label && <p className="mt-1 text-[12px] text-ink-3">{label}</p>}
      </div>
    </div>
  );
}
