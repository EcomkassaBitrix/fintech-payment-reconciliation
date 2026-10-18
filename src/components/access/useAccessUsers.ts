import { useState, useEffect } from 'react';
import { useToast } from '@/hooks/use-toast';
import functionUrls from '../../../backend/func2url.json';
import { CompanyUser, Invite, Role } from '@/components/access/accessTypes';

const useAccessUsers = (companyId: number | undefined, refreshCompanies: () => Promise<void>) => {
  const [users, setUsers] = useState<CompanyUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [isPageLoading, setIsPageLoading] = useState(true);
  const { toast } = useToast();

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

  const toggleUserStatus = async (userId: number) => {
    if (!companyId) return;
    const targetUser = users.find(u => u.id === userId);
    if (!targetUser) return;

    const newStatus = targetUser.status === 'active' ? 'blocked' : 'active';

    try {
      const res = await fetch(functionUrls['company-users-list'], {
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
      const res = await fetch(functionUrls['company-users-list'], {
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
      const res = await fetch(functionUrls['company-users-list'], {
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

  return {
    users,
    invites,
    setInvites,
    roles,
    isPageLoading,
    loadData,
    toggleUserStatus,
    deleteUser,
    transferOwner
  };
};

export default useAccessUsers;
