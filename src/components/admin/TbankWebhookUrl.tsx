import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import Icon from '@/components/ui/icon';
import functionUrls from '../../../backend/func2url.json';

const WEBHOOK_URL = `${(functionUrls as Record<string, string>)['subscription-checkout']}?tbank_notify=1`;

const TbankWebhookUrl = () => {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(WEBHOOK_URL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-2 rounded-lg border border-border p-4">
      <p className="text-sm font-medium text-foreground">Адрес для уведомлений об оплате</p>
      <div className="flex gap-2">
        <Input value={WEBHOOK_URL} readOnly className="font-mono text-xs" onFocus={(e) => e.target.select()} />
        <Button variant="outline" onClick={copy} className="shrink-0">
          <Icon name={copied ? 'Check' : 'Copy'} size={14} className="mr-2" />
          {copied ? 'Скопировано' : 'Скопировать'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Сервис сам передаёт этот адрес в каждом платеже, указывать его в терминале не обязательно. Если хотите — Т‑Бизнес →
        Интернет‑эквайринг → Магазины → Терминалы → Настройки → Уведомления → «По протоколу HTTP». Не меняйте адрес, если
        этот терминал подключён как интеграция у какой‑то компании в Сверке.
      </p>
    </div>
  );
};

export default TbankWebhookUrl;
