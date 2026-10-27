import Icon from "@/components/ui/icon";

// Server fallback of browser-only routes: the same spinner the pages show while the session loads.
const RoutePending = () => (
  <div className="min-h-screen flex items-center justify-center bg-background">
    <Icon name="Loader2" className="animate-spin text-primary" size={32} />
    <span className="sr-only">
      Сверка — электронный бухгалтер. Сверяет все платежи с чеками без вашего участия. Загружаем страницу личного
      кабинета, подождите несколько секунд…
    </span>
  </div>
);

export default RoutePending;