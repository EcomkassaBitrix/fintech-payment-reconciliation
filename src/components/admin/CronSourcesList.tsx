import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { formatDateTime } from '@/lib/formatDate';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';

export interface CronSourceIntegration {
  id: number;
  name: string | null;
  company: string;
  last_synced_at: string | null;
}

export interface CronSourceRun {
  loaded: number;
  calls: number;
  failed: number;
  finished_at: string | null;
  error: string | null;
  pending?: number;
}

export interface CronDayStats {
  runs: number;
  errors: number;
  last_error: string | null;
  last_error_at: string | null;
}

export interface CronSource {
  key: string;
  unit: string;
  interval: string;
  last_run: CronSourceRun | null;
  day_stats?: CronDayStats;
  name: string;
  hint: string;
  enabled: boolean;
  integrations: CronSourceIntegration[];
}

const INTERVAL_OPTIONS = [
  { value: 'cron', label: 'По крону' },
  { value: '1h', label: 'Раз в час' },
  { value: '12h', label: 'Раз в 12 часов' },
  { value: '1d', label: 'Раз в день' }
];

interface Props {
  sources: CronSource[];
  values: Record<string, boolean>;
  intervals: Record<string, string>;
  onChange: (key: string, enabled: boolean) => void;
  onIntervalChange: (key: string, interval: string) => void;
  onRunNow?: (key: string) => void;
  running?: string | null;
}

const lastSync = (src: CronSource) =>
  src.integrations.map((i) => i.last_synced_at).filter(Boolean).sort().pop() || null;

const CronSourcesList = ({ sources, values, intervals, onChange, onIntervalChange, onRunNow, running }: Props) => (
  <div className="space-y-2">
    <div className="text-sm font-medium">Что загружать автоматически</div>
    <div className="divide-y divide-border rounded-lg border border-border">
      {sources.map((src) => {
        const on = values[src.key] ?? src.enabled;
        return (
          <div key={src.key} className="flex items-start gap-3 p-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{src.name}</span>
                {src.day_stats && src.day_stats.runs > 0 && (
                  <span
                    title={
                      src.day_stats.last_error
                        ? `Последняя ошибка ${formatDateTime(src.day_stats.last_error_at!, undefined, true)}: ${src.day_stats.last_error}`
                        : undefined
                    }
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      src.day_stats.errors > 0 ? 'bg-destructive/15 text-destructive' : 'bg-success/15 text-success'
                    }`}
                  >
                    За сутки: {src.day_stats.errors > 0 ? `ошибок ${src.day_stats.errors} из ${src.day_stats.runs}` : `без ошибок, ${src.day_stats.runs} запусков`}
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">{src.hint}</div>
              {src.last_run?.finished_at && (
                <div className={`mt-1 text-xs ${src.last_run.failed ? 'text-destructive' : 'text-foreground'}`}>
                  {src.last_run.failed && src.last_run.failed === src.last_run.calls
                    ? `Не загрузилось ${formatDateTime(src.last_run.finished_at, undefined, true)}: ${src.last_run.error || 'ошибка'}`
                    : `Загрузили ${src.last_run.loaded} ${src.unit} ${formatDateTime(src.last_run.finished_at, undefined, true)}`}
                  {src.last_run.failed > 0 && src.last_run.failed < src.last_run.calls && ` · с ошибкой: ${src.last_run.failed} из ${src.last_run.calls}`}
                  {src.last_run.pending
                    ? src.key === 'subscriptions'
                      ? ' · не все успели, продолжим при следующем запуске'
                      : ' · банк ещё формирует выписку, заберём при следующем запуске'
                    : ''}
                </div>
              )}
              {src.integrations.length > 0 && (
                <div className="mt-1 text-xs text-muted-foreground">
                  Подключено у компаний: {new Set(src.integrations.map((i) => i.company)).size}
                  {lastSync(src) && <> · последняя загрузка {formatDateTime(lastSync(src)!, undefined, true)}</>}
                </div>
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              <div className="flex items-center gap-2">
                <span className={`text-xs ${on ? 'text-foreground' : 'text-muted-foreground'}`}>{on ? 'Да' : 'Нет'}</span>
                <Switch checked={on} onCheckedChange={(v) => onChange(src.key, v)} />
              </div>
              <Select value={intervals[src.key] ?? src.interval} onValueChange={(v) => onIntervalChange(src.key, v)} disabled={!on}>
                <SelectTrigger className="h-8 w-40 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERVAL_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value} className="text-xs">{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {onRunNow && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 w-40 gap-1.5 text-xs"
                  disabled={!!running}
                  onClick={() => onRunNow(src.key)}
                >
                  <Icon
                    name={running === src.key ? 'Loader2' : 'Play'}
                    size={14}
                    className={running === src.key ? 'animate-spin' : ''}
                  />
                  Загрузить сейчас
                </Button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

export default CronSourcesList;