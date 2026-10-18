import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';

export interface AutomationQueue {
  waiting: number;
  retry: number;
  processing: number;
  stuck: number;
  failed_day: number;
  oldest_due: string | null;
  companies: { id: number; name: string; stuck: number; failed: number; retry: number }[];
}

interface Props {
  queue: AutomationQueue;
  onRefresh: () => void;
  refreshing: boolean;
}

const Tile = ({ label, value, hint, tone }: { label: string; value: number; hint: string; tone?: 'warn' | 'bad' }) => {
  const color = value > 0 && tone === 'bad' ? 'text-destructive' : value > 0 && tone === 'warn' ? 'text-warning' : 'text-foreground';
  return (
    <div className="rounded-lg border border-border p-3" title={hint}>
      <div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
};

const AutomationQueueStats = ({ queue, onRefresh, refreshing }: Props) => {
  const healthy = queue.stuck === 0 && queue.failed_day === 0;
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Icon name="ListChecks" size={16} />
          Очередь автоматизации
          {healthy ? (
            <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs font-normal text-success">в порядке</span>
          ) : (
            <span className="rounded-full bg-destructive/15 px-2 py-0.5 text-xs font-normal text-destructive">есть проблемы</span>
          )}
        </div>
        <Button size="icon" variant="ghost" onClick={onRefresh} title="Обновить">
          <Icon name="RefreshCw" size={16} className={refreshing ? 'animate-spin' : ''} />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Tile label="Ждут запуска" value={queue.waiting} hint="Новые задания, время которых подошло" />
        <Tile label="В работе" value={queue.processing} hint="Обрабатываются прямо сейчас" />
        <Tile label="Ждут повтора" value={queue.retry} hint="Была ошибка, повтор по расписанию" tone="warn" />
        <Tile label="Зависли" value={queue.stuck} hint="В работе дольше 2 минут: обработка прервалась, подхватятся на следующем запуске" tone="bad" />
        <Tile label="Не удалось за сутки" value={queue.failed_day} hint="Автоповторы закончились, нужен ручной разбор" tone="bad" />
      </div>

      {queue.companies.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-muted-foreground">Компании с проблемными заданиями</div>
          {queue.companies.map((c) => (
            <div key={c.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 rounded-md bg-muted/40 px-3 py-1.5 text-sm">
              <span className="min-w-0 break-words">{c.name}</span>
              <span className="flex gap-3 text-xs tabular-nums">
                {c.stuck > 0 && <span className="text-destructive">зависли: {c.stuck}</span>}
                {c.failed > 0 && <span className="text-destructive">не удалось: {c.failed}</span>}
                {c.retry > 0 && <span className="text-warning">повтор: {c.retry}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AutomationQueueStats;
