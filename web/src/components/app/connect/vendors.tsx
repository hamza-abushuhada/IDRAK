"use client";
import { useState } from "react";
import clsx from "clsx";

/** POS vendors shown in "Connect a new system". Only "available" ones can be selected, and
 *  only when the server says their connector is configured here; "soon" ones are display-only
 *  (no button, no form) until a real, tested connector exists.
 *  `logo` = an official logo file exists in /public/logos (sources: docs/brand-logos.md). */
export type Vendor = { code: string; name: string; status: "available" | "soon"; logo: boolean };
export const POS_VENDORS: Vendor[] = [
  { code: "loyverse", name: "Loyverse POS", status: "available", logo: true },
  { code: "foodics", name: "Foodics", status: "soon", logo: true },
  { code: "odoo", name: "Odoo POS", status: "soon", logo: true },
  { code: "shopify", name: "Shopify POS", status: "soon", logo: false },
  { code: "square", name: "Square POS", status: "soon", logo: false },
  { code: "lightspeed", name: "Lightspeed POS", status: "soon", logo: true },
];
const HAS_LOGO = new Set(POS_VENDORS.filter((v) => v.logo).map((v) => v.code));

/** Official vendor logo (wordmark) in one consistent wide frame, original colors on white.
 *  Without an approved file it shows a neutral initial; a load error never shows a broken image. */
export function VendorLogo({ code, name, size = "md", className }: { code: string; name: string; size?: "sm" | "md"; className?: string }) {
  const [failed, setFailed] = useState(false);
  const frame = size === "sm" ? "h-9 w-[84px]" : "h-11 w-[96px]";
  if (failed || !HAS_LOGO.has(code)) {
    return (
      <span aria-hidden className={clsx("grid shrink-0 place-items-center rounded-xl border border-line bg-paper font-serif text-[15px] text-ink-2", frame, className)}>
        {name.trim().charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <span className={clsx("grid shrink-0 place-items-center rounded-xl border border-line bg-white px-2.5 py-2", frame, className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- small static brand asset */}
      <img src={`/logos/${code}.svg`} alt={name} className="max-h-full max-w-full object-contain" onError={() => setFailed(true)} />
    </span>
  );
}
