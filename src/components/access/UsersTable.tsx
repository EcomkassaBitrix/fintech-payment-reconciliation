import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import TransferOwnerDialog from '@/components/access/TransferOwnerDialog';

interface User {
  id: number;
  fullName: string;
  email: string;
  phone: string;
  role: string;
  status: 'active' | 'pending' | 'blocked';
  modules: string[];
  lastActive: string;
}

interface Role {
  id: string;
  name: string;
  color: string;
  modules: string[];
  permissions: string[];
}

interface Module {
  id: string;
  name: string;
  icon: string;
}

interface UsersTableProps {
  users: User[];
  roles: Role[];
  modules: Module[];
  onToggleStatus: (userId: number) => void;
  onDeleteUser: (userId: number) => void;
  currentUserId?: number;
  onTransferOwner?: (userId: number) => Promise<boolean>;
}

const UsersTable = ({ users, roles, modules, onToggleStatus, onDeleteUser, currentUserId, onTransferOwner }: UsersTableProps) => {
  const getRoleInfo = (roleId: string) => {
    return roles.find(r => r.id === roleId) || roles[0];
  };

  return (
    <Table className="min-w-[560px]">
      <TableHeader>
        <TableRow>
          <TableHead>ФИО</TableHead>
          <TableHead>Контакты</TableHead>
          <TableHead>Роль</TableHead>
          <TableHead>Статус</TableHead>
          <TableHead>Модули</TableHead>
          <TableHead>Последняя активность</TableHead>
          <TableHead className="text-right">Действия</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((user) => {
          const roleInfo = getRoleInfo(user.role);
          return (
            <TableRow key={user.id}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
                    <Icon name="User" size={20} className="text-primary" />
                  </div>
                  <div>
                    {user.fullName ? (
                      <div className="font-medium">{user.fullName}</div>
                    ) : (
                      <div className="text-sm italic text-muted-foreground">Не указано</div>
                    )}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <div className="space-y-1">
                  <div className="text-sm">{user.phone}</div>
                  <div className="text-xs text-muted-foreground">{user.email}</div>
                </div>
              </TableCell>
              <TableCell>
                <Badge className={`${roleInfo.color} text-white`}>
                  {roleInfo.name}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={
                  user.status === 'active' ? 'default' :
                  user.status === 'pending' ? 'secondary' :
                  'destructive'
                }>
                  {user.status === 'active' ? 'Активен' :
                   user.status === 'pending' ? 'Ожидает' :
                   'Заблокирован'}
                </Badge>
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  {user.modules.slice(0, 3).map((moduleId) => {
                    const module = modules.find(m => m.id === moduleId);
                    return module ? (
                      <Icon key={moduleId} name={module.icon as any} size={16} className="text-muted-foreground" />
                    ) : null;
                  })}
                  {user.modules.length > 3 && (
                    <span className="text-xs text-muted-foreground">+{user.modules.length - 3}</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">{user.lastActive}</span>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  {user.role === 'owner' && user.id === currentUserId && onTransferOwner && (
                    <TransferOwnerDialog
                      candidates={users
                        .filter((u) => u.id !== user.id && u.status === 'active')
                        .map((u) => ({ id: u.id, fullName: u.fullName, phone: u.phone }))}
                      onTransfer={onTransferOwner}
                    />
                  )}
                  {user.role !== 'owner' && (
                    <>
                      <Button 
                        variant="ghost" 
                        size="icon"
                        onClick={() => onToggleStatus(user.id)}
                      >
                        <Icon name={user.status === 'active' ? 'Ban' : 'CheckCircle'} size={16} />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="icon"
                        onClick={() => onDeleteUser(user.id)}
                      >
                        <Icon name="Trash2" size={16} className="text-destructive" />
                      </Button>
                    </>
                  )}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
};

export default UsersTable;