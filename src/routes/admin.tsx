import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import RequireAdmin from "@/components/RequireAdmin";
import Admin from "@/pages/Admin";

export const Route = createFileRoute("/admin")({
  ssr: false,
  pendingComponent: RoutePending,
  component: Page,
});

function Page() {
  return (
    <RequireAdmin>
      <Admin />
    </RequireAdmin>
  );
}
