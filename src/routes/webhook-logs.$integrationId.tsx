import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import RequireAuth from "@/components/RequireAuth";
import WebhookLogsPage from "@/pages/WebhookLogsPage";

export const Route = createFileRoute("/webhook-logs/$integrationId")({
  ssr: false,
  pendingComponent: RoutePending,
  component: Page,
});

function Page() {
  return (
    <RequireAuth>
      <WebhookLogsPage />
    </RequireAuth>
  );
}
