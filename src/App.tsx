
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { BackfillProvider } from "@/contexts/BackfillContext";
import RequireAuth from "@/components/RequireAuth";
import MaintenanceGate from "@/components/MaintenanceGate";
import RequireAdmin from "@/components/RequireAdmin";
import YandexMetrika from "@/components/YandexMetrika";
import Index from "./pages/Index";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import CreateCompany from "./pages/CreateCompany";
import Admin from "./pages/Admin";
import NotFound from "./pages/NotFoundPage";
import WebhookLogsPage from "./pages/WebhookLogsPage";
import InvitePage from "./pages/InvitePage";
import TochkaOAuthCallback from "./pages/TochkaOAuthCallback";
import YookassaOAuthCallback from "./pages/YookassaOAuthCallback";
import LegalDocumentPage from "./pages/LegalDocumentPage";
import PromoLinkPage from "./pages/PromoLinkPage";
import PendingPromoActivator from "@/components/PendingPromoActivator";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <YandexMetrika />
        <AuthProvider>
          <BackfillProvider>
            <MaintenanceGate>
            <PendingPromoActivator />
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/create-company" element={<CreateCompany />} />
              <Route path="/invite/:token" element={<InvitePage />} />
              <Route path="/promo/:code" element={<PromoLinkPage />} />
              <Route path="/oauth/tochka" element={<TochkaOAuthCallback />} />
              <Route path="/oauth/yookassa" element={<YookassaOAuthCallback />} />
              <Route path="/terms" element={<LegalDocumentPage doc="terms" />} />
              <Route path="/legal" element={<LegalDocumentPage doc="privacy" />} />
              <Route path="/payment" element={<LegalDocumentPage doc="payment" />} />
              <Route path="/app" element={<RequireAuth><Index /></RequireAuth>} />
              <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
              <Route path="/webhook-logs/:integrationId" element={<RequireAuth><WebhookLogsPage /></RequireAuth>} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
            </MaintenanceGate>
          </BackfillProvider>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;