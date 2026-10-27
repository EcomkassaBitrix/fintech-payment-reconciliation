import { createFileRoute } from "@tanstack/react-router";
import functionUrls from "../../backend/func2url.json";
import PricingPage from "@/pages/PricingPage";
import type { Tariff } from "@/components/landing/PricingSection";

const TITLE = "Тарифы и цены — Сверка";
const DESCRIPTION =
  "Стоимость сервиса автоматической сверки платежей, чеков 54-ФЗ и поступлений на расчётный счёт. Бесплатный пробный период, оплата за месяц или год со скидкой.";
const URL = "https://s-verka.ru/pricing";

export const Route = createFileRoute("/pricing")({
  loader: async (): Promise<{ tariffs: Tariff[] | null }> => {
    try {
      const res = await fetch((functionUrls as Record<string, string>)["tariffs-list"]);
      const data = await res.json();
      return { tariffs: data.success && data.tariffs?.length ? (data.tariffs as Tariff[]) : null };
    } catch {
      return { tariffs: null };
    }
  },
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:url", content: URL },
    ],
    links: [{ rel: "canonical", href: URL }],
  }),
  component: Page,
});

function Page() {
  const { tariffs } = Route.useLoaderData();
  return <PricingPage tariffs={tariffs} />;
}
