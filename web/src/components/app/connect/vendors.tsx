"use client";
import { useState } from "react";
import clsx from "clsx";

/** POS vendors shown in "Connect a new system". Only "available" ones can be selected, and
 *  only when the server says their connector is configured here; "soon" ones are display-only
 *  (no button, no form) until a real, tested connector exists. */
export type Vendor = { code: string; name: string; status: "available" | "soon" };
export const POS_VENDORS: Vendor[] = [
  { code: "loyverse", name: "Loyverse POS", status: "available" },
  { code: "foodics", name: "Foodics", status: "soon" },
  { code: "odoo", name: "Odoo POS", status: "soon" },
  { code: "shopify", name: "Shopify POS", status: "soon" },
  { code: "square", name: "Square POS", status: "soon" },
  { code: "lightspeed", name: "Lightspeed POS", status: "soon" },
];

/** Official vendor logo from /logos/<code>.svg, at one consistent size; a neutral monogram
 *  when the file isn't there, so a missing asset never shows a broken image. */
export function VendorLogo({ code, name, size = 40, className }: { code: string; name: string; size?: number; className?: string }) {
  const [failed, setFailed] = useState(false);
  const box = { width: size, height: size };
  if (failed) {
    return (
      <span aria-hidden style={box} className={clsx("grid shrink-0 place-items-center rounded-xl border border-line bg-paper font-serif text-[15px] text-ink-2", className)}>
        {name.trim().charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <span style={box} className={clsx("grid shrink-0 place-items-center overflow-hidden rounded-xl border border-line bg-white p-1.5", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- small static brand asset */}
      <img src={`/logos/${code}.svg`} alt={`${name} logo`} className="max-h-full max-w-full object-contain" onError={() => setFailed(true)} />
    </span>
  );
}
