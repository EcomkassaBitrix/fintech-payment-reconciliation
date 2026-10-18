import { Progress } from '@/components/ui/progress';
import Icon from '@/components/ui/icon';
import { useBackfill } from '@/contexts/BackfillContext';

// Блок прогресса - как был: полоса Екомкассы, строки ОФД и банков, ошибки.
// Показывает только те источники, которые реально участвовали в запуске
// (lastConfig), а не все подключённые.
const StatusIcon = ({ loading }: { loading: boolean }) =>
  loading ? (
    <Icon name="Loader2" size={13} className="animate-spin" />
  ) : (
    <Icon name="CheckCircle2" size={13} className="text-success" />
  );

const BackfillProgress = () => {
  const { phase, ecomkassaProgress, ofdResult, bankResults, errors, lastConfig } = useBackfill();
  if (phase === 'idle' || !lastConfig) return null;

  return (
    <div className="space-y-3">
      {lastConfig.hasEcomkassa && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Екомкасса ({(lastConfig.ecomkassaNames || []).join(', ')})
            </span>
            <span className="font-medium">
              {ecomkassaProgress.total > 0
                ? `${Math.min(ecomkassaProgress.processed, ecomkassaProgress.total)} из ${ecomkassaProgress.total} · загружено ${ecomkassaProgress.inserted}`
                : phase === 'running' ? 'Ищем документы…' : 'Готово'}
            </span>
          </div>
          <Progress
            value={ecomkassaProgress.total > 0 ? Math.min(100, (ecomkassaProgress.processed / ecomkassaProgress.total) * 100) : (phase === 'running' ? 10 : 100)}
          />
        </div>
      )}

      {lastConfig.hasOfd && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground flex items-center gap-2">
            <StatusIcon loading={phase === 'running' && !ofdResult} />
            ОФД ({(lastConfig.ofdNames || []).join(', ')})
          </span>
          <span className="font-medium">
            {ofdResult ? `загружено ${ofdResult.inserted} из ${ofdResult.total}` : phase === 'running' ? 'Загрузка…' : ''}
          </span>
        </div>
      )}

      {[...(lastConfig.acquiringIntegrations || []), ...lastConfig.bankIntegrations].map((bi) => {
        const result = bankResults[bi.id];
        return (
          <div key={bi.id} className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground flex items-center gap-2">
              <StatusIcon loading={phase === 'running' && !result} />
              {bi.name}
            </span>
            <span className="font-medium">
              {result ? `загружено ${result.inserted} из ${result.total}` : phase === 'running' ? 'Загрузка…' : ''}
            </span>
          </div>
        );
      })}

      {errors.length > 0 && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 space-y-1">
          {errors.map((err, i) => (
            <div key={i} className="text-xs text-destructive flex items-start gap-1.5">
              <Icon name="XCircle" size={13} className="shrink-0 mt-0.5" />
              {err}
            </div>
          ))}
        </div>
      )}

      {phase === 'done' && errors.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-success">
          <Icon name="CheckCircle2" size={14} />
          Загрузка завершена
        </div>
      )}
    </div>
  );
};

export default BackfillProgress;