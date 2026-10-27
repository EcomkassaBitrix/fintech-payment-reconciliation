import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import Login from "@/pages/Login";

export const Route = createFileRoute("/login")({
  ssr: false,
  pendingComponent: RoutePending,
  component: Login,
});
