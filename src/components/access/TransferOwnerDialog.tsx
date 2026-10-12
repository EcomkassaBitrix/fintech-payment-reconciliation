import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Icon from '@/components/ui/icon';

interface Candidate {
  id: number;
  fullName: string;
  phone: string;
}

interface TransferOwnerDialogProps {
  candidates: Candidate[];
  onTransfer: (userId: number) => Promise<boolean>;
}

const TransferOwnerDialog = ({ candidates, onTransfer }: TransferOwnerDialogProps) => {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const target = candidates.find((c) => String(c.id) === selected);

  const submit = async () => {
    if (!target) return;
    setBusy(true);
    const ok = await onTransfer(target.id);
    setBusy(false);
    if (ok) {
      setOpen(false);
      setSelected('');
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Icon name="ArrowRightLeft" size={14} />
          Передать роль
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Передать роль владельца</DialogTitle>
          <DialogDescription>
            Новый владелец получит полный доступ к компании, подписке и сотрудникам. Вы станете админом компании.
          </DialogDescription>
        </DialogHeader>

        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Нет активных сотрудников. Сначала пригласите пользователя и дождитесь, пока он примет приглашение.
          </p>
        ) : (
          <Select value={selected} onValueChange={setSelected}>
            <SelectTrigger>
              <SelectValue placeholder="Выберите пользователя" />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.fullName || 'Без имени'} · {c.phone}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {target && (
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/10 p-3">
            <Icon name="AlertTriangle" size={16} className="text-warning shrink-0 mt-0.5" />
            <p className="text-sm text-foreground">
              Вернуть роль сможет только новый владелец — {target.fullName || target.phone}.
            </p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Отмена</Button>
          <Button onClick={submit} disabled={!target || busy}>
            {busy && <Icon name="Loader2" size={14} className="animate-spin mr-2" />}
            Передать
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default TransferOwnerDialog;
