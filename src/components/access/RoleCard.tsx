import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className={`w-3 h-3 rounded-full ${role.color}`} />
          <Badge variant="secondary">
            {userCount}
          </Badge>
        </div>
        <CardTitle className="text-lg">{role.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {role.modules.length} модулей
            <Icon name={expanded ? 'ChevronUp' : 'ChevronDown'} size={12} />
          </button>
          {expanded ? (
            <ul className="space-y-1.5">
              {role.modules.map((moduleId) => {
                const module = modules.find((m) => m.id === moduleId);
                return module ? (
                  <li key={moduleId} className="flex items-center gap-2 text-sm text-foreground">
                    <Icon name={module.icon} fallback="Circle" size={14} className="text-muted-foreground" />
                    {module.name}
                  </li>
                ) : null;
              })}
            </ul>
          ) : (
            <div className="flex flex-wrap gap-1">
              {role.modules.slice(0, 3).map((moduleId) => {
                const module = modules.find((m) => m.id === moduleId);
                return module ? (
                  <Badge key={moduleId} variant="outline" className="text-xs">
                    <Icon name={module.icon} fallback="Circle" size={12} className="mr-1" />
                    {module.name}
                  </Badge>
                ) : null;
              })}
              {role.modules.length > 3 && (
                <button type="button" onClick={() => setExpanded(true)}>
                  <Badge variant="outline" className="text-xs hover:bg-muted">
                    +{role.modules.length - 3}
                  </Badge>
                </button>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default RoleCard;
