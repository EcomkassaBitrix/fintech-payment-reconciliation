import { createFileRoute } from "@tanstack/react-router";
import PromoLinkPage from "@/pages/PromoLinkPage";

export const Route = createFileRoute("/promo/$code")({
  component: PromoLinkPage,
});
