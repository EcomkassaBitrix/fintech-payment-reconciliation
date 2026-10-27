import { createFileRoute } from "@tanstack/react-router";
import LegalDocumentPage from "@/pages/LegalDocumentPage";

const TITLE = "Публичная оферта — Сверка";

export const Route = createFileRoute("/offer")({
  head: () => ({
    meta: [{ title: TITLE }, { property: "og:title", content: TITLE }],
  }),
  component: Page,
});

function Page() {
  return <LegalDocumentPage doc="offer" />;
}
