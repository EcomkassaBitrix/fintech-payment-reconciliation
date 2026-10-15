import { useState } from 'react';
import Icon from '@/components/ui/icon';
import { pendingPromo } from '@/lib/pendingPromo';

interface Props {
  hint: string;
  className?: string;
}

const PendingPromoNotice = ({ hint, className = '' }: Props) => {
  const [code] = useState(pendingPromo);
  if (!code) return null;
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
