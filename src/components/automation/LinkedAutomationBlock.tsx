import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import { JOB_STATUS, JobStatus } from './automationConfig';
import functionUrls from '../../../backend/func2url.json';

export type AutomationRefKind = 'payment' | 'payment_row' | 'receipt' | 'receipt_row' | 'crm' | 'invoice';

interface LinkedDocument {
  operation: string;
  doc_kind: string;
  uuid: string | null;
  status: string | null;
  total: number | null;
}

interface LinkedJob {
  id: number;
  scenario_name: string;
  status: JobStatus;
  attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  created_at: string;
  updated_at: string;
  last_message: string | null;
  documents: LinkedDocument[];
}

const DOC_STATUS: Record<string, string> = { done: 'пробит', wait: 'ожидает кассу', fail: 'ошибка кассы' };

const docLabel = (d: LinkedDocument) => {
  const kind = d.operation.endsWith('_correction') ? 'Чек коррекции' : d.operation.startsWith('sell_refund') ? 'Чек возврата'
    : d.doc_kind === 'order' ? 'Заказ' : 'Чек';
  const sum = d.total !== null ? ` · ${Number(d.total).toFixed(2)} ₽` : '';
  return `${kind}${d.uuid ? ` #${d.uuid}` : ''}${sum}`;
};

interface LinkedAutomationBlockProps {
  kind: AutomationRefKind;
  refValue: string | number | null | undefined;
}

const LinkedAutomationBlock = ({ kind, refValue }: LinkedAutomationBlockProps) => {
  const { currentCompany } = useAuth();
  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;
  const [jobs, setJobs] = useState<LinkedJob[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!currentCompany?.id || refValue === null || refValue === undefined || refValue === '') return;
    setJobs(null);
    setError(false);
    const params = new URLSearchParams({ company_id: String(currentCompany.id), for: kind, ref: String(refValue) });
    fetch(`${functionUrls['automation-jobs']}?${params}`)
      .then((r) => r.json())
      .then((data) => (data.success ? setJobs(data.jobs || []) : setError(true)))
      .catch(() => setError(true));
  }, [currentCompany?.id, kind, refValue]);

  if (refValue === null || refValue === undefined || refValue === '') return null;

  return (
    <div className="space-y-3">
      <h3 className="flex items-center gap-2 font-semibold">
        <Icon name="Workflow" size={18} />
        Автоматизация
      </h3>
      {error && <p className="text-sm text-muted-foreground">Не удалось загрузить данные автоматизации</p>}
      {!error && jobs === null && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="Loader2" size={14} className="animate-spin" /> Загрузка…
        </p>
      )}
      {jobs && jobs.length === 0 && (
        <p className="text-sm text-muted-foreground">По этому событию сценарии автоматизации не запускались</p>
      )}
      {jobs && jobs.length > 0 && (
        <div className="space-y-2">
          {jobs.map((job) => {
            const st = JOB_STATUS[job.status] || JOB_STATUS.new;
            return (
              <div key={job.id} className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-words font-medium">{job.scenario_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Задание #{job.id} · {formatDateTime(job.created_at, timezone, true)}
                      {job.attempts > 1 ? ` · попыток: ${job.attempts}` : ''}
                    </p>
                  </div>
                  <Badge variant="outline" className={st.className}>{st.label}</Badge>
                </div>
                {job.documents.map((d, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                    <Icon name="Receipt" size={14} className="text-muted-foreground" />
                    <span className="break-all">{docLabel(d)}</span>
                    {d.status && <span className="text-xs text-muted-foreground">({DOC_STATUS[d.status] || d.status})</span>}
                  </div>
                ))}
                {(job.status === 'error' || job.status === 'failed') && job.last_error ? (
                  <p className="break-words text-xs text-destructive [overflow-wrap:anywhere]">{job.last_error}</p>
                ) : job.last_message ? (
                  <p className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">{job.last_message}</p>
                ) : null}
              </div>
            );
          })}
          <a href="/app?section=automation" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
            Открыть журнал автоматизации <Icon name="ArrowRight" size={14} />
          </a>
        </div>
      )}
    </div>
  );
};

export default LinkedAutomationBlock;
