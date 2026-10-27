import { useEffect, useState } from 'react';
import { useParams } from "@/lib/router-compat";
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { formatDateTime, DEFAULT_TIMEZONE } from '@/lib/formatDate';
import functionUrls from '../../backend/func2url.json';

interface WebhookLog {
  id: number;
  webhook_payment_id: number | null;
  forward_url: string;
  status_code: number | null;
  error_message: string | null;
  response_time_ms: number;
  created_at: string;
  payment_id: string | null;
  order_id: string | null;
  amount: number | null;
  payment_status: string | null;
}

export default function WebhookLogsPage() {
  const { integrationId } = useParams();
  const { currentCompany } = useAuth();
  const companyId = currentCompany?.id;
  const timezone = currentCompany?.timezone || DEFAULT_TIMEZONE;
  const [logs, setLogs] = useState<WebhookLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!companyId) return;
    loadLogs();
    const interval = setInterval(loadLogs, 5000);
    return () => clearInterval(interval);
  }, [integrationId, companyId]);

  const loadLogs = async () => {
    try {
      const url = `${functionUrls['webhook-logs']}?company_id=${companyId}&integration_id=${integrationId}&limit=100`;
      const res = await fetch(url);
      const data = await res.json();
      setLogs(data.logs || []);
    } catch (error) {
      console.error('Failed to load logs:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (statusCode: number | null) => {
    if (!statusCode) return <Badge variant="secondary">Не отправлено</Badge>;
    if (statusCode >= 200 && statusCode < 300) return <Badge variant="default">Успешно ({statusCode})</Badge>;
    if (statusCode >= 400) return <Badge variant="destructive">Ошибка ({statusCode})</Badge>;
    return <Badge variant="secondary">{statusCode}</Badge>;
  };

  if (loading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-muted-foreground">Загрузка...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Логи переадресации вебхуков</h1>
        <p className="text-muted-foreground">
          История отправки вебхуков на внешний URL
        </p>
      </div>

      {logs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Icon name="FileText" size={48} className="mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">Пока нет логов переадресации</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {logs.map((log) => (
            <Card key={log.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <CardTitle className="text-base mb-2">
                      {log.payment_id ? `Платёж ${log.payment_id}` : 'Вебхук'}
                    </CardTitle>
                    <div className="space-y-1 text-sm">
                      <div className="flex items-center gap-2">
                        <Icon name="Globe" size={14} className="text-muted-foreground" />
                        <span className="font-mono text-xs">{log.forward_url}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Icon name="Clock" size={14} className="text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {formatDateTime(log.created_at, timezone)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    {getStatusBadge(log.status_code)}
                    {log.response_time_ms > 0 && (
                      <span className="text-xs text-muted-foreground">
                        {log.response_time_ms}ms
                      </span>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  {log.order_id && (
                    <div>
                      <span className="text-muted-foreground">Order ID:</span>
                      <span className="ml-2 font-medium">{log.order_id}</span>
                    </div>
                  )}
                  {log.amount !== null && (
                    <div>
                      <span className="text-muted-foreground">Сумма:</span>
                      <span className="ml-2 font-medium">{log.amount.toFixed(2)} ₽</span>
                    </div>
                  )}
                  {log.payment_status && (
                    <div>
                      <span className="text-muted-foreground">Статус:</span>
                      <span className="ml-2 font-medium">{log.payment_status}</span>
                    </div>
                  )}
                </div>
                {log.error_message && (
                  <div className="mt-4 p-3 bg-destructive/10 rounded-md">
                    <div className="flex items-start gap-2">
                      <Icon name="AlertCircle" size={16} className="text-destructive mt-0.5" />
                      <div>
                        <div className="font-medium text-sm text-destructive mb-1">Ошибка</div>
                        <div className="text-xs text-muted-foreground">{log.error_message}</div>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}