import type { Metadata } from "next";
import clsx from "clsx";
import { getCopy, resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { Container, PageHeader } from "@/components/marketing/primitives";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "changelog", "/changelog");
}

const tagCls: Record<string, string> = { new: "bg-olive-soft text-olive", improved: "bg-saffron-soft text-[#8a5d0e]", fixed: "bg-sand text-ink-2" };

export default async function ChangelogPage({ params }: P) {
  const locale = await resolveLocale(params);
  const L = getCopy(locale).changelog;
  return (
    <>
      <PageHeader kicker={L.kicker} title={L.title} sub={L.sub} />
      <Container className="py-16 sm:py-20">
        <ol className="relative">
          {L.entries.map((e) => (
            <li key={e.version} className="grid grid-cols-1 gap-4 border-b border-line py-10 first:pt-0 md:grid-cols-12 md:gap-10">
              <div className="md:col-span-3">
                <p className="num text-[13px] text-terra">v{e.version}</p>
                <p className="mt-1 text-[14.5px] text-ink-2">{e.date}</p>
              </div>
              <div className="md:col-span-9">
                <h2 className="font-serif text-[26px] leading-snug text-ink sm:text-[30px] rtl:font-semibold rtl:leading-[1.5]">{e.title}</h2>
                <ul className="mt-5 space-y-3">
                  {e.items.map((it) => (
                    <li key={it.text} className="flex items-start gap-3 text-[16px] leading-relaxed text-ink-2">
                      <span className={clsx("mt-[3px] w-[4.75rem] shrink-0 rounded-full px-2 py-0.5 text-center text-[11.5px] font-medium", tagCls[it.tag])}>
                        {L.tags[it.tag as keyof typeof L.tags]}
                      </span>
                      {it.text}
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ol>
      </Container>
    </>
  );
}
