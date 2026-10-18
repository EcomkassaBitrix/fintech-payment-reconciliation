interface Props {
  variables: { token: string; hint?: string }[];
  active?: string;
  onPick: (token: string) => void;
}

const VariableChips = ({ variables, active, onPick }: Props) => (
  <div className="flex flex-wrap items-center gap-1.5">
    <span className="text-xs text-muted-foreground">Переменные:</span>
    {variables.map((v) => (
      <button
        key={v.token}
        type="button"
        title={v.hint}
        onClick={() => onPick(v.token)}
        className={`rounded-md border px-2 py-0.5 font-mono text-xs transition-colors ${
          active === v.token
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-border bg-muted text-foreground hover:border-primary/50'
        }`}
      >
        {v.token}
      </button>
    ))}
  </div>
);

export const SEQ_VARIABLE = { token: '{порядковый номер}', hint: 'Номер чека коррекции в компании по порядку: 1, 2, 3…' };

export const DATE_VARIABLES = [
  { token: '{сегодня}', hint: 'Дата отправки чека' },
  { token: '{вчера}', hint: 'День до отправки чека' },
  { token: '{дата платежа}', hint: 'Дата оплаты, по которой пробивается чек' }
];

export default VariableChips;
