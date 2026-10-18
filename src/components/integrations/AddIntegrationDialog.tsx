import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { GOALS, reachGoal } from '@/lib/metrika';
import functionUrls from '../../../backend/func2url.json';
import {
  Category,
  ConfigState,
  DEFAULT_WEBHOOK_SETTINGS,
  Provider,
  UserIntegration,
  acceptsIncomingWebhook,
  buildDefaultConfig,
  PROVIDER_FIELDS
} from './providerFieldsConfig';
import IntegrationCategoryStep from './IntegrationCategoryStep';
import IntegrationProviderStep from './IntegrationProviderStep';
import IntegrationConfigStep from './IntegrationConfigStep';
import IntegrationSuccessStep from './IntegrationSuccessStep';
import { TochkaOAuthDraft, saveTochkaDraft } from './tochkaOAuthDraft';

interface AddIntegrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  initialCategory: Category | null;
  editingIntegration: UserIntegration | null;
  allProviders: Provider[];
  connectedProviderIds: number[];
  companyId: number;
  onSuccess: () => void;
  onSetupReceipts?: (integrationId: number) => void;
  restoredDraft?: TochkaOAuthDraft | null;
}

const AddIntegrationDialog = ({
  open,
  onOpenChange,
  categories,
  initialCategory,
  editingIntegration,
  allProviders,
  connectedProviderIds,
  companyId,
  onSuccess,
  onSetupReceipts,
  restoredDraft
}: AddIntegrationDialogProps) => {
  const [createdIntegrationId, setCreatedIntegrationId] = useState<number | null>(null);
  const getInitialStep = () => {
    if (editingIntegration) return 2;
    if (initialCategory) return 1;
    return 0;
  };

  const [step, setStep] = useState(getInitialStep());
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(initialCategory);
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(
    editingIntegration ? allProviders.find(p => p.id === editingIntegration.provider_id) || null : null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [integrationName, setIntegrationName] = useState(editingIntegration?.integration_name || '');
  const [config, setConfig] = useState<ConfigState>(editingIntegration?.config || {});
  const [forwardUrl, setForwardUrl] = useState(editingIntegration?.forward_url || '');
  const [visiblePasswords, setVisiblePasswords] = useState<Record<string, boolean>>({});
  const { toast } = useToast();

  useEffect(() => {
    if (!open) return;

    if (restoredDraft && !restoredDraft.integrationId) {
      const draftSlug = restoredDraft.providerSlug || 'tochka_account';
      const prov = allProviders.find(p => p.slug === draftSlug) || null;
      setStep(2);
      setSelectedProvider(prov);
      setSelectedCategory(categories.find(c => c.providers.some(p => p.slug === draftSlug)) || null);
      setIntegrationName(restoredDraft.integrationName);
      setConfig(restoredDraft.config);
      setForwardUrl('');
    } else if (editingIntegration) {
      const prov = allProviders.find(p => p.id === editingIntegration.provider_id) || null;
      setStep(2);
      setSelectedProvider(prov);
      setSelectedCategory(categories.find(c => c.providers.some(p => p.id === editingIntegration.provider_id)) || null);
      setIntegrationName(editingIntegration.integration_name || '');
      setConfig(restoredDraft?.integrationId === editingIntegration.id
        ? restoredDraft.config
        : editingIntegration.config || buildDefaultConfig(prov?.slug || ''));
      setForwardUrl(editingIntegration.forward_url || '');
    } else {
      setStep(initialCategory ? 1 : 0);
      setSelectedCategory(initialCategory);
      setSelectedProvider(null);
      setIntegrationName('');
      setConfig({});
      setForwardUrl('');
    }
    setWebhookUrl('');
    setVisiblePasswords({});
  }, [open, editingIntegration, initialCategory, allProviders, categories, restoredDraft]);

  const handlePickCategory = (category: Category) => {
    setSelectedCategory(category);
    setStep(1);
  };

  const handlePickProvider = (prov: Provider) => {
    setSelectedProvider(prov);
    setConfig(buildDefaultConfig(prov.slug));
    setStep(2);
  };

  const handleCreate = async () => {
    if (!selectedProvider) return;

    setIsLoading(true);
    try {
      // У банков частота сохраняется всегда - если список не трогали, берём значение по умолчанию.
      const intervalField = (PROVIDER_FIELDS[selectedProvider.slug] || []).find((f) => f.key === 'sync_interval_hours');
      const syncIntervalHours = config.sync_interval_hours
        ? Number(config.sync_interval_hours)
        : intervalField?.default
          ? Number(intervalField.default)
          : undefined;

      if (editingIntegration) {
        const response = await fetch(functionUrls['integrations-list'], {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            integration_id: editingIntegration.id,
            company_id: companyId,
            integration_name: integrationName,
            config,
            forward_url: acceptsIncomingWebhook(selectedProvider.slug) ? forwardUrl : '',
            sync_interval_hours: syncIntervalHours
          })
        });

        const data = await response.json();

        if (response.ok && data.success) {
          toast(data.warning ? { title: 'Интеграция обновлена', description: data.warning } : { title: 'Интеграция обновлена' });
          handleFinish();
        } else {
          toast({
            title: data.error_code === 'invalid_credentials' ? 'Банк не принял данные' : 'Ошибка',
            description: data.error || 'Не удалось обновить',
            variant: 'destructive'
          });
        }
      } else {
        const response = await fetch(functionUrls['integrations-list'], {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            company_id: companyId,
            provider_slug: selectedProvider.slug,
            integration_name: integrationName || selectedProvider.name,
            config,
            webhook_settings: DEFAULT_WEBHOOK_SETTINGS,
            forward_url: acceptsIncomingWebhook(selectedProvider.slug) ? forwardUrl : '',
            sync_interval_hours: syncIntervalHours
          })
        });

        const data = await response.json();

        if (response.ok && data.success) {
          reachGoal(GOALS.integrationAdded, { provider: selectedProvider.slug });
          setWebhookUrl(data.webhook_url || '');
          setCreatedIntegrationId(data.integration_id || null);
          setStep(3);
          toast({
            title: 'Интеграция создана',
            description: data.warning || 'Теперь настройте подключение на стороне сервиса'
          });
        } else {
          toast({
            title: data.error_code === 'invalid_credentials' ? 'Банк не принял данные' : 'Ошибка',
            description: data.error || 'Не удалось создать интеграцию',
            variant: 'destructive'
          });
        }
      }
    } catch (error) {
      toast({
        title: 'Ошибка подключения',
        description: 'Проверьте интернет-соединение',
        variant: 'destructive'
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleFinish = () => {
    setStep(0);
    setSelectedCategory(null);
    setSelectedProvider(null);
    setIntegrationName('');
    setConfig({});
    setWebhookUrl('');
    onSuccess();
    onOpenChange(false);
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(webhookUrl);
    toast({
      title: 'Скопировано',
      description: 'URL скопирован в буфер обмена'
    });
  };

  const togglePasswordVisibility = (key: string) => {
    setVisiblePasswords(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl w-[calc(100vw-2rem)] overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {editingIntegration
              ? 'Редактирование интеграции'
              : step === 0
                ? 'Добавить интеграцию'
                : step === 1
                  ? selectedCategory?.name
                  : 'Настройка интеграции'}
          </DialogTitle>
          <DialogDescription>
            {editingIntegration
              ? 'Измените настройки интеграции'
              : step === 0
                ? 'Выберите, что подключаем — покажу только нужные настройки'
                : step === 1
                  ? selectedCategory?.description || 'Выберите сервис для подключения'
                  : 'Заполните данные для подключения'}
          </DialogDescription>
        </DialogHeader>

        {step === 0 && !editingIntegration && (
          <IntegrationCategoryStep
            categories={categories}
            onSelectCategory={handlePickCategory}
          />
        )}

        {step === 1 && selectedCategory && !editingIntegration && (
          <IntegrationProviderStep
            selectedCategory={selectedCategory}
            connectedProviderIds={connectedProviderIds}
            onSelectProvider={handlePickProvider}
            onBack={() => setStep(0)}
          />
        )}

        {step === 2 && selectedProvider && (
          <IntegrationConfigStep
            selectedProvider={selectedProvider}
            isEditing={!!editingIntegration}
            companyId={companyId}
            integrationId={editingIntegration?.id}
            integrationName={integrationName}
            onIntegrationNameChange={setIntegrationName}
            config={config}
            onConfigChange={setConfig}
            forwardUrl={forwardUrl}
            onForwardUrlChange={setForwardUrl}
            visiblePasswords={visiblePasswords}
            onTogglePasswordVisibility={togglePasswordVisibility}
            isLoading={isLoading}
            onBack={() => setStep(1)}
            onCancel={() => onOpenChange(false)}
            onSubmit={handleCreate}
            onBeforeOAuthRedirect={() => saveTochkaDraft({
              companyId,
              integrationId: editingIntegration?.id ?? null,
              providerSlug: selectedProvider.slug,
              integrationName,
              config: { ...config, auth_method: 'oauth' }
            })}
          />
        )}

        {step === 3 && selectedProvider && (
          <IntegrationSuccessStep
            selectedProvider={selectedProvider}
            stage={String(config.stage || (selectedProvider.slug === 'realtycalendar' ? 'income' : 'payment_new'))}
            webhookUrl={webhookUrl}
            autoWebhook={selectedProvider.slug === 'tochka_acquiring' && config.auth_method === 'oauth'}
            onCopyWebhookUrl={copyToClipboard}
            onFinish={handleFinish}
            onSetupReceipts={
              onSetupReceipts && createdIntegrationId
                ? () => {
                    const id = createdIntegrationId;
                    handleFinish();
                    onSetupReceipts(id);
                  }
                : undefined
            }
          />
        )}
      </DialogContent>
    </Dialog>
  );
};

export default AddIntegrationDialog;