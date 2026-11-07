import { Plus } from "lucide-react";
import { Container, Kicker } from "./primitives";

export function Faq({ kicker, title, items, id = "faq", bg }: { kicker?: string; title: string; items: { q: string; a: string }[]; id?: string; bg?: string }) {
  return (
    <section aria-labelledby={`${id}-title`} className={`border-b border-line ${bg ?? ""}`}>
      <Container className="grid grid-cols-1 gap-10 py-20 sm:py-28 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-4">
          {kicker && <Kicker className="mb-4">{kicker}</Kicker>}
          <h2 id={`${id}-title`} className="font-serif text-[32px] font-[400] leading-[1.1] tracking-[-0.018em] text-ink sm:text-[40px] rtl:font-semibold rtl:leading-[1.4] rtl:tracking-normal">{title}</h2>
        </div>
        <div className="border-t border-ink/80 lg:col-span-8">
          {items.map((it) => (
            <details key={it.q} className="group border-b border-line">
              <summary className="flex cursor-pointer list-none items-start justify-between gap-6 py-5 text-[17px] font-medium text-ink outline-none transition-colors hover:text-terra-2 focus-visible:text-terra-2 [&::-webkit-details-marker]:hidden">
                <span>{it.q}</span>
                <Plus size={18} aria-hidden className="mt-1 shrink-0 text-ink-3 transition-transform duration-200 group-open:rotate-45" />
              </summary>
              <p className="max-w-[62ch] pb-6 pe-10 text-[16px] leading-[1.7] text-ink-2">{it.a}</p>
            </details>
          ))}
        </div>
      </Container>
    </section>
  );
}
