import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Icon from '@/components/ui/icon';
import { formatDistanceToNow } from 'date-fns';
import { ru } from 'date-fns/locale';
import { AppNotification } from '@/hooks/useNotifications';

interface NotificationCenterProps {
  items: AppNotification[];
  unread: number;
  isLoading: boolean;
  onClose: () => void;
  onMarkRead: (ids?: number[]) => void;
  onHide: (id: number) => void;
  onReload: () => void;
  onOpen: (notification: AppNotification) => void;
}

const LEVEL_STYLE: Record<string, { icon: string; color: string; bg: string }> = {
  success: { icon: 'CheckCircle2', color: 'text-success', bg: 'bg-success/20' },
  warning: { icon: 'AlertTriangle', color: 'text-warning', bg: 'bg-warning/20' },
  error: { icon: 'XCircle', color: 'text-destructive', bg: 'bg-destructive/20' },
  info: { icon: 'Info', color: 'text-info', bg: 'bg-info/20' }
};

const linkLabel = (n: AppNotification) => {
  if (n.kind === 'missing_receipts' && n.payload?.date) return 'Показать платежи без чека';
  return n.link_module ? MODULE_LABELS[n.link_module] : undefined;
};

const MODULE_LABELS: Record<string, string> = {
  automation: 'Открыть автоматизацию',
  transactions: 'Открыть транзакции',
  reconciliation: 'Открыть сверку',
  integrations: 'Открыть интеграции',
  subscription: 'Открыть подписку'
};

const timeAgo = (value: string) => {
  const iso = /Z|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: ru });
};

const NotificationCenter = ({
  items, unread, isLoading, onClose, onMarkRead, onHide, onReload, onOpen
}: NotificationCenterProps) => {
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const visible = filter === 'unread' ? items.filter((n) => !n.read) : items;

  const open = (n: AppNotification) => {
    if (!n.read) onMarkRead([n.id]);
    if (n.link_module) {
      onOpen(n);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 animate-fade-in" onClick={onClose}>
      <div
        className="fixed right-0 top-0 h-full w-full md:w-[500px] bg-background border-l border-border shadow-2xl animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-col h-full">
          <div className="p-6 border-b border-border">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center">
                  <Icon name="Bell" size={20} className="text-primary" />
                </div>
                <div>
                  <h2 className="text-2xl font-display font-bold text-foreground">Уведомления</h2>
                  <p className="text-sm text-muted-foreground">
                    {unread > 0 ? `${unread} непрочитанных` : 'Все прочитаны'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="icon" onClick={onReload} title="Обновить">
                  <Icon name="RefreshCw" size={18} className={isLoading ? 'animate-spin' : ''} />
                </Button>
                <Button variant="ghost" size="icon" onClick={onClose}>
                  <Icon name="X" size={20} />
                </Button>
              </div>
            </div>

            <div className="flex gap-2">
              <Button variant={filter === 'all' ? 'default' : 'outline'} size="sm" onClick={() => setFilter('all')} className="flex-1">
                Все
              </Button>
              <Button variant={filter === 'unread' ? 'default' : 'outline'} size="sm" onClick={() => setFilter('unread')} className="flex-1">
                Непрочитанные
                {unread > 0 && <Badge className="ml-2" variant="secondary">{unread}</Badge>}
              </Button>
            </div>

            {unread > 0 && (
              <Button variant="ghost" size="sm" onClick={() => onMarkRead()} className="w-full mt-2">
                <Icon name="CheckCheck" size={16} className="mr-2" />
                Отметить все прочитанными
              </Button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {visible.length === 0 ? (
                <div className="text-center py-12">
                  <Icon name="Inbox" size={48} className="mx-auto mb-4 text-muted-foreground" />
                  <p className="text-muted-foreground">
                    {filter === 'unread' ? 'Нет непрочитанных уведомлений' : 'Уведомлений пока нет'}
                  </p>
                </div>
              ) : (
                visible.map((n) => {
                  const style = LEVEL_STYLE[n.level] || LEVEL_STYLE.info;
                  return (
                    <Card
                      key={n.id}
                      className={`transition-all cursor-pointer hover:shadow-md ${!n.read ? 'border-primary/50 bg-primary/5' : ''}`}
                      onClick={() => open(n)}
                    >
                      <CardContent className="p-4">
                        <div className="flex gap-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${style.bg}`}>
                            <Icon name={style.icon} size={20} className={style.color} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <h4 className="font-semibold text-foreground text-sm">{n.title}</h4>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 flex-shrink-0"
                                title="Убрать из списка"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onHide(n.id);
                                }}
                              >
                                <Icon name="X" size={14} />
                              </Button>
                            </div>
                            <p className="text-sm text-muted-foreground mb-2">{n.message}</p>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs text-muted-foreground flex items-center gap-1">
                                <Icon name="Clock" size={12} />
                                {timeAgo(n.created_at)}
                              </span>
                              {!n.read && <Badge variant="secondary" className="text-xs">Новое</Badge>}
                              {linkLabel(n) && (
                                <span className="text-xs text-primary flex items-center gap-1">
                                  {linkLabel(n)}
                                  <Icon name="ArrowRight" size={12} />
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })
              )}
            </div>
          </div>

          <div className="p-4 border-t border-border">
            <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
              <Icon name="MessageSquare" size={16} className="mt-0.5 shrink-0" />
              <span>Дублировать уведомления себе в Max, WhatsApp, Telegram или на почту можно в разделе «Настройки».</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NotificationCenter;
