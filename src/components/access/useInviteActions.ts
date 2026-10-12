import { useState, Dispatch, SetStateAction } from 'react';
import { useToast } from '@/hooks/use-toast';
import { GOALS, reachGoal } from '@/lib/metrika';
import { SITE_URL } from '@/config/site';
import functionUrls from '../../../backend/func2url.json';
import {
  Invite,
  Role,
  NewUserForm,
  channelProviderMap,
  channelLabelMap
} from '@/components/access/accessTypes';

interface UseInviteActionsParams {
  companyId: number | undefined;
  companyName: string | undefined;
  userId: number | undefined;
  roles: Role[];
  invites: Invite[];
  setInvites: Dispatch<SetStateAction<Invite[]>>;
  loadData: () => Promise<void>;
}

const useInviteActions = ({ companyId, companyName, userId, roles, invites, setInvites, loadData }: UseInviteActionsParams) => {
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [inviteLink, setInviteLink] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const [newUser, setNewUser] = useState<NewUserForm>({
    phone: '+7',
    fullName: '',
    email: '',
    role: '',
    messenger: 'telegram' as 'telegram' | 'whatsapp' | 'max' | 'email'
  });

  const handleInviteUser = async () => {
    if (!companyId || !newUser.phone || !newUser.fullName || !newUser.role) return;

    setIsLoading(true);

    try {
      const inviteRes = await fetch(functionUrls['company-users-invite'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_id: companyId,
          phone: newUser.phone,
          full_name: newUser.fullName,
          email: newUser.email || null,
          role_slug: newUser.role,
          channel: newUser.messenger,
          invited_by: userId
        })
      });

      const inviteData = await inviteRes.json();

      if (!inviteRes.ok || !inviteData.success) {
        toast({
          title: inviteData.error_code === 'limit_reached' ? 'Лимит тарифа исчерпан' : 'Ошибка приглашения',
          description: inviteData.error || 'Не удалось создать приглашение',
          variant: 'destructive'
        });
        return;
      }
      reachGoal(GOALS.userInvited, { role: newUser.role });

      const link = `${SITE_URL}/invite/${inviteData.token}`;
      setInviteLink(link);

      const roleName = roles.find(r => r.slug === newUser.role)?.name;
      const messageText = `Привет, ${newUser.fullName}! Вас пригласили в команду «${companyName}» на портале Сверка.\n\nПерейдите по ссылке, чтобы принять приглашение: ${link}\n\nРоль: ${roleName}\nСсылка действует 7 дней.`;

      const recipient = newUser.messenger === 'email'
        ? newUser.email
        : newUser.phone.replace(/\D/g, '');

      const sendRes = await fetch(functionUrls['send-message'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: channelProviderMap[newUser.messenger],
          recipient,
          message: messageText
        })
      });

      const sendData = await sendRes.json();

      if (sendRes.ok && sendData.success) {
        toast({
          title: 'Приглашение отправлено',
          description: `${newUser.fullName} получит ссылку через ${channelLabelMap[newUser.messenger]}`
        });
      } else {
        toast({
          title: 'Приглашение создано, но не доставлено',
          description: 'Скопируйте ссылку и отправьте её вручную',
          variant: 'destructive'
        });
      }

      loadData();
    } catch (error) {
      toast({
        title: 'Ошибка',
        description: 'Проблема с подключением к серверу',
        variant: 'destructive'
      });
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: 'Ссылка скопирована' });
  };

  const [resendingId, setResendingId] = useState<number | null>(null);

  const resendInvite = async (invite: Invite, channel: string = invite.channel) => {
    if (!companyId) return;
    if (channel === 'email' && !invite.email) {
      toast({ title: 'Нет почты', description: 'У приглашения не указан email — выберите мессенджер', variant: 'destructive' });
      return;
    }
    setResendingId(invite.id);

    try {
      const inviteRes = await fetch(functionUrls['company-users-invite'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_id: companyId,
          phone: invite.phone,
          full_name: invite.full_name,
          email: invite.email,
          role_slug: invite.role_slug,
          channel,
          invited_by: userId
        })
      });

      const inviteData = await inviteRes.json();

      if (!inviteRes.ok || !inviteData.success) {
        toast({
          title: 'Ошибка приглашения',
          description: inviteData.error || 'Не удалось создать новую ссылку',
          variant: 'destructive'
        });
        return;
      }

      const link = `${SITE_URL}/invite/${inviteData.token}`;
      const messageText = `Привет, ${invite.full_name || ''}! Вас пригласили в команду «${companyName}» на портале Сверка.\n\nПерейдите по ссылке, чтобы принять приглашение: ${link}\n\nРоль: ${invite.role_name}\nСсылка действует 7 дней.`;

      const recipient = channel === 'email' ? invite.email || '' : invite.phone;

      const sendRes = await fetch(functionUrls['send-message'], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: channelProviderMap[channel] || 'ek_tg',
          recipient,
          message: messageText
        })
      });

      const sendData = await sendRes.json();

      if (sendRes.ok && sendData.success) {
        toast({
          title: 'Приглашение отправлено повторно',
          description: `Новая ссылка ушла через ${channelLabelMap[channel] || 'Telegram'}`
        });
      } else {
        toast({
          title: `Не удалось отправить через ${channelLabelMap[channel] || 'мессенджер'}`,
          description: 'Выберите другой способ в списке «Отправлено через»',
          variant: 'destructive'
        });
      }

      loadData();
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    } finally {
      setResendingId(null);
    }
  };

  const cancelInvite = async (inviteId: number) => {
    if (!companyId) return;
    try {
      const res = await fetch(functionUrls['company-users-update'], {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, invite_id: inviteId })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setInvites(invites.filter(i => i.id !== inviteId));
        toast({ title: 'Приглашение отменено' });
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  return {
    showInviteDialog,
    setShowInviteDialog,
    inviteLink,
    isLoading,
    newUser,
    setNewUser,
    handleInviteUser,
    copyToClipboard,
    resendingId,
    resendInvite,
    cancelInvite
  };
};

export default useInviteActions;
