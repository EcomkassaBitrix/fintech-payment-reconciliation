import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CorrectionSettings } from './automationConfig';
import VariableChips, { DATE_VARIABLES, SEQ_VARIABLE } from './VariableChips';

const isToken = (v?: string) => !!v && v.startsWith('{');

interface ScenarioCorrectionFieldsProps {
  cs: CorrectionSettings;
  setCs: (patch: CorrectionSettings) => void;
  isV5: boolean;
  dateLabel: string;
  askNumber: boolean;
  askName: boolean;
  askDate: boolean;
  correctionMissing: (string | false)[];
}

const ScenarioCorrectionFields = ({ cs, setCs, isV5, dateLabel, askNumber, askName, askDate, correctionMissing }: ScenarioCorrectionFieldsProps) => (
  <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
    <p className="text-xs text-muted-foreground">
      Самостоятельная коррекция · протокол {isV5 ? 'v5 (ФФД 1.2)' : 'v4 (ФФД 1.05)'}. Дата основания — {dateLabel}. Место расчётов — адрес магазина в Екомкассе.
    </p>
    {!askNumber && !askName && !askDate && (
      <p className="text-xs text-muted-foreground">Все поля коррекции заданы в шаблоне — заполнять ничего не нужно</p>
    )}
    {askDate && (
      <div className="space-y-1">
        <Label>{isV5 ? 'Дата корректируемого расчёта' : 'Дата документа-основания'}</Label>
        {isToken(cs.correction_base_date) ? (
          <div className="flex h-10 items-center justify-between rounded-md border border-input bg-background px-3 text-sm">
            <span className="font-mono">{cs.correction_base_date}</span>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setCs({ correction_base_date: '' })}
            >
              Выбрать дату
            </button>
          </div>
        ) : (
          <Input
            type="date"
            value={cs.correction_base_date || ''}
            onChange={(e) => setCs({ correction_base_date: e.target.value })}
          />
        )}
        <VariableChips
          variables={DATE_VARIABLES}
          active={cs.correction_base_date}
          onPick={(token) => setCs({ correction_base_date: token })}
        />
      </div>
    )}
    {askNumber && (
      <div className="space-y-1">
        <Label>Номер документа-основания{isV5 ? ' (необязательно)' : ''}</Label>
        <Input
          placeholder="Например, 1 или номер акта"
          maxLength={32}
          value={cs.correction_base_number || ''}
          onChange={(e) => setCs({ correction_base_number: e.target.value })}
        />
        <VariableChips
          variables={[SEQ_VARIABLE]}
          onPick={(token) => {
            const cur = cs.correction_base_number || '';
            if (!cur.includes(token)) setCs({ correction_base_number: `${cur}${token}`.slice(0, 32) });
          }}
        />
      </div>
    )}
    {askName && (
      <div className="space-y-1">
        <Label>Описание коррекции</Label>
        <Input
          placeholder="Не пробит чек при оплате"
          value={cs.correction_base_name || ''}
          onChange={(e) => setCs({ correction_base_name: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">Причина коррекции — попадёт в чек</p>
      </div>
    )}
    {correctionMissing.length > 0 && (
      <p className="text-xs text-destructive">Заполните: {correctionMissing.join(', ')}</p>
    )}
  </div>
);

export default ScenarioCorrectionFields;
