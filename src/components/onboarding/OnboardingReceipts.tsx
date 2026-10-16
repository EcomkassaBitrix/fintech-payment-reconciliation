import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { UserIntegration } from '@/components/integrations/integrationsPageTypes';
import { suggestsReceiptScenario } from '@/components/integrations/providerFieldsConfig';

interface Props {
  items: UserIntegration[];
  isLoading: boolean;
  onSetupReceipts?: (integrationId: number) => void;
}

const OnboardingReceipts = ({ items, isLoading, onSetupReceipts }: Props) => {
  const sources = items.filter((i) => suggestsReceiptScenario(i.provider_slug));
  const hasCashRegister = items.some((i) => i.category_slug === 'cash_registers');

  if (isLoading) return <Icon name="Loader2" size={20} className="animate-spin text-muted-foreground" />;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Если платёжный сервис сам не пробивает чеки, создайте автоматизацию: при каждой оплате чек будет пробиваться
        через вашу кассу автоматически. Если чеки уже пробиваются — шаг можно пропустить.
      </p>

      {!hasCashRegister && (
        <div className="flex gap-2 rounded-lg bg-warning/10 p-3 text-sm">
          <Icon name="TriangleAlert" size={16} className="mt-0.5 shrink-0 text-warning" />
          <span>Касса не подключена — без неё пробивать чеки не через что. Вернитесь на шаг назад и подключите кассу.</span>
        </div>
      )}

      {sources.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          Нет платёжных сервисов, для которых нужна автоматизация чеков.
        </div>
      ) : (
        sources.map((i) => (
          <div key={i.id} className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:flex-row sm:items-center">
            <div className="flex-1">
              <div className="text-sm font-medium">{i.integration_name || i.provider_name}</div>
              <div className="text-xs text-muted-foreground">{i.provider_name}</div>
            </div>
            {i.receipts_enabled ? (
              <span className="flex items-center gap-1 text-sm text-success">
                <Icon name="CheckCircle" size={16} />
                Чеки создаются
              </span>
            ) : onSetupReceipts ? (
              <Button size="sm" className="gap-1.5" disabled={!hasCashRegister} onClick={() => onSetupReceipts(i.id)}>
                <Icon name="Workflow" size={14} />
                Настроить чеки
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">Нет доступа к автоматизации</span>
            )}
          </div>
        ))
      )}
    </div>
  );
};

export default OnboardingReceipts;
