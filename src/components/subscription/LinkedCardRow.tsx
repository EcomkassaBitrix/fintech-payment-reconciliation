import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from '@/components/ui/alert-dialog';
import Icon from '@/components/ui/icon';

const PROVIDER_ICONS: Record<string, string> = {
  tbank: '/payments/tbank-shield.svg'
};

interface LinkedCardRowProps {
  pan: string;
  provider?: string;
  canManage: boolean;
  busy: boolean;
  onRemove: () => void;
}

const lastDigits = (pan: string) => pan.replace(/\D/g, '').slice(-4);

const LinkedCardRow = ({ pan, provider = 'tbank', canManage, busy, onRemove }: LinkedCardRowProps) => {
  const [confirm, setConfirm] = useState(false);
  const icon = PROVIDER_ICONS[provider];

  return (
    <>
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-3 text-muted-foreground">
          {icon ? (
            <img src={icon} alt="" className="h-6 w-6 shrink-0" />
          ) : (
            <Icon name="CreditCard" size={22} className="shrink-0" />
          )}
          <span>
            Привязана карта <span className="tracking-widest">•••</span>
            {lastDigits(pan)}
          </span>
        </div>
        {canManage && (
          <Button variant="outline" size="sm" disabled={busy} onClick={() => setConfirm(true)} className="gap-2">
            {busy ? <Icon name="Loader2" size={14} className="animate-spin" /> : <Icon name="Unlink" size={14} />}
            Отвязать карту
          </Button>
        )}
      </div>

      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Отвязать карту •••{lastDigits(pan)}?</AlertDialogTitle>
            <AlertDialogDescription>
              Карта будет удалена, автопродление выключится. Подписка продолжит действовать до конца оплаченного срока,
              дальше её можно будет оплатить вручную.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={onRemove}
            >
              Отвязать
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default LinkedCardRow;
