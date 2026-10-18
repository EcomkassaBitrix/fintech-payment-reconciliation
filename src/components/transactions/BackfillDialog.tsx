import { useEffect, useRef, useState } from 'react';
import { DateRange } from 'react-day-picker';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { useBackfill } from '@/contexts/BackfillContext';
import { useToast } from '@/hooks/use-toast';
import BackfillPeriodPicker from './backfill/BackfillPeriodPicker';
import BackfillDocTypes from './backfill/BackfillDocTypes';
import BackfillProgress from './backfill/BackfillProgress';
import {
  ActiveSources,
  NamedIntegration,
  Selection,
  buildPlan,
  fetchActiveSources,
  fullSelection,
} from './backfill/backfillSources';

interface BackfillDialogProps {
  ecomkassaIntegrations: NamedIntegration[];
  ofdIntegrations: NamedIntegration[];
  bankIntegrations: NamedIntegration[];
}

// Верхняя граница периода - конец СЕГОДНЯШНЕГО дня: ручная дозагрузка
// должна уметь подтянуть и то, что пришло сегодня.
const endOfToday = () => {
  const d = new Date();
  d.setHours(23, 59, 59, 999);
  return d;
};

const monthAgo = () => {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  d.setHours(0, 0, 0, 0);
  return d;
};

// Диалог - только "витрина" для процесса, который живёт в BackfillContext
// (смонтирован на уровне App.tsx). Свернуть окно не останавливает загрузку.
const BackfillDialog = ({ ecomkassaIntegrations, ofdIntegrations, bankIntegrations }: BackfillDialogProps) => {
  const { currentCompany } = useAuth();
  const companyId = currentCompany?.id;
  const { toast } = useToast();
  const { isDialogOpen, closeDialog, reset, phase, start } = useBackfill();

  const [dateRange, setDateRange] = useState<DateRange>({ from: monthAgo(), to: endOfToday() });
  const dateFrom = dateRange.from ?? monthAgo();
  const dateTo = dateRange.to ?? dateFrom;
  const [selection, setSelection] = useState<Selection>({});
  const [isChecking, setIsChecking] = useState(false);

  const sources: ActiveSources = { ecomkassa: ecomkassaIntegrations, ofd: ofdIntegrations, bank: bankIntegrations };
  const hasAnySource = sources.ecomkassa.length > 0 || sources.ofd.length > 0 || sources.bank.length > 0;
  const plan = buildPlan(selection, sources);
  const hasSelection = Object.keys(plan.typeStatuses).length > 0 || plan.hasOfd || plan.bankIds.length > 0;
  const isRunning = phase === 'running';

  // Новые подключённые интеграции по умолчанию выбраны целиком; выбор,
  // который пользователь уже поменял, не трогаем.
  const seenKeys = useRef<Set<string>>(new Set());
  const sourcesKey = JSON.stringify(sources);
  useEffect(() => {
    const full = fullSelection(sources);
    const fresh = Object.keys(full).filter((k) => !seenKeys.current.has(k));
    if (fresh.length === 0) return;
    fresh.forEach((k) => seenKeys.current.add(k));
    setSelection((prev) => {
      const next = { ...prev };
      fresh.forEach((k) => { next[k] = full[k]; });
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourcesKey]);

  const changeSelection = (key: string, statusIds: string[]) => {
    setSelection((prev) => ({ ...prev, [key]: statusIds }));
  };

  const handleStart = async () => {
    if (!companyId) return;
    setIsChecking(true);
    let fresh: ActiveSources;
    try {
      fresh = await fetchActiveSources(companyId);
    } catch {
      toast({ title: 'Ошибка подключения', description: 'Не удалось проверить интеграции', variant: 'destructive' });
      setIsChecking(false);
      return;
    }
    setIsChecking(false);

    const freshPlan = buildPlan(selection, fresh);
    const orderTypes = Object.keys(freshPlan.typeStatuses);
    const useEcomkassa = fresh.ecomkassa.length > 0 && orderTypes.length > 0;
    const useOfd = freshPlan.hasOfd;
    const banks = fresh.bank.filter((b) => freshPlan.bankIds.includes(b.id));
    const allStatuses = Array.from(new Set(Object.values(freshPlan.typeStatuses).flat()));

    if (!useEcomkassa && !useOfd && banks.length === 0) {
      toast({
        title: 'Нет активных интеграций',
        description: 'Для выбранных документов нет активной интеграции — проверьте раздел «Интеграции»',
        variant: 'destructive'
      });
      return;
    }

    // Календарь отдаёт даты на полночь - конец периода растягиваем до конца дня.
    const from = new Date(dateFrom);
    from.setHours(0, 0, 0, 0);
    const to = new Date(dateTo);
    to.setHours(23, 59, 59, 999);
    start({
      companyId,
      dateFrom: from,
      dateTo: to,
      hasEcomkassa: useEcomkassa,
      orderTypes,
      statuses: allStatuses,
      typeStatuses: freshPlan.typeStatuses,
      hasOfd: useOfd,
      bankIntegrations: banks,
      ecomkassaNames: fresh.ecomkassa.map((i) => i.name),
      ofdNames: fresh.ofd.map((i) => i.name)
    });
  };

  // Закрытие окна во время работы - это просто "свернуть", процесс
  // продолжается в контексте. Сбрасываем прогресс только после завершения.
  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      closeDialog();
      if (phase === 'done') reset();
    }
  };

  return (
    <Dialog open={isDialogOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Icon name="Download" size={20} />
            Дозагрузка исторических данных
          </DialogTitle>
          <DialogDescription>
            Подтянем документы за выбранный период из активных интеграций — пригодится, если часть
            данных не пришла вебхуком. Окно можно закрыть — загрузка продолжится в фоне
          </DialogDescription>
        </DialogHeader>

        {!hasAnySource && phase === 'idle' ? (
          <div className="flex items-center gap-3 bg-muted/50 border border-border rounded-lg p-4">
            <Icon name="AlertTriangle" size={20} className="text-muted-foreground shrink-0" />
            <div className="text-sm text-muted-foreground">
              У компании нет активных интеграций с поддержкой дозагрузки (касса Екомкасса, ОФД
              или расчётный счёт) — сначала подключите их в разделе «Интеграции»
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <BackfillPeriodPicker
              dateRange={dateRange}
              dateFrom={dateFrom}
              dateTo={dateTo}
              maxDate={endOfToday()}
              disabled={isRunning}
              onChange={setDateRange}
            />

            <Separator />

            <BackfillDocTypes selection={selection} sources={sources} disabled={isRunning} onChange={changeSelection} />

            {phase !== 'idle' && (
              <>
                <Separator />
                <BackfillProgress />
              </>
            )}
          </div>
        )}

        <DialogFooter className="flex-col sm:flex-row gap-2">
          {isRunning ? (
            <>
              <Button variant="outline" onClick={() => closeDialog()} className="w-full sm:w-auto gap-2">
                <Icon name="Minimize2" size={14} />
                Свернуть
              </Button>
              <Button disabled className="w-full sm:flex-1 gap-2">
                <Icon name="Loader2" size={16} className="animate-spin" />
                Загружаем…
              </Button>
            </>
          ) : phase === 'done' ? (
            <Button onClick={() => handleOpenChange(false)} className="w-full">
              Готово
            </Button>
          ) : (
            <Button
              onClick={handleStart}
              disabled={!hasAnySource || !hasSelection || isChecking}
              className="w-full gap-2"
            >
              <Icon name={isChecking ? 'Loader2' : 'Download'} size={16} className={isChecking ? 'animate-spin' : ''} />
              {isChecking ? 'Проверяем интеграции…' : 'Начать загрузку'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BackfillDialog;
