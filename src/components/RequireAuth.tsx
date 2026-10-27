import { ReactNode } from 'react';
import { Navigate } from "@/lib/router-compat";
import { useAuth } from '@/contexts/AuthContext';
import Icon from '@/components/ui/icon';

const RequireAuth = ({ children }: { children: ReactNode }) => {
  const { user, companies, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (companies.length === 0) {
    return <Navigate to="/create-company" replace />;
  }

  return <>{children}</>;
};

export default RequireAuth;
