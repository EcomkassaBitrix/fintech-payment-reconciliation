import { useAuth } from '@/contexts/AuthContext';
import InviteUserDialog from '@/components/access/InviteUserDialog';
import AccessUsersSection from '@/components/access/AccessUsersSection';
import useAccessUsers from '@/components/access/useAccessUsers';
import useInviteActions from '@/components/access/useInviteActions';
import Icon from '@/components/ui/icon';
import SupportAccessCard from '@/components/settings/SupportAccessCard';

const AccessManagement = () => {
  const { user, currentCompany, refreshCompanies } = useAuth();
  const companyId = currentCompany?.id;
  const maxUsers = currentCompany?.max_users;

  const {
    users,
    invites,
    setInvites,
    roles,
    isPageLoading,
    loadData,
    toggleUserStatus,
    deleteUser,
    transferOwner
  } = useAccessUsers(companyId, refreshCompanies);

  const {
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
  } = useInviteActions({
    companyId,
    companyName: currentCompany?.name,
    userId: user?.user_id,
    roles,
    invites,
    setInvites,
    loadData
  });

  const activeAndPendingCount = users.filter(u => u.status !== 'removed').length + invites.length;
  const isLimitReached = typeof maxUsers === 'number' && activeAndPendingCount >= maxUsers;

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
            Роли, пользователи
            {typeof maxUsers === 'number' && (
              <span className="text-xs">· {activeAndPendingCount}/{maxUsers} пользователей по тарифу</span>
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

      {currentCompany && !currentCompany.support_access
        && ['owner', 'admin'].includes(currentCompany.role_slug) && (
        <SupportAccessCard companyId={currentCompany.id} timezone={currentCompany.timezone} />
      )}

      <AccessUsersSection
        users={users}
        invites={invites}
        rolesForUi={rolesForUi}
        usersForUi={usersForUi}
        currentUserId={user?.user_id}
        onToggleStatus={toggleUserStatus}
        onDeleteUser={deleteUser}
        onTransferOwner={currentCompany?.role_slug === 'owner' ? transferOwner : undefined}
        onCancelInvite={cancelInvite}
        onResendInvite={resendInvite}
        resendingId={resendingId}
      />
    </div>
  );
};

export default AccessManagement;