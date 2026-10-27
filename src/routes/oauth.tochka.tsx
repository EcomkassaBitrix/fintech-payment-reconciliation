import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import TochkaOAuthCallback from "@/pages/TochkaOAuthCallback";

export const Route = createFileRoute("/oauth/tochka")({
  ssr: false,
  pendingComponent: RoutePending,
  component: TochkaOAuthCallback,
});
