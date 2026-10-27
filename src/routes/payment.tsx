import { createFileRoute } from "@tanstack/react-router";
import LegalDocumentPage from "@/pages/LegalDocumentPage";

const TITLE = "Оплата, возврат и безопасность платежей — Сверка";

export const Route = createFileRoute("/payment")({
  head: () => ({
    meta: [{ title: TITLE }, { property: "og:title", content: TITLE }],
  }),
  component: Page,
});

function Page() {
  return <LegalDocumentPage doc="payment" />;
}
