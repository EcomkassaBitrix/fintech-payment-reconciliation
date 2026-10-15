import { useState } from 'react';
import { Button } from '@/components/ui/button';
import Icon from '@/components/ui/icon';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import RoleCard from '@/components/access/RoleCard';
import UsersTable from '@/components/access/UsersTable';
import PendingInvitesTable from '@/components/access/PendingInvitesTable';
import { CompanyUser, Invite, modules } from '@/components/access/accessTypes';

interface RoleForUi {
  id: string;
  name: string;
  color: string;
  modules: string[];
  permissions: string[];
}

interface UserForUi {
  id: number;
  fullName: string;
  email: string;
  phone: string;
  role: string;
  status: 'active' | 'pending' | 'blocked';
  modules: string[];
  lastActive: string;
}

interface AccessUsersSectionProps {
  users: CompanyUser[];
  invites: Invite[];
  rolesForUi: RoleForUi[];
  usersForUi: UserForUi[];
  currentUserId?: number;
  onToggleStatus: (userId: number) => void;
  onDeleteUser: (userId: number) => void;
  onTransferOwner?: (userId: number) => Promise<boolean>;
  onCancelInvite: (inviteId: number) => void;
  onResendInvite: (invite: Invite, channel?: string) => void;
  resendingId: number | null;
}

const AccessUsersSection = ({
  users,
  invites,
  rolesForUi,
  usersForUi,
  currentUserId,
  onToggleStatus,
  onDeleteUser,
  onTransferOwner,
  onCancelInvite,
  onResendInvite,
  resendingId
}: AccessUsersSectionProps) => {
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const filterRole = rolesForUi.find((r) => r.id === roleFilter) || null;
  const shownUsers = filterRole ? usersForUi.filter((u) => u.role === filterRole.id) : usersForUi;

  return (
    <>
      <div
        className="grid items-start gap-3"
        style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${rolesForUi.length > 4 ? 170 : 200}px, 1fr))` }}
      >
        {rolesForUi.map((role) => (
          <RoleCard
            key={role.id}
            role={role}
            userCount={users.filter(u => u.role_slug === role.id && u.status !== 'removed').length}
            modules={modules}
            active={roleFilter === role.id}
            onCountClick={() => setRoleFilter(roleFilter === role.id ? null : role.id)}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1.5">
              <CardTitle>Пользователи</CardTitle>
              <CardDescription>Управляйте доступом пользователей к системе</CardDescription>
            </div>
            {filterRole && (
              <Button variant="outline" size="sm" className="gap-2" onClick={() => setRoleFilter(null)}>
                Роль: {filterRole.name}
                <Icon name="X" size={14} />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {filterRole && shownUsers.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">С ролью «{filterRole.name}» пользователей нет</div>
          ) : (
          <UsersTable
            users={shownUsers}
            roles={rolesForUi}
            modules={modules}
            onToggleStatus={onToggleStatus}
            onDeleteUser={onDeleteUser}
            currentUserId={currentUserId}
            onTransferOwner={onTransferOwner}
          />
          )}
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
              onCancel={onCancelInvite}
              onResend={onResendInvite}
              resendingId={resendingId}
            />
          </CardContent>
        </Card>
      )}
    </>
  );
};

export default AccessUsersSection;
