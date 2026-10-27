import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import YookassaOAuthCallback from "@/pages/YookassaOAuthCallback";

export const Route = createFileRoute("/oauth/yookassa")({
  ssr: false,
  pendingComponent: RoutePending,
  component: YookassaOAuthCallback,
});
