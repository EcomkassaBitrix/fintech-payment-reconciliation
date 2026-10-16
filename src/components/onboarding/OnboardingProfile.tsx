import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { isValidEmail } from '@/lib/formatters';
import functionUrls from '../../../backend/func2url.json';

const OnboardingProfile = ({ onSaved }: { onSaved: () => void }) => {
  const { user, updateUser } = useAuth();
  const { toast } = useToast();
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [isSaving, setIsSaving] = useState(false);

  const emailOk = !!email.trim() && isValidEmail(email.trim());
  const canSave = !!fullName.trim() && emailOk && !isSaving;

  const save = async () => {
    if (!user || !canSave) return;
    setIsSaving(true);
    try {
      const res = await fetch(functionUrls['profile-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.user_id, full_name: fullName.trim(), email: email.trim() })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        updateUser({ full_name: data.user.full_name, email: data.user.email });
        toast({ title: 'Профиль сохранён' });
        onSaved();
      } else {
        toast({ title: 'Не удалось сохранить', description: data.error || 'Попробуйте ещё раз', variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', description: 'Проверьте интернет-соединение', variant: 'destructive' });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Имя</Label>
        <Input placeholder="Иван Иванов" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </div>
      <div className="space-y-2">
        <Label>Email</Label>
        <Input type="email" placeholder="ivan@company.ru" value={email} onChange={(e) => setEmail(e.target.value)} />
        <p className={`text-xs ${email && !emailOk ? 'text-destructive' : 'text-muted-foreground'}`}>
          {email && !emailOk ? 'Некорректный формат email' : 'Сюда можно получать уведомления и документы'}
        </p>
      </div>
      <Button className="gap-2" onClick={save} disabled={!canSave}>
        <Icon name={isSaving ? 'Loader2' : 'Check'} size={16} className={isSaving ? 'animate-spin' : ''} />
        Сохранить и продолжить
      </Button>
    </div>
  );
};

export default OnboardingProfile;
