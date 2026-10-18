import { useCallback, useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import { AutomationJob, JOB_STATUS } from './automationConfig';
import functionUrls from '../../../backend/func2url.json';

interface HistoryItem {
  level: string;
  message: string;
  created_at: string;
}

interface AutomationJournalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SOURCE_LABELS: Record<string, string> = { payment: 'Платёж', crm_deal: 'Сделка CRM', crm_lead: 'Лид Битрикс24', ecom_invoice: 'Счёт Екомкассы' };

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'Все' },
  { value: 'error', label: 'Повтор' },
  { value: 'failed', label: 'Не удалось' },
  { value: 'done', label: 'Выполнены' },
  { value: 'ready', label: 'Собраны' }
];

// «В работе» дольше блокировки (2 мин) - обработка прервалась, задание можно повторить вручную.
const STUCK_MS = 3 * 60_000;
const isStuck = (job: { status: string; updated_at?: string | null }) =>
  job.status === 'processing' && !!job.updated_at &&
  Date.now() - new Date(job.updated_at.endsWith('Z') ? job.updated_at : `${job.updated_at}Z`).getTime() > STUCK_MS;

const URL_RE = /(https?:\/\/[^\s)]+)/g;

const Message = ({ text }: { text: string }) => (
  <>
    {text.split(URL_RE).map((part, i) =>
      i % 2 === 1 ? (
        <a
          key={i}
          href={part}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-0.5 font-medium text-primary underline-offset-2 hover:underline"
        >
          открыть
          <Icon name="ExternalLink" size={12} />
        </a>
      ) : (
        <span key={i}>{part.replace(/\(\s*$/, '').replace(/^\s*\)/, '')}</span>
      )
    )}
  </>
);

const AutomationJournal = ({ open, onOpenChange }: AutomationJournalProps) => {
  const { currentCompany } = useAuth();
  const { toast } = useToast();
  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;
  const [jobs, setJobs] = useState<AutomationJob[]>([]);
  const [filter, setFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [retrying, setRetrying] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!currentCompany) return;
    setIsLoading(true);
    try {
      const params = new URLSearchParams({ company_id: String(currentCompany.id), limit: '200' });
      if (filter) params.set('status', filter);
      const res = await fetch(`${functionUrls['automation-jobs']}?${params}`);
      const data = await res.json();
      if (res.ok) setJobs(data.jobs || []);
    } finally {
      setIsLoading(false);
    }
  }, [currentCompany, filter]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const toggle = async (job: AutomationJob) => {
    if (expanded === job.id) {
      setExpanded(null);
      return;
    }
    setExpanded(job.id);
    setHistory([]);
    const res = await fetch(`${functionUrls['automation-jobs']}?company_id=${currentCompany?.id}&job_id=${job.id}`);
    const data = await res.json();
    setHistory(data.history || []);
  };

  const retry = async (job: AutomationJob) => {
    setRetrying(job.id);
    try {
      const res = await fetch(functionUrls['automation-jobs'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'retry', company_id: currentCompany?.id, job_id: job.id })
      });
      const data = await res.json();
      if (!res.ok) toast({ title: 'Не удалось повторить', description: data.error, variant: 'destructive' });
      setExpanded(null);
      await load();
    } finally {
      setRetrying(null);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-4 sm:max-w-xl sm:p-6 lg:max-w-2xl">
        <SheetHeader className="pr-8 text-left">
          <SheetTitle className="flex items-center gap-2">
            <Icon name="ScrollText" size={20} />
            Журнал
          </SheetTitle>
          <SheetDescription>Задания сценариев: что пришло, что собрано, где ошибка</SheetDescription>
        </SheetHeader>

        <div className="mt-4 flex items-center gap-2">
          <div className="-mx-1 flex min-w-0 flex-1 gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none] sm:flex-wrap sm:overflow-visible [&::-webkit-scrollbar]:hidden">
            {FILTERS.map((f) => (
              <Button
                key={f.value}
                size="sm"
                className="shrink-0"
                variant={filter === f.value ? 'default' : 'outline'}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </Button>
            ))}
          </div>
          <Button size="icon" variant="ghost" className="shrink-0 self-start" onClick={load} title="Обновить">
            <Icon name="RefreshCw" size={16} className={isLoading ? 'animate-spin' : ''} />
          </Button>
        </div>

        <div className="mt-4 space-y-2">
          {jobs.length === 0 && !isLoading && (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              Заданий пока нет. Они появятся, когда запущенный сценарий получит событие.
            </div>
          )}
          {jobs.map((job) => {
            const st = JOB_STATUS[job.status] || JOB_STATUS.new;
            return (
              <div key={job.id} className="overflow-hidden rounded-lg border border-border">
                <button type="button" onClick={() => toggle(job)} className="flex w-full min-w-0 items-start gap-3 p-3 text-left hover:bg-muted/40">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="min-w-0 break-words text-sm font-medium">{job.scenario_name}</span>
                      <Badge variant="outline" className={`shrink-0 ${st.className}`}>{st.label}</Badge>
                    </div>
                    <div className="mt-1 break-words text-xs text-muted-foreground">
                      {SOURCE_LABELS[job.source_type] || job.source_type} #{job.source_id} · {formatDateTime(job.created_at, timezone)}
                      {job.attempts > 1 && ` · попыток: ${job.attempts}`}
                      {job.status === 'error' && job.next_attempt_at && ` · следующая попытка ${formatDateTime(job.next_attempt_at, timezone, true)}`}
                    </div>
                    {job.last_error && <div className="mt-1 break-words text-xs text-destructive [overflow-wrap:anywhere]">{job.last_error}</div>}
                    {isStuck(job) && (
                      <div className="mt-1 text-xs text-muted-foreground">Обработка прервалась - задание повторится автоматически, или нажмите «Повторить сейчас»</div>
                    )}
                    {job.status === 'failed' && (
                      <div className="mt-1 text-xs text-muted-foreground">Автоповторы закончились - проверьте причину и нажмите «Повторить сейчас»</div>
                    )}
                  </div>
                  <Icon name={expanded === job.id ? 'ChevronUp' : 'ChevronDown'} size={16} className="mt-1 shrink-0 text-muted-foreground" />
                </button>
                {expanded === job.id && (
                  <div className="space-y-3 border-t border-border bg-muted/20 p-3 sm:space-y-2">
                    {history.map((h, i) => (
                      <div key={i} className="flex flex-col gap-0.5 text-xs sm:flex-row sm:gap-3">
                        <span className="shrink-0 tabular-nums text-muted-foreground">{formatDateTime(h.created_at, timezone, true)}</span>
                        <span className={`min-w-0 break-words [overflow-wrap:anywhere] ${h.level === 'error' ? 'text-destructive' : ''}`}>
                          <Message text={h.message} />
                        </span>
                      </div>
                    ))}
                    {(job.status === 'error' || job.status === 'failed' || isStuck(job)) && (
                      <Button size="sm" variant="outline" className="gap-1.5" disabled={retrying === job.id} onClick={() => retry(job)}>
                        <Icon name={retrying === job.id ? 'Loader2' : 'RotateCw'} size={14} className={retrying === job.id ? 'animate-spin' : ''} />
                        Повторить сейчас
                      </Button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default AutomationJournal;
