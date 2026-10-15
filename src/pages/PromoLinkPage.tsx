import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Icon from '@/components/ui/icon';
import { useAuth } from '@/contexts/AuthContext';
import { rememberPromo } from '@/lib/pendingPromo';

const PromoLinkPage = () => {
  const { code } = useParams();
  const { user, companies, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (code) rememberPromo(code);
  }, [code]);

  useEffect(() => {
    if (isLoading) return;
    if (!user) navigate('/login', { replace: true });
    else if (companies.length === 0) navigate('/create-company', { replace: true });
    else navigate('/app?section=subscription', { replace: true });
  }, [isLoading, user, companies.length, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Icon name="Loader2" className="animate-spin text-primary" size={32} />
    </div>
  );
};

export default PromoLinkPage;
