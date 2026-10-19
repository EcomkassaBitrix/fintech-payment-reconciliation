import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Icon from '@/components/ui/icon';
import NotificationCenter from '@/components/NotificationCenter';
import AppHeader from '@/components/layout/AppHeader';
import AppSidebar from '@/components/layout/AppSidebar';
import AccessManagement from './AccessManagement';
import IntegrationsPage from './IntegrationsPage';
import AutomationPage from './AutomationPage';
import EventsPage from './EventsPage';
import TransactionsPage from './TransactionsPage';
import ReconciliationPage from './ReconciliationPage';
import NotificationsPage from '@/pages/NotificationsPage';
import SettingsPlaceholder from './SettingsPlaceholder';
import { useAuth } from '@/contexts/AuthContext';
import { useAutomationHeartbeat } from '@/hooks/useAutomationHeartbeat';
import { usePageBanners } from '@/hooks/usePageBanners';
import PageBanner from '@/components/banners/PageBanner';
import { useNotifications, AppNotification } from '@/hooks/useNotifications';
import { canOpenModule, defaultModuleFor, effectiveModules, isLockedByTariff } from '@/config/modules';
import TariffLockedScreen from '@/components/layout/TariffLockedScreen';
import OnboardingWizard from '@/components/onboarding/OnboardingWizard';
import SubscriptionPage from './SubscriptionPage';
import SubscriptionBlockedNotice from '@/components/subscription/SubscriptionBlockedNotice';
import { DateFilter } from '@/components/filters/DateRangeFilter';
import { TYPE_FILTERS, TypeFilter, TypeFilterKey } from '@/lib/transactionTypeFilter';

const Index = () => {
  const { currentCompany, user, cronEnabled } = useAuth();
  // null - пользователь ещё не выбирал раздел, открываем стартовый доступный.
  const [searchParams] = useSearchParams();
  const [activeModule, setActiveModule] = useState<string | null>(() => searchParams.get('section'));
  const [showNotifications, setShowNotifications] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // Раздел, из которого пришли в «Подписку» с экрана закрытого раздела - подсветить тарифы.
  const [upgradeFor, setUpgradeFor] = useState<string | null>(null);
  const [transactionsDateFilter, setTransactionsDateFilter] = useState<DateFilter | null>(null);
  const [transactionsTypeFilter, setTransactionsTypeFilter] = useState<TypeFilter | null>(null);
  const [transactionsUnmatchedOnly, setTransactionsUnmatchedOnly] = useState(false);
  // Меняется при каждом переходе с фильтрами - «Транзакции» пересоздаются и
  // применяют их, даже если раздел уже открыт.
  const [transactionsNavKey, setTransactionsNavKey] = useState(0);
  // Платёжка, для которой сразу открыть новый сценарий чеков в «Автоматизации».
  const [receiptSourceId, setReceiptSourceId] = useState<number | null>(null);
  // Раздел интеграций, который сразу открыть в окне подключения (переход из «Сверки»).
  const [integrationCategory, setIntegrationCategory] = useState<string | null>(null);

  // Переход из «Сверки» (плитки, столбцы графика) в «Транзакции» сразу с
  // фильтром на нужный период.
  const openTransactionsForPeriod = (from: Date, to: Date, typeKey?: TypeFilterKey, unmatchedOnly = false) => {
    setTransactionsDateFilter({ from, to });
    setTransactionsTypeFilter(typeKey ? TYPE_FILTERS[typeKey] : null);
    setTransactionsUnmatchedOnly(unmatchedOnly);
    setTransactionsNavKey((k) => k + 1);
    setActiveModule('transactions');
  };


  const openFromNotification = (n: AppNotification) => {
    const day = typeof n.payload?.date === 'string' ? n.payload.date : null;
    if (n.link_module === 'transactions' && day) {
      const [y, m, d] = day.split('-').map(Number);
      const date = new Date(y, m - 1, d);
      setTransactionsDateFilter({ from: date, to: date });
      setTransactionsTypeFilter(null);
      setTransactionsUnmatchedOnly(n.kind === 'missing_receipts');
      setTransactionsNavKey((k) => k + 1);
      setActiveModule('transactions');
      return;
    }
    if (n.link_module) handleModuleChange(n.link_module);
  };

  const roleModules = effectiveModules(currentCompany);
  // «Настройки» открыты всем: там личные уведомления, а общие настройки компании
  // страница сама скрывает от ролей без этого раздела.
  const canOpen = (id: string) => id === 'settings' || id === 'subscription' || id === 'notifications' || canOpenModule(roleModules, id);
  // Раздел, недоступный роли (ссылка из уведомления, смена компании), не открываем -
  // показываем стартовый раздел роли.
  // Раздел есть в роли, но закрыт тарифом - открываем экран с предложением сменить тариф.
  // Подписка закончилась - кабинет закрыт, всегда открыт только экран подписки и оплаты.
  const subscriptionBlocked = !!currentCompany?.subscription_blocked;
  const lockedModule = !subscriptionBlocked && activeModule && isLockedByTariff(currentCompany, activeModule) ? activeModule : null;
  const shownModule = subscriptionBlocked
    ? 'subscription'
    : lockedModule ?? (activeModule && canOpen(activeModule) ? activeModule : defaultModuleFor(roleModules));
  const canOpenTransactions = canOpen('transactions');

  const handleModuleChange = (id: string) => {
    setTransactionsUnmatchedOnly(false);
    setTransactionsDateFilter(null);
    setTransactionsTypeFilter(null);
    setUpgradeFor(null);
    setActiveModule(id);
  };

  const companyId = currentCompany?.id;
  useAutomationHeartbeat(subscriptionBlocked ? undefined : companyId, cronEnabled);
  const notifications = useNotifications(companyId, user?.user_id);
  const banners = usePageBanners();



  return (
    <div className="min-h-screen bg-background">
      {showNotifications && (
        <NotificationCenter
          items={notifications.items}
          unread={notifications.unread}
          isLoading={notifications.isLoading}
          onClose={() => setShowNotifications(false)}
          onMarkRead={notifications.markRead}
          onHide={notifications.hide}
          onReload={notifications.reload}
          onOpen={openFromNotification}
        />
      )}

      <AppHeader
        onOpenSubscription={() => handleModuleChange('subscription')}
        subscriptionActive={shownModule === 'subscription'}
        onOpenMenu={() => setMenuOpen(true)}
        unreadCount={notifications.unread}
        onShowNotifications={() => {
          setShowNotifications(true);
          notifications.reload();
        }}
      />


      {!subscriptionBlocked && <OnboardingWizard
        onConnect={
          canOpen('integrations')
            ? (slug) => {
                handleModuleChange('integrations');
                setIntegrationCategory(slug);
              }
            : undefined
        }
        onSetupReceipts={
          canOpen('automation')
            ? (id) => {
                setReceiptSourceId(id);
                handleModuleChange('automation');
              }
            : undefined
        }
      />}

      <AppSidebar activeModule={shownModule ?? ''} onModuleChange={handleModuleChange} open={menuOpen} onClose={() => setMenuOpen(false)} />

      <main className="lg:ml-64 mt-16 p-4 sm:p-6 lg:p-8">
        {lockedModule && <TariffLockedScreen
            moduleId={lockedModule}
            onUpgrade={() => {
              handleModuleChange('subscription');
              setUpgradeFor(lockedModule);
            }}
          />}
        {shownModule && !lockedModule && banners.forPage(shownModule).map((b) => <PageBanner key={b.page} banner={b} />)}
        {!lockedModule && shownModule === 'reconciliation' && (
          <ReconciliationPage
            onOpenTransactions={canOpenTransactions ? openTransactionsForPeriod : undefined}
            onConnectIntegration={
              canOpen('integrations')
                ? (slug) => {
                    handleModuleChange('integrations');
                    setIntegrationCategory(slug);
                  }
                : undefined
            }
          />
        )}
        {!lockedModule && shownModule === 'events' && <EventsPage />}
        {!lockedModule && shownModule === 'transactions' && <TransactionsPage key={transactionsNavKey} initialDateFilter={transactionsDateFilter} initialTypeFilter={transactionsTypeFilter} initialUnmatchedOnly={transactionsUnmatchedOnly} />}
        {!lockedModule && shownModule === 'automation' && (
          <AutomationPage prefillSourceId={receiptSourceId} onPrefillUsed={() => setReceiptSourceId(null)} />
        )}
        {!lockedModule && shownModule === 'integrations' && (
          <IntegrationsPage
            openCategorySlug={integrationCategory}
            onCategoryOpened={() => setIntegrationCategory(null)}
            onSetupReceipts={
              canOpen('automation')
                ? (id) => {
                    setReceiptSourceId(id);
                    handleModuleChange('automation');
                  }
                : undefined
            }
          />
        )}
        {!lockedModule && shownModule === 'access' && <AccessManagement />}
        {!lockedModule && shownModule === 'settings' && <SettingsPlaceholder />}
        {!lockedModule && shownModule === 'notifications' && <NotificationsPage />}
        {subscriptionBlocked && <SubscriptionBlockedNotice />}
        {!lockedModule && shownModule === 'subscription' && <SubscriptionPage highlightModule={upgradeFor} />}
        {!shownModule && (
          <div className="mx-auto mt-24 max-w-md text-center text-muted-foreground">
            <Icon name="Lock" size={40} className="mx-auto mb-4" />
            <p className="font-medium text-foreground">Нет доступных разделов</p>
            <p className="mt-1 text-sm">В вашей роли не включён ни один раздел. Обратитесь к владельцу компании.</p>
          </div>
        )}
      </main>
    </div>
  );
};

export default Index;