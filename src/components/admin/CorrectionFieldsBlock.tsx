import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import ReceiptFieldSelect from './ReceiptFieldSelect';
import VariableChips, { SEQ_VARIABLE } from '@/components/automation/VariableChips';
import { ActionTemplateForm, DATE_SOURCE_OPTIONS } from './actionTemplatesConfig';

interface CorrectionFieldsBlockProps {
  form: ActionTemplateForm;
  onChange: (form: ActionTemplateForm) => void;
}

const CorrectionFieldsBlock = ({ form, onChange }: CorrectionFieldsBlockProps) => {
  const v5 = form.protocol_version === 'v5';
  const set = (field: keyof ActionTemplateForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...form, [field]: e.target.value });

  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
      <div>
        <div className="text-sm font-semibold">Основание коррекции</div>
        <div className="text-xs text-muted-foreground">
          Самостоятельная коррекция · {form.protocol_version}. Пустые поля клиент заполнит в своём сценарии
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ReceiptFieldSelect
          label={v5 ? 'Дата корректируемого расчёта' : 'Дата документа основания'}
          value={form.correction_date_source}
          options={DATE_SOURCE_OPTIONS}
          onChange={(v) => onChange({ ...form, correction_date_source: v })}
        />
        {form.correction_date_source === 'fixed' && (
          <div className="space-y-2">
            <Label>Дата</Label>
            <Input type="date" value={form.correction_base_date} onChange={set('correction_base_date')} />
          </div>
        )}
      </div>

      <div className="space-y-2">
        <Label>Номер документа основания{v5 ? ' (необязательно)' : ''}</Label>
        <Input value={form.correction_base_number} maxLength={32} placeholder="Заполнит клиент" onChange={set('correction_base_number')} />
        <VariableChips
          variables={[SEQ_VARIABLE]}
          onPick={(token) => {
            if (!form.correction_base_number.includes(token))
              onChange({ ...form, correction_base_number: `${form.correction_base_number}${token}`.slice(0, 32) });
          }}
        />
        {!v5 && <p className="text-xs text-muted-foreground">Обязателен в v4 — если пусто, клиент укажет в сценарии</p>}
      </div>

      {!v5 && (
        <div className="space-y-2">
          <Label>Описание коррекции</Label>
          <Input value={form.correction_base_name} maxLength={255} placeholder="Заполнит клиент" onChange={set('correction_base_name')} />
          <p className="text-xs text-muted-foreground">Причина коррекции — попадёт в чек. Если пусто, клиент укажет в сценарии</p>
        </div>
      )}

      <p className="text-xs text-muted-foreground">Место расчётов берётся из адреса магазина в Екомкассе</p>
    </div>
  );
};

export default CorrectionFieldsBlock;
