import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import { GOALS, reachGoal } from '@/lib/metrika';
import { SITE_URL } from '@/config/site';
import functionUrls from '../../backend/func2url.json';
import RoleCard from '@/components/access/RoleCard';
import InviteUserDialog from '@/components/access/InviteUserDialog';
import UsersTable from '@/components/access/UsersTable';
import PendingInvitesTable from '@/components/access/PendingInvitesTable';
import Icon from '@/components/ui/icon';

interface CompanyUser {
  id: number;
  full_name: string | null;
  email: string | null;
  phone: string;
  role_slug: string;
  role_name: string;
  role_color: string;
  status: 'active' | 'pending' | 'blocked' | 'removed';
  invited_at: string | null;
  joined_at: string | null;
}

interface Invite {
  id: number;
  phone: string;
  email: string | null;
  full_name: string | null;
  channel: string;
  role_slug: string;
  role_name: string;
  role_color: string;
  created_at: string | null;
  expires_at: string | null;
}

interface Role {
  id: number;
  slug: string;
  name: string;
  description: string;
  color: string;
  modules: string[];
  permissions: string[];
  is_system: boolean;
}

const modules = [
  { id: 'reconciliation', name: 'Сверка', icon: 'GitCompare' },
  { id: 'events', name: 'События', icon: 'Radio' },
  { id: 'transactions', name: 'Транзакции', icon: 'ArrowLeftRight' },
  { id: 'automation', name: 'Автоматизация', icon: 'Workflow' },
  { id: 'integrations', name: 'Интеграции', icon: 'Plug' },
  { id: 'access', name: 'Управление доступом', icon: 'Users' },
  { id: 'settings', name: 'Настройки', icon: 'Settings' }
];

const channelProviderMap: Record<string, string> = {
  whatsapp: 'ek_wa',
  telegram: 'ek_tg',
  max: 'ek_max',
  email: 'ek_email'
};

const channelLabelMap: Record<string, string> = {
  whatsapp: 'WhatsApp',
  telegram: 'Telegram',
  max: 'Max',
  email: 'почту'
};

const AccessManagement = () => {
  const { user, currentCompany, refreshCompanies } = useAuth();
  const companyId = currentCompany?.id;
  const maxUsers = currentCompany?.max_users;

  const [users, setUsers] = useState<CompanyUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [isPageLoading, setIsPageLoading] = useState(true);
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [inviteLink, setInviteLink] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const [newUser, setNewUser] = useState({
    phone: '+7',
    fullName: '',
    email: '',
    role: '',
    messenger: 'telegram' as 'telegram' | 'whatsapp' | 'max' | 'email'
  });

  const loadData = async () => {
    if (!companyId) return;
    setIsPageLoading(true);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        fetch(`${functionUrls['company-users-list']}?company_id=${companyId}`),
        fetch(`${functionUrls['roles-list']}?scope=company`)
      ]);

      const usersData = await usersRes.json();
      const rolesData = await rolesRes.json();

      if (usersRes.ok) {
        setUsers(usersData.users || []);
        setInvites(usersData.invites || []);
      }
      if (rolesRes.ok) setRoles(rolesData.roles || []);
    } catch (error) {
      toast({
        title: 'Ошибка загрузки',
        description: 'Не удалось загрузить пользователей и роли',
        variant: 'destructive'
      });
    } finally {
      setIsPageLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [companyId]);

  const activeAndPendingCount = users.filter(u => u.status !== 'removed').length + invites.length;
  const isLimitReached = typeof maxUsers === 'number' && activeAndPendingCount >= maxUsers;

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
          invited_by: user?.user_id
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
      const messageText = `Привет, ${newUser.fullName}! Вас пригласили в команду «${currentCompany?.name}» на портале Сверка.\n\nПерейдите по ссылке, чтобы принять приглашение: ${link}\n\nРоль: ${roleName}\nСсылка действует 7 дней.`;

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
          invited_by: user?.user_id
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
      const messageText = `Привет, ${invite.full_name || ''}! Вас пригласили в команду «${currentCompany?.name}» на портале Сверка.\n\nПерейдите по ссылке, чтобы принять приглашение: ${link}\n\nРоль: ${invite.role_name}\nСсылка действует 7 дней.`;

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

  const toggleUserStatus = async (userId: number) => {
    if (!companyId) return;
    const targetUser = users.find(u => u.id === userId);
    if (!targetUser) return;

    const newStatus = targetUser.status === 'active' ? 'blocked' : 'active';

    try {
      const res = await fetch(functionUrls['company-users-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, user_id: userId, status: newStatus })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setUsers(users.map(u => u.id === userId ? { ...u, status: newStatus } : u));
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  const deleteUser = async (userId: number) => {
    if (!companyId) return;

    try {
      const res = await fetch(functionUrls['company-users-update'], {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_id: companyId, user_id: userId })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        setUsers(users.filter(u => u.id !== userId));
      } else {
        toast({ title: 'Ошибка', description: data.error, variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
  };

  const transferOwner = async (userId: number): Promise<boolean> => {
    if (!companyId) return false;
    try {
      const res = await fetch(functionUrls['company-users-update'], {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'transfer_owner', company_id: companyId, user_id: userId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const target = users.find(u => u.id === userId);
        const who = target?.full_name || target?.phone || '';
        toast({
          title: 'Роль владельца передана',
          description: [
            data.notified
              ? `${who} получит сообщение в выбранный им канал уведомлений.`
              : `${who} увидит уведомление в кабинете (канал уведомлений у него не выбран).`,
            data.notified_self
              ? 'Подтверждение отправлено в ваш канал уведомлений.'
              : 'Подтверждение — в ваших уведомлениях в кабинете.'
          ].join(' ')
        });
        await refreshCompanies();
        await loadData();
        return true;
      }
      toast({ title: 'Не удалось передать роль', description: data.error, variant: 'destructive' });
    } catch {
      toast({ title: 'Ошибка подключения', variant: 'destructive' });
    }
    return false;
  };

  if (isPageLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <Icon name="Loader2" className="animate-spin mx-auto mb-2" size={32} />
          <p className="text-muted-foreground">Загрузка доступов...</p>
        </div>
      </div>
    );
  }

  const rolesForUi = roles.map(r => ({
    id: r.slug,
    name: r.name,
    color: r.color,
    modules: r.modules,
    permissions: r.permissions
  }));

  const usersForUi = users
    .filter(u => u.status !== 'removed')
    .map(u => ({
      id: u.id,
      fullName: u.full_name || '',
      email: u.email || '',
      phone: u.phone,
      role: u.role_slug,
      status: u.status as 'active' | 'pending' | 'blocked',
      modules: roles.find(r => r.slug === u.role_slug)?.modules || [],
      lastActive: u.joined_at ? new Date(u.joined_at).toLocaleDateString('ru-RU') : 'Не заходил'
    }));

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-display font-bold text-foreground mb-2">Управление доступом</h2>
          <p className="text-muted-foreground">
            Роли, пользователи и права доступа компании «{currentCompany?.name}»
            {typeof maxUsers === 'number' && (
              <span className="ml-2 text-xs">· {activeAndPendingCount}/{maxUsers} пользователей по тарифу</span>
            )}
          </p>
        </div>
        
        <div className="flex flex-wrap gap-3">
          <InviteUserDialog
            open={showInviteDialog}
            onOpenChange={setShowInviteDialog}
            newUser={newUser}
            setNewUser={setNewUser}
            roles={rolesForUi}
            inviteLink={inviteLink}
            isLoading={isLoading}
            isLimitReached={isLimitReached}
            onInvite={handleInviteUser}
            onCopyLink={copyToClipboard}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {rolesForUi.map((role) => (
          <RoleCard
            key={role.id}
            role={role}
            userCount={users.filter(u => u.role_slug === role.id && u.status !== 'removed').length}
            modules={modules}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Пользователи</CardTitle>
          <CardDescription>Управляйте доступом пользователей к системе</CardDescription>
        </CardHeader>
        <CardContent>
          <UsersTable
            users={usersForUi}
            roles={rolesForUi}
            modules={modules}
            onToggleStatus={toggleUserStatus}
            onDeleteUser={deleteUser}
            currentUserId={user?.user_id}
            onTransferOwner={currentCompany?.role_slug === 'owner' ? transferOwner : undefined}
          />
        </CardContent>
      </Card>

      {invites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ожидают подтверждения</CardTitle>
            <CardDescription>Приглашения, которые ещё не были приняты</CardDescription>
          </CardHeader>
          <CardContent>
            <PendingInvitesTable
              invites={invites}
              onCancel={cancelInvite}
              onResend={resendInvite}
              resendingId={resendingId}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default AccessManagement;