import type { Metadata } from "next";
import { resolveLocale } from "@/components/marketing/copy";
import { pageMeta } from "@/components/marketing/meta";
import { HealthCheck } from "@/components/marketing/HealthCheck";

type P = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: P): Promise<Metadata> {
  return pageMeta(await resolveLocale(params), "healthCheck", "/health-check");
}

export default function HealthCheckPage() {
  return <HealthCheck />;
}
