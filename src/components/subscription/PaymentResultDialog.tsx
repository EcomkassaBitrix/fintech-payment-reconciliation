import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';

export type PaymentResultState =
  | { kind: 'checking' }
  | { kind: 'success'; tariffName?: string; amount?: number; until?: string; cardSaved?: boolean }
  | { kind: 'fail'; reason?: string | null }
  | { kind: 'pending' };

interface PaymentResultDialogProps {
  state: PaymentResultState | null;
  onClose: () => void;
  onRetry?: () => void;
}

const money = (n?: number) => (n ? `${new Intl.NumberFormat('ru-RU').format(n)} ₽` : '');

const PaymentResultDialog = ({ state, onClose, onRetry }: PaymentResultDialogProps) => (
  <Dialog open={Boolean(state)} onOpenChange={(o) => !o && state?.kind !== 'checking' && onClose()}>
    <DialogContent className="max-w-sm text-center sm:max-w-md">
      {state?.kind === 'checking' && (
        <div className="flex flex-col items-center gap-4 py-6">
          <Icon name="Loader2" size={48} className="animate-spin text-primary" />
          <DialogTitle className="text-xl">Проверяем оплату</DialogTitle>
          <DialogDescription>Ждём подтверждение от банка, обычно это несколько секунд</DialogDescription>
        </div>
      )}

      {state?.kind === 'success' && (
        <div className="flex flex-col items-center gap-4 py-4">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-success/15">
            <Icon name="CircleCheck" size={48} className="text-success" />
          </div>
          <DialogTitle className="text-2xl">Оплата прошла</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-1 text-base">
              {state.tariffName && (
                <p className="text-foreground">
                  Тариф «{state.tariffName}»{state.amount ? ` · ${money(state.amount)}` : ''}
                </p>
              )}
              {state.until && <p>Подписка действует до {state.until}</p>}
              {state.cardSaved && <p className="text-sm">Карта привязана — подписка будет продлеваться автоматически</p>}
              <p className="text-sm">Чек отправлен на вашу почту или телефон</p>
            </div>
          </DialogDescription>
          <Button className="mt-2 w-full" onClick={onClose}>
            Отлично
          </Button>
        </div>
      )}

      {state?.kind === 'fail' && (
        <div className="flex flex-col items-center gap-4 py-4">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-destructive/15">
            <Icon name="CircleX" size={48} className="text-destructive" />
          </div>
          <DialogTitle className="text-2xl">Оплата не прошла</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-1 text-base">
              <p className="text-foreground">{state.reason || 'Банк отклонил оплату'}</p>
              <p className="text-sm">Деньги не списаны. Попробуйте ещё раз или оплатите другой картой.</p>
            </div>
          </DialogDescription>
          <div className="mt-2 flex w-full flex-col gap-2 sm:flex-row">
            {onRetry && (
              <Button className="flex-1" onClick={onRetry}>
                <Icon name="RotateCcw" size={16} className="mr-2" />
                Попробовать снова
              </Button>
            )}
            <Button variant="outline" className="flex-1" onClick={onClose}>
              Закрыть
            </Button>
          </div>
        </div>
      )}

      {state?.kind === 'pending' && (
        <div className="flex flex-col items-center gap-4 py-4">
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-warning/15">
            <Icon name="Clock" size={48} className="text-warning" />
          </div>
          <DialogTitle className="text-2xl">Оплата обрабатывается</DialogTitle>
          <DialogDescription className="text-base">
            Банк ещё не подтвердил платёж. Если деньги списались, тариф включится автоматически в течение нескольких минут.
          </DialogDescription>
          <Button variant="outline" className="mt-2 w-full" onClick={onClose}>
            Понятно
          </Button>
        </div>
      )}
    </DialogContent>
  </Dialog>
);

export default PaymentResultDialog;
