import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';
import TbankAccountPicker from './TbankAccountPicker';
import EcomkassaStorePicker from './EcomkassaStorePicker';
import OfdKktPicker from './OfdKktPicker';
import EcomkassaPaymentTypesPicker from './EcomkassaPaymentTypesPicker';
import TochkaAuthMethodPicker from './TochkaAuthMethodPicker';
import TochkaAcquiringPicker from './TochkaAcquiringPicker';
import MoyklassPaymentTypesPicker from './MoyklassPaymentTypesPicker';
import BitrixCategoriesPicker from './BitrixCategoriesPicker';
import {
  ConfigState,
  FieldConfig,
  PROVIDER_FIELDS,
  Provider,
  acceptsIncomingWebhook
} from './providerFieldsConfig';

interface IntegrationConfigStepProps {
  selectedProvider: Provider;
  isEditing: boolean;
  companyId: number;
  integrationId?: number;
  integrationName: string;
  onIntegrationNameChange: (value: string) => void;
  config: ConfigState;
  onConfigChange: (config: ConfigState) => void;
  forwardUrl: string;
  onForwardUrlChange: (value: string) => void;
  visiblePasswords: Record<string, boolean>;
  onTogglePasswordVisibility: (key: string) => void;
  isLoading: boolean;
  onBack: () => void;
  onCancel: () => void;
  onSubmit: () => void;
  onBeforeOAuthRedirect?: () => void;
}

const IntegrationConfigStep = ({
  selectedProvider,
  isEditing,
  companyId,
  integrationId,
  integrationName,
  onIntegrationNameChange,
  config,
  onConfigChange,
  forwardUrl,
  onForwardUrlChange,
  visiblePasswords,
  onTogglePasswordVisibility,
  isLoading,
  onBack,
  onCancel,
  onSubmit,
  onBeforeOAuthRedirect
}: IntegrationConfigStepProps) => {
  const currentFields = PROVIDER_FIELDS[selectedProvider.slug] || [];
  const isTbankAccount = selectedProvider.slug === 'tbank_account';
  const isTochkaAccount = selectedProvider.slug === 'tochka_account';
  const isTochkaAcquiring = selectedProvider.slug === 'tochka_acquiring';
  const isEcomkassa = selectedProvider.slug === 'ecomkassa';
  const isEcomkassaGateway = selectedProvider.slug === 'ecomkassa_gateway';
  const isOfd = selectedProvider.slug === 'ofdru';

  const isConfigValid = () => {
    if (isTbankAccount && !String(config.account_number ?? '').trim()) {
      return false;
    }

    if (isTochkaAccount && config.auth_method === 'oauth'
      ? !String(config.account_number ?? '').trim()
      : isTochkaAccount && !String(config.api_token ?? '').trim()) {
      return false;
    }

    if (isTochkaAcquiring && (config.auth_method === 'oauth'
      ? !String(config.customer_code ?? '').trim()
      : !String(config.api_token ?? '').trim())) {
      return false;
    }

    if (isEcomkassa && (!config.token || !String(config.store_id ?? '').trim())) {
      return false;
    }

    const ofdKkts = Array.isArray(config.kkts) ? config.kkts : config.kkt ? [config.kkt] : [];
    if (isOfd && (!String(config.auth_token ?? '').trim() || ofdKkts.length === 0)) {
      return false;
    }

    return currentFields
      .filter(field => field.required !== false)
      .every(field => {
        const value = config[field.key];
        if (field.type === 'multiselect') {
          return Array.isArray(value) && value.length > 0;
        }
        if (field.validate && field.validate(String(value ?? ''))) return false;
        return value !== undefined && value !== null && String(value).trim() !== '';
      });
  };

  const renderField = (field: FieldConfig) => {
    if (field.type === 'checkbox') {
      return (
        <label key={field.key} className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={!!config[field.key]}
            onChange={(e) => onConfigChange({ ...config, [field.key]: e.target.checked })}
          />
          <span className="text-sm">{field.label}</span>
        </label>
      );
    }

    if (field.type === 'select') {
      return (
        <div key={field.key}>
          <Label>{field.label}</Label>
          <Select
            value={String(config[field.key] ?? field.default ?? '')}
            onValueChange={(value) => onConfigChange({ ...config, [field.key]: value })}
          >
            <SelectTrigger>
              <SelectValue placeholder={field.placeholder} />
            </SelectTrigger>
            <SelectContent>
              {(field.options || []).map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {field.hint && <p className="text-xs text-muted-foreground mt-1">{field.hint}</p>}
        </div>
      );
    }

    if (field.type === 'multiselect') {
      const selected = Array.isArray(config[field.key]) ? (config[field.key] as string[]) : [];
      const toggle = (value: string) => {
        const next = selected.includes(value)
          ? selected.filter((v) => v !== value)
          : [...selected, value];
        onConfigChange({ ...config, [field.key]: next });
      };

      return (
        <div key={field.key} className="space-y-2">
          <Label>{field.label}</Label>
          <div className="space-y-2">
            {(field.options || []).map((opt) => (
              <label key={opt.value} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={() => toggle(opt.value)}
                />
                <span className="text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
          {field.hint && <p className="text-xs text-muted-foreground mt-1">{field.hint}</p>}
        </div>
      );
    }

    if (field.type === 'keywords') {
      return (
        <div key={field.key}>
          <Label htmlFor={field.key}>{field.label}</Label>
          <Input
            id={field.key}
            placeholder={field.placeholder}
            value={(config[field.key] ?? field.default ?? '') as string}
            onChange={(e) => onConfigChange({ ...config, [field.key]: e.target.value })}
          />
          {field.hint && <p className="text-xs text-muted-foreground mt-1">{field.hint}</p>}
        </div>
      );
    }

    const isPassword = field.type === 'password';
    const isVisible = visiblePasswords[field.key];
    const fieldError = field.validate ? field.validate(String(config[field.key] ?? '')) : null;

    return (
      <div key={field.key}>
        <Label htmlFor={field.key}>{field.label}</Label>
        <div className="relative">
          <Input
            id={field.key}
            type={isPassword && !isVisible ? 'password' : field.type === 'number' ? 'number' : 'text'}
            placeholder={field.placeholder}
            value={(config[field.key] ?? '') as string | number}
            onChange={(e) => onConfigChange({
              ...config,
              [field.key]: field.type === 'number' ? Number(e.target.value) : field.normalize ? field.normalize(e.target.value) : e.target.value
            })}
            aria-invalid={!!fieldError}
            className={`${isPassword ? 'pr-10' : ''} ${fieldError ? 'border-destructive focus-visible:ring-destructive' : ''}`}
          />
          {isPassword && (
            <button
              type="button"
              onClick={() => onTogglePasswordVisibility(field.key)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              tabIndex={-1}
            >
              <Icon name={isVisible ? 'EyeOff' : 'Eye'} size={16} />
            </button>
          )}
        </div>
        {fieldError ? (
          <p className="text-xs text-destructive mt-1">{fieldError}</p>
        ) : (
          field.hint && <p className="text-xs text-muted-foreground mt-1">{field.hint}</p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="integration_name">Название (для удобства)</Label>
        <Input
          id="integration_name"
          placeholder="Например: Терминал на кассе №1"
          value={integrationName}
          onChange={(e) => onIntegrationNameChange(e.target.value)}
        />
      </div>

      {isTbankAccount && (
        <TbankAccountPicker
          companyId={companyId}
          accountNumber={String(config.account_number ?? '')}
          onAccountNumberChange={(value) => onConfigChange({ ...config, account_number: value })}
        />
      )}

      {isOfd && (
        <OfdKktPicker
          companyId={companyId}
          config={config}
          onConfigChange={onConfigChange}
          visiblePassword={!!visiblePasswords.auth_token}
          onTogglePasswordVisibility={() => onTogglePasswordVisibility('auth_token')}
        />
      )}

      {isEcomkassa && (
        <EcomkassaStorePicker
          companyId={companyId}
          config={config}
          onConfigChange={onConfigChange}
        />
      )}

      {isEcomkassaGateway && (
        <EcomkassaPaymentTypesPicker
          companyId={companyId}
          config={config}
          onConfigChange={onConfigChange}
        />
      )}

      {isTochkaAccount && (
        <TochkaAuthMethodPicker
          companyId={companyId}
          onBeforeOAuthRedirect={onBeforeOAuthRedirect}
          config={config}
          onConfigChange={onConfigChange}
          visiblePassword={!!visiblePasswords.api_token}
          onTogglePasswordVisibility={() => onTogglePasswordVisibility('api_token')}
        />
      )}

      {isTochkaAcquiring && (
        <TochkaAcquiringPicker
          companyId={companyId}
          config={config}
          onConfigChange={onConfigChange}
          visiblePassword={!!visiblePasswords.api_token}
          onTogglePasswordVisibility={() => onTogglePasswordVisibility('api_token')}
          onBeforeOAuthRedirect={onBeforeOAuthRedirect}
        />
      )}

      {currentFields.map(renderField)}

      {selectedProvider.slug === 'bitrix24' && (
        <BitrixCategoriesPicker
          companyId={companyId}
          integrationId={integrationId}
          config={config}
          onConfigChange={onConfigChange}
        />
      )}

      {selectedProvider.slug === 'moyklass' && (config.stage || 'payment_new') === 'payment_new' && (
        <MoyklassPaymentTypesPicker
          companyId={companyId}
          integrationId={integrationId}
          config={config}
          onConfigChange={onConfigChange}
        />
      )}

      {acceptsIncomingWebhook(selectedProvider.slug) && (
        <div>
          <Label htmlFor="forward_url">URL для переадресации (опционально)</Label>
          <Input
            id="forward_url"
            placeholder="https://your-domain.com/webhook"
            value={forwardUrl}
            onChange={(e) => onForwardUrlChange(e.target.value)}
          />
          <p className="text-xs text-muted-foreground mt-1">
            Данные будут дублироваться на указанный адрес после сохранения в БД
          </p>
        </div>
      )}

      <div className="flex justify-between gap-2">
        {!isEditing && (
          <Button variant="ghost" onClick={onBack}>
            <Icon name="ArrowLeft" size={14} className="mr-2" />
            Назад
          </Button>
        )}
        <div className="flex gap-2 ml-auto">
          <Button variant="outline" onClick={onCancel}>
            Отмена
          </Button>
          <Button
            onClick={onSubmit}
            disabled={isLoading || !isConfigValid()}
          >
            {isLoading ? (
              isEditing ? 'Сохранение...' : 'Создание...'
            ) : (
              isEditing ? 'Сохранить' : 'Далее'
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default IntegrationConfigStep;