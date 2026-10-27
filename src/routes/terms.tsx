import { createFileRoute } from "@tanstack/react-router";
import LegalDocumentPage from "@/pages/LegalDocumentPage";

const TITLE = "Пользовательское соглашение — Сверка";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [{ title: TITLE }, { property: "og:title", content: TITLE }],
  }),
  component: Page,
});

function Page() {
  return <LegalDocumentPage doc="terms" />;
}
