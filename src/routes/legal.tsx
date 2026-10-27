import { createFileRoute } from "@tanstack/react-router";
import LegalDocumentPage from "@/pages/LegalDocumentPage";

const TITLE = "Политика в отношении обработки персональных данных — Сверка";

export const Route = createFileRoute("/legal")({
  head: () => ({
    meta: [{ title: TITLE }, { property: "og:title", content: TITLE }],
  }),
  component: Page,
});

function Page() {
  return <LegalDocumentPage doc="privacy" />;
}
