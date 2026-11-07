import clsx from "clsx";

export const scoreTone = (v: number) => (v < 50 ? "terra" : v < 80 ? "saffron" : "olive");
const toneStroke = { terra: "var(--color-terra)", saffron: "var(--color-saffron)", olive: "var(--color-olive)" } as const;

export function Gauge({ value, ghost, size = 240, className, label, children }: {
  value: number; ghost?: number; size?: number; className?: string; label?: string; children?: React.ReactNode;
}) {
  const v = Math.max(0, Math.min(100, value));
  const tone = scoreTone(v);
  return (
    <div className={clsx("relative", className)} style={{ width: size, height: size * 0.6 }} role="img" aria-label={label}>
      <svg viewBox="0 0 200 120" className="absolute inset-0 h-full w-full rtl:-scale-x-100" aria-hidden>
        {Array.from({ length: 11 }).map((_, i) => {
          const a = Math.PI - (i / 10) * Math.PI;
          const r1 = 96, r2 = i % 5 === 0 ? 89 : 92;
          return <line key={i} x1={100 + r1 * Math.cos(a)} y1={108 - r1 * Math.sin(a)} x2={100 + r2 * Math.cos(a)} y2={108 - r2 * Math.sin(a)} stroke="var(--color-ink-3)" strokeOpacity={0.45} strokeWidth={1} />;
        })}
        <path d="M 20 108 A 80 80 0 0 1 180 108" fill="none" stroke="var(--color-sand)" strokeWidth={12} strokeLinecap="round" pathLength={100} />
        {ghost !== undefined && (
          <path d="M 20 108 A 80 80 0 0 1 180 108" fill="none" stroke="var(--color-olive)" strokeOpacity={0.22} strokeWidth={12} strokeLinecap="round" pathLength={100} strokeDasharray={`${Math.max(0.01, ghost)} 100`} />
        )}
        <path
          d="M 20 108 A 80 80 0 0 1 180 108"
          fill="none"
          stroke={toneStroke[tone]}
          strokeWidth={12}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${Math.max(0.01, v)} 100`}
          style={{ transition: "stroke 400ms ease" }}
        />
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center">{children}</div>
    </div>
  );
}
