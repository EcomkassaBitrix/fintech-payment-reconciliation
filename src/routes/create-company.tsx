import { createFileRoute } from "@tanstack/react-router";
import RoutePending from "@/components/route/RoutePending";
import CreateCompany from "@/pages/CreateCompany";

export const Route = createFileRoute("/create-company")({
  ssr: false,
  pendingComponent: RoutePending,
  component: CreateCompany,
});
