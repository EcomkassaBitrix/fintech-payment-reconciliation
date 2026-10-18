import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import Icon from '@/components/ui/icon';
import {
  ActionTemplateRow,
  OPERATION_OPTIONS,
  PAYMENT_OBJECT_OPTIONS,
  PAYMENT_TYPE_OPTIONS,
  RECEIPT_TYPE_OPTIONS,
  NO_PAYMENT,
  labelOf
} from './actionTemplatesConfig';

interface Props {
  t: ActionTemplateRow;
  onEdit: (t: ActionTemplateRow) => void;
  onCopy: (t: ActionTemplateRow) => void;
  onDelete: (t: ActionTemplateRow) => void;
}

const ActionTemplateCard = ({ t, onEdit, onCopy, onDelete }: Props) => (
  <Card
    onClick={() => onEdit(t)}
    className={`cursor-pointer transition-colors hover:border-primary/40 ${t.is_active ? '' : 'opacity-60'}`}
  >
    <CardContent className="space-y-3 p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold">{t.name}</div>
          <div className="font-mono text-xs text-muted-foreground">{t.code}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge
            variant="outline"
            className={t.is_active ? 'border-success/30 bg-success/15 text-success' : 'text-muted-foreground'}
          >
            {t.is_active ? 'Доступен' : 'Выключен'}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-primary"
            title="Копировать"
            onClick={(e) => {
              e.stopPropagation();
              onCopy(t);
            }}
          >
            <Icon name="Copy" size={16} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            disabled={t.scenarios_count > 0}
            title={t.scenarios_count > 0 ? 'Используется в сценариях — можно только выключить' : 'Удалить'}
            onClick={(e) => {
              e.stopPropagation();
              onDelete(t);
            }}
          >
            <Icon name="Trash2" size={16} />
          </Button>
        </div>
      </div>
      {t.description && <p className="line-clamp-2 text-sm text-muted-foreground">{t.description}</p>}
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-md bg-muted px-2 py-1">
          {t.provider_name || 'Касса не выбрана'} · {t.protocol_version}
        </span>
        <span className="rounded-md bg-muted px-2 py-1">
          {labelOf(RECEIPT_TYPE_OPTIONS, t.receipt_type)} · {labelOf(OPERATION_OPTIONS, t.operation)}
        </span>
        <span className="rounded-md bg-muted px-2 py-1">{labelOf(PAYMENT_OBJECT_OPTIONS, t.payment_object)}</span>
        <span className="rounded-md bg-muted px-2 py-1">
          Оплата: {labelOf(PAYMENT_TYPE_OPTIONS, t.payment_type === null ? NO_PAYMENT : String(t.payment_type))}
        </span>
        {t.auto_deliver && (
          <span className="rounded-md bg-primary/15 px-2 py-1 text-primary">Сразу доставка</span>
        )}
        <span className="rounded-md bg-muted px-2 py-1">Сценариев: {t.scenarios_count}</span>
      </div>
    </CardContent>
  </Card>
);

export default ActionTemplateCard;
