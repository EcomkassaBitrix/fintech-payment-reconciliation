import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import RequireAuth from "@/components/RequireAuth";
import Index from "@/pages/Index";

export const Route = createFileRoute("/app")({
  ssr: false,
  pendingComponent: RoutePending,
  component: Page,
});

function Page() {
  return (
    <RequireAuth>
      <Index />
    </RequireAuth>
  );
}
