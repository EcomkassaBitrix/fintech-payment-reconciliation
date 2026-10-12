import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import AddIntegrationDialog from '@/components/integrations/AddIntegrationDialog';
import DeleteIntegrationDialog from '@/components/integrations/DeleteIntegrationDialog';
import IntegrationsCategoryList from '@/components/integrations/IntegrationsCategoryList';
import { useIntegrationsPageData } from '@/components/integrations/useIntegrationsPageData';
import { TochkaOAuthDraft, takeTochkaDraft } from '@/components/integrations/tochkaOAuthDraft';

interface IntegrationsPageProps {
  onSetupReceipts?: (integrationId: number) => void;
}

const IntegrationsPage = ({ onSetupReceipts }: IntegrationsPageProps) => {
  const {
    categories,
    userIntegrations,
    allProviders,
    editingIntegration,
    deletingIntegration,
    showAddDialog,
    setShowAddDialog,
    showDeleteDialog,
    setShowDeleteDialog,
    isLoading,
    loadingStatement,
    expandedIds,
    companyId,
    fetchIntegrations,
    toggleExpand,
    handleAddNew,
    handleEdit,
    handleDeleteClick,
    handleDeleteConfirm,
    copyWebhookUrl,
    formatDate,
    handleSyncStatement,
    handleToggleActive,
    handleEnableReceipts,
    togglingId,
    getCategoryIntegrations
  } = useIntegrationsPageData();
  const [restoredDraft, setRestoredDraft] = useState<TochkaOAuthDraft | null>(null);

  // Вернулись из Точки после подтверждения доступа - открываем ту же форму, чтобы сразу выбрать счёт.
  useEffect(() => {
    if (isLoading || !companyId || allProviders.length === 0) return;
    const draft = takeTochkaDraft(companyId);
    if (!draft) return;
    const editing = draft.integrationId ? userIntegrations.find((i) => i.id === draft.integrationId) : null;
    setRestoredDraft(draft);
    if (editing) {
      handleEdit(editing);
    } else {
      handleAddNew();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, companyId, allProviders.length]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Icon name="Loader2" className="animate-spin mx-auto mb-2" size={32} />
          <p className="text-muted-foreground">Загрузка интеграций...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2">Интеграции</h2>
          <p className="text-muted-foreground">
            Подключено сервисов: {userIntegrations.length}
          </p>
        </div>
        <Button onClick={handleAddNew}>
          <Icon name="Plus" size={16} className="mr-2" />
          Добавить интеграцию
        </Button>
      </div>

      <IntegrationsCategoryList
        categories={categories}
        userIntegrations={userIntegrations}
        getCategoryIntegrations={getCategoryIntegrations}
        expandedIds={expandedIds}
        onToggleExpand={toggleExpand}
        onEdit={handleEdit}
        onDeleteClick={handleDeleteClick}
        onCopyWebhookUrl={copyWebhookUrl}
        formatDate={formatDate}
        loadingStatement={loadingStatement}
        onSyncStatement={handleSyncStatement}
        onToggleActive={handleToggleActive}
        togglingId={togglingId}
        onSetupReceipts={onSetupReceipts}
        onEnableReceipts={handleEnableReceipts}
        onAddNew={handleAddNew}
      />

      <AddIntegrationDialog
        open={showAddDialog}
        onOpenChange={(o) => {
          setShowAddDialog(o);
          if (!o) setRestoredDraft(null);
        }}
        categories={categories}
        initialCategory={null}
        editingIntegration={editingIntegration}
        allProviders={allProviders}
        connectedProviderIds={userIntegrations.map(ui => ui.provider_id)}
        companyId={companyId || 0}
        onSuccess={fetchIntegrations}
        onSetupReceipts={onSetupReceipts}
        restoredDraft={restoredDraft}
      />

      <DeleteIntegrationDialog
        deletingIntegration={deletingIntegration}
        showDeleteDialog={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
};

export default IntegrationsPage;