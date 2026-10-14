import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import Icon from '@/components/ui/icon';

export interface TbankConfig {
  receipt_enabled?: boolean;
  taxation?: string;
  vat?: string;
  payment_method?: string;
  payment_object?: string;
  ffd?: string;
  measurement_unit?: string;
}

interface TbankTerminalFormProps {
  terminalKey: string | null;
  config: TbankConfig;
  busy: boolean;
  onSave: (body: Record<string, unknown>) => void;
  onCancel?: () => void;
}

const TAXATIONS = [
  ['usn_income', 'УСН доходы'],
  ['usn_income_outcome', 'УСН доходы минус расходы'],
  ['osn', 'ОСН'],
  ['patent', 'Патент'],
  ['esn', 'ЕСХН']
];

const VATS = [
  ['none', 'Без НДС'],
  ['vat0', 'НДС 0%'],
  ['vat5', 'НДС 5%'],
  ['vat7', 'НДС 7%'],
  ['vat10', 'НДС 10%'],
  ['vat20', 'НДС 20%'],
  ['vat22', 'НДС 22%']
];

const PAYMENT_METHODS = [
  ['full_payment', 'Полный расчёт'],
  ['full_prepayment', 'Предоплата 100%'],
  ['prepayment', 'Предоплата'],
  ['advance', 'Аванс']
];

const PAYMENT_OBJECTS = [
  ['service', 'Услуга'],
  ['intellectual_activity', 'Результаты интеллектуальной деятельности'],
  ['job', 'Работа'],
  ['commodity', 'Товар'],
  ['another', 'Иной предмет расчёта']
];

const selectClass = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground';

const TbankTerminalForm = ({ terminalKey, config, busy, onSave, onCancel }: TbankTerminalFormProps) => {
  const [key, setKey] = useState(terminalKey || '');
  const [password, setPassword] = useState('');
  const [receipt, setReceipt] = useState(Boolean(config.receipt_enabled));
  const [taxation, setTaxation] = useState(config.taxation || 'usn_income');
  const [vat, setVat] = useState(config.vat || 'none');
  const [paymentMethod, setPaymentMethod] = useState(config.payment_method || 'full_payment');
  const [paymentObject, setPaymentObject] = useState(config.payment_object || 'service');
  const [ffd, setFfd] = useState(config.ffd || '1.2');
  const keepPassword = Boolean(terminalKey) && key === terminalKey;

  return (
    <div className="space-y-4 rounded-lg border border-border p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>TerminalKey</Label>
          <Input value={key} onChange={(e) => setKey(e.target.value.trim())} placeholder="1700000000000" />
        </div>
        <div className="space-y-1.5">
          <Label>Пароль терминала</Label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={keepPassword ? 'Оставьте пустым, чтобы не менять' : 'Из личного кабинета Т‑Бизнеса'}
          />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Т‑Бизнес → Интернет‑эквайринг → Магазины → Терминалы. В терминале должны быть включены рекуррентные платежи —
        их подключает менеджер Т‑Банка. Тестовый терминал (с DEMO в конце) можно использовать для проверки.
      </p>

      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Передавать чек в Т‑Банк</p>
          <p className="text-xs text-muted-foreground">Если к терминалу подключена онлайн‑касса Т‑Банка</p>
        </div>
        <Switch checked={receipt} onCheckedChange={setReceipt} />
      </div>
      {receipt && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Система налогообложения</Label>
            <select className={selectClass} value={taxation} onChange={(e) => setTaxation(e.target.value)}>
              {TAXATIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>НДС</Label>
            <select className={selectClass} value={vat} onChange={(e) => setVat(e.target.value)}>
              {VATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Признак способа расчёта</Label>
            <select className={selectClass} value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
              {PAYMENT_METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Признак предмета расчёта</Label>
            <select className={selectClass} value={paymentObject} onChange={(e) => setPaymentObject(e.target.value)}>
              {PAYMENT_OBJECTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Версия ФФД кассы</Label>
            <select className={selectClass} value={ffd} onChange={(e) => setFfd(e.target.value)}>
              <option value="1.2">1.2 (единица измерения «шт»)</option>
              <option value="1.05">1.05</option>
            </select>
          </div>
          <p className="text-xs text-muted-foreground sm:col-span-2">
            В чеке одна позиция: «Подписка на сервис «Сверка», тариф «…», 1 мес.» на сумму оплаты.
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            Отмена
          </Button>
        )}
        <Button
          disabled={busy || !key || (!password && !keepPassword)}
          onClick={() =>
            onSave({
              action: 'save_terminal', terminal_key: key, terminal_password: password, receipt_enabled: receipt, taxation, vat,
              payment_method: paymentMethod, payment_object: paymentObject, ffd, measurement_unit: 'шт'
            })
          }
        >
          {busy ? <Icon name="Loader2" size={14} className="animate-spin mr-2" /> : <Icon name="Check" size={14} className="mr-2" />}
          Проверить и сохранить
        </Button>
      </div>
    </div>
  );
};

export default TbankTerminalForm;
