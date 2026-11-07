import { Nav } from "@/components/marketing/Nav";
import { Footer } from "@/components/marketing/Footer";
import { Chrome } from "@/components/marketing/Chrome";
import { resolveLocale } from "@/components/marketing/copy";

export default async function MarketingLayout({ children, params }: { children: React.ReactNode; params: Promise<{ locale: string }> }) {
  const locale = await resolveLocale(params);
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <Chrome nav={<Nav />} footer={<Footer locale={locale} />}>
        {children}
      </Chrome>
    </div>
  );
}
