import { useState } from 'react';
import Icon from '@/components/ui/icon';
import { pendingPromo, pendingPromoError } from '@/lib/pendingPromo';

interface Props {
  hint: string;
  className?: string;
}

const PendingPromoNotice = ({ hint, className = '' }: Props) => {
  const [code] = useState(pendingPromo);
  const [error] = useState(pendingPromoError);
  if (!code) return null;
  if (error) {
    return (
      <div className={`flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-3 animate-fade-in ${className}`}>
        <Icon name="CircleAlert" size={20} className="mt-0.5 shrink-0 text-destructive" />
        <div className="text-sm">
          <div className="font-medium text-foreground">
            Промокод <span className="font-mono">{code}</span> недействителен
          </div>
          <div className="text-muted-foreground">{error}</div>
        </div>
      </div>
    );
  }
  return (
    <div className={`flex items-start gap-3 rounded-lg border border-primary/40 bg-primary/10 p-3 animate-fade-in ${className}`}>
      <Icon name="Gift" size={20} className="mt-0.5 shrink-0 text-primary" />
      <div className="text-sm">
        <div className="font-medium text-foreground">
          По ссылке будет применён промокод <span className="font-mono text-primary">{code}</span>
        </div>
        <div className="text-muted-foreground">{hint}</div>
      </div>
    </div>
  );
};

export default PendingPromoNotice;
