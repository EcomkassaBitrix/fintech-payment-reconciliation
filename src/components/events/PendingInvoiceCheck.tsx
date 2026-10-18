import { useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import functionUrls from '../../../backend/func2url.json';

interface Props {
  companyId: number;
  invoiceUuid: string;
}

type Verdict = 'paid' | 'not_paid' | 'unknown';

const VIEW: Record<Verdict, { icon: string; className: string; title: string }> = {
  paid: { icon: 'CircleCheck', className: 'border-success/40 bg-success/10 text-success', title: 'Оплачен' },
  not_paid: { icon: 'CircleX', className: 'border-destructive/40 bg-destructive/10 text-destructive', title: 'Не оплачен' },
  unknown: { icon: 'CircleHelp', className: 'border-border bg-muted/50 text-muted-foreground', title: 'Не удалось проверить' }
};

// Только спрашивает банк и показывает ответ: транзакцию и чек создаёт сценарий «Расхождение».
const PendingInvoiceCheck = ({ companyId, invoiceUuid }: Props) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ verdict: Verdict; message: string } | null>(null);

  const check = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(functionUrls['automation-jobs'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'check_invoice', company_id: companyId, invoice_uuid: invoiceUuid })
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data?.success) {
        setResult({ verdict: 'unknown', message: data?.error || 'Сервис не ответил, попробуйте ещё раз' });
      } else {
        setResult({ verdict: data.verdict as Verdict, message: data.message });
      }
    } catch {
      setResult({ verdict: 'unknown', message: 'Нет связи, попробуйте ещё раз' });
    } finally {
      setLoading(false);
    }
  };

  const view = result ? VIEW[result.verdict] || VIEW.unknown : null;

  return (
    <div className="space-y-3">
      <h3 className="font-semibold flex items-center gap-2">
        <Icon name="ShieldCheck" size={18} />
        Проверка оплаты
      </h3>
      <p className="text-sm text-muted-foreground">
        Спросим подключённый эквайринг (Т-Банк, Альфа-Банк), оплачен ли заказ с номером этого счёта. Чек и транзакцию
        здесь не создаём — это делает сценарий «Расхождение».
      </p>
      <Button onClick={check} disabled={loading} variant="outline" className="gap-2">
        <Icon name={loading ? 'Loader2' : 'RefreshCw'} size={16} className={loading ? 'animate-spin' : ''} />
        {loading ? 'Спрашиваем банк…' : 'Проверить оплату сейчас'}
      </Button>
      {result && view && (
        <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${view.className}`}>
          <Icon name={view.icon} size={18} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="font-medium">{view.title}</p>
            <p className="break-words text-foreground/80">{result.message}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default PendingInvoiceCheck;
