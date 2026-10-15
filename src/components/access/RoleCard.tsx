import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';

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

interface RoleCardProps {
  role: Role;
  userCount: number;
  modules: Module[];
}

const RoleCard = ({ role, userCount, modules }: RoleCardProps) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <Card className="transition-shadow hover:shadow-lg">
      <CardContent className="p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${role.color}`} />
            <span className="truncate font-semibold text-foreground">{role.name}</span>
          </div>
          <Badge variant="secondary" title="Пользователей с этой ролью">
            {userCount}
          </Badge>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {role.modules.length} модулей
          <Icon name={expanded ? 'ChevronUp' : 'ChevronDown'} size={12} />
        </button>
        {expanded && (
          <ul className="mt-2 space-y-1">
            {role.modules.map((moduleId) => {
              const module = modules.find((m) => m.id === moduleId);
              return module ? (
                <li key={moduleId} className="flex items-center gap-2 text-xs text-foreground">
                  <Icon name={module.icon} fallback="Circle" size={12} className="text-muted-foreground" />
                  {module.name}
                </li>
              ) : null;
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};

export default RoleCard;
