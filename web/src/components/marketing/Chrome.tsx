"use client";
import { usePathname } from "next/navigation";

export function Chrome({ nav, footer, children }: { nav: React.ReactNode; footer: React.ReactNode; children: React.ReactNode }) {
  const pathname = usePathname() || "";
  const bare = /^\/(ar|en)\/links\/?$/.test(pathname);
  if (bare) return <main id="main">{children}</main>;
  return (
    <>
      {nav}
      <main id="main" className="min-h-[60vh]">{children}</main>
      {footer}
    </>
  );
}
