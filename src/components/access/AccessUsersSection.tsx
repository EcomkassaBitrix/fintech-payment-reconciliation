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
  return (
    <>
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
            onToggleStatus={onToggleStatus}
            onDeleteUser={onDeleteUser}
            currentUserId={currentUserId}
            onTransferOwner={onTransferOwner}
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
