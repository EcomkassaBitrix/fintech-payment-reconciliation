import { useState } from 'react';
import { Navigate } from "@/lib/router-compat";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import PendingPromoNotice from '@/components/PendingPromoNotice';
import { formatPhoneNumber, isValidPhone } from '@/lib/formatters';

type MessengerType = 'whatsapp' | 'telegram' | 'max' | null;

const Login = () => {
  const [step, setStep] = useState<'phone' | 'code' | 'blocked'>('phone');
  const [phone, setPhone] = useState('+7');
  const [selectedMessenger, setSelectedMessenger] = useState<MessengerType>(null);
  const [code, setCode] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [blockTime, setBlockTime] = useState(0);
  const { toast } = useToast();
  const { requestCode, loginWithPhone, user, isLoading: authLoading } = useAuth();

  const MAX_ATTEMPTS = 5;
  const BLOCK_DURATION = 300;

  const messengers = [
    { id: 'whatsapp' as MessengerType, icon: 'MessageCircle', label: 'WhatsApp', color: 'hover:bg-success/10' },
    { id: 'telegram' as MessengerType, icon: 'Send', label: 'Telegram', color: 'hover:bg-info/10' },
    { id: 'max' as MessengerType, icon: 'Mail', label: 'Max', color: 'hover:bg-accent/10' }
  ];

  const messengerLabel = (m: MessengerType) => messengers.find((x) => x.id === m)?.label || 'мессенджер';

  const startBlock = () => {
    setStep('blocked');
    setBlockTime(BLOCK_DURATION);
    const timer = setInterval(() => {
      setBlockTime((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setStep('phone');
          setAttempts(0);
          setCode('');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const handleSendCode = async () => {
    if (!isValidPhone(phone) || !selectedMessenger) return;
    setIsLoading(true);
    try {
      await requestCode(phone.replace(/\D/g, ''), selectedMessenger, 'login');
      setAttempts(0);
      setCode('');
      toast({ title: 'Код отправлен', description: `Проверьте ${messengerLabel(selectedMessenger)}` });
      setStep('code');
    } catch (error) {
      toast({
        title: 'Ошибка отправки',
        description: `${(error as Error).message}. Попробуйте другой мессенджер`,
        variant: 'destructive'
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (code.length !== 6) return;
    setIsLoading(true);
    try {
      await loginWithPhone(phone, code);
      window.location.href = '/app';
    } catch (error) {
      const message = (error as Error).message || 'Не удалось войти';
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);
      setCode('');
      if (/истёк|не запрашивался/i.test(message)) {
        setStep('phone');
        toast({ title: 'Код больше не действует', description: message, variant: 'destructive' });
      } else if (/Превышено/i.test(message) || newAttempts >= MAX_ATTEMPTS) {
        startBlock();
        toast({
          title: 'Превышен лимит попыток',
          description: `Запросите новый код через ${Math.floor(BLOCK_DURATION / 60)} минут`,
          variant: 'destructive'
        });
      } else {
        toast({ title: 'Ошибка входа', description: message, variant: 'destructive' });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatPhoneNumber(e.target.value, phone);
    if (formatted.replace(/\D/g, '').length <= 11) {
      setPhone(formatted);
      if (isValidPhone(formatted) && !selectedMessenger) setSelectedMessenger(messengers[0].id);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Icon name="Loader2" className="animate-spin text-primary" size={32} />
      </div>
    );
  }

  if (user) {
    return <Navigate to="/app" replace />;
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center animate-fade-in">
          <a href="/" className="flex items-center justify-center gap-2 mb-2">
            <Icon name="Zap" size={32} className="text-primary" />
            <h1 className="text-3xl font-display font-bold text-foreground">Сверка</h1>
          </a>
          <p className="text-sm text-muted-foreground">Автоматизация платежей</p>
        </div>

        <PendingPromoNotice className="mb-4" hint="Войдите или зарегистрируйтесь — подписка включится сама" />

        <Card className="shadow-2xl border-0 animate-scale-in">
          <CardHeader className="text-center pb-4">
            <CardTitle className="text-2xl font-display">
              {step === 'phone' ? 'Введите номер телефона или почту' : step === 'code' ? 'Введите код' : 'Доступ заблокирован'}
            </CardTitle>
            <CardDescription className="text-base">
              {step === 'phone' 
                ? 'Чтобы войти или зарегистрироваться'
                : step === 'code'
                ? `Код отправлен в ${selectedMessenger === 'whatsapp' ? 'WhatsApp' : selectedMessenger === 'telegram' ? 'Telegram' : 'Max'}`
                : 'Превышен лимит попыток ввода кода'
              }
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-6">
            {step === 'phone' ? (
              <>
                <div className="space-y-4">
                  <div className="relative">
                    <div className="absolute left-3 top-1/2 -translate-y-1/2 flex items-center gap-2 pointer-events-none">
                      <div className="w-6 h-6 rounded-full overflow-hidden flex items-center justify-center bg-muted">
                        <span className="text-xs font-bold">🇷🇺</span>
                      </div>
                    </div>
                    <Input
                      type="tel"
                      value={phone}
                      onChange={handlePhoneChange}
                      placeholder="+7 (___) ___-__-__"
                      className="pl-14 h-14 text-lg border-2 focus:border-primary transition-all"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-sm text-muted-foreground">Получить код в:</Label>
                    <div className="grid grid-cols-3 gap-3">
                      {messengers.map((messenger) => (
                        <button
                          key={messenger.id}
                          onClick={() => setSelectedMessenger(messenger.id)}
                          className={`flex flex-col items-center justify-center gap-2 p-4 rounded-xl border-2 transition-all ${
                            selectedMessenger === messenger.id
                              ? 'border-primary bg-primary/5 scale-105'
                              : 'border-border hover:border-primary/50'
                          } ${messenger.color}`}
                        >
                          <Icon name={messenger.icon as any} size={24} className={
                            selectedMessenger === messenger.id ? 'text-primary' : 'text-muted-foreground'
                          } />
                          <span className={`text-xs font-medium ${
                            selectedMessenger === messenger.id ? 'text-primary' : 'text-muted-foreground'
                          }`}>
                            {messenger.label}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <Button 
                  onClick={handleSendCode}
                  disabled={!isValidPhone(phone) || !selectedMessenger || isLoading}
                  className="w-full h-14 text-lg font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all"
                >
                  {isLoading ? (
                    <>
                      <Icon name="Loader2" size={20} className="mr-2 animate-spin" />
                      Отправка...
                    </>
                  ) : 'Войти'}
                </Button>

                <p className="text-xs text-center text-muted-foreground px-4">
                  Нажимая «Войти», вы принимаете{' '}
                  <a href="/offer" target="_blank" rel="noreferrer" className="underline hover:text-foreground">оферту</a>{' '}
                  и{' '}
                  <a href="/legal" target="_blank" rel="noreferrer" className="underline hover:text-foreground">политику обработки персональных данных</a>
                </p>
              </>
            ) : step === 'code' ? (
              <>
                <div className="space-y-6">
                  <div className="flex justify-center">
                    <InputOTP
                      autoFocus
                      maxLength={6}
                      value={code}
                      onChange={(value) => setCode(value)}
                    >
                      <InputOTPGroup>
                        <InputOTPSlot index={0} className="w-12 h-14 text-xl" />
                        <InputOTPSlot index={1} className="w-12 h-14 text-xl" />
                        <InputOTPSlot index={2} className="w-12 h-14 text-xl" />
                        <InputOTPSlot index={3} className="w-12 h-14 text-xl" />
                        <InputOTPSlot index={4} className="w-12 h-14 text-xl" />
                        <InputOTPSlot index={5} className="w-12 h-14 text-xl" />
                      </InputOTPGroup>
                    </InputOTP>
                  </div>

                  <div className="text-center space-y-2">
                    <p className="text-sm text-muted-foreground">
                      Не пришёл код?
                    </p>
                    <Button 
                      variant="link" 
                      onClick={handleSendCode}
                      disabled={isLoading}
                      className="text-primary"
                    >
                      {isLoading ? 'Отправка...' : 'Отправить повторно'}
                    </Button>
                  </div>
                </div>

                <Button 
                  onClick={handleVerifyCode}
                  disabled={code.length !== 6 || isLoading}
                  className="w-full h-14 text-lg font-semibold bg-primary hover:bg-primary/90 text-primary-foreground transition-all"
                >
                  {isLoading ? (
                    <>
                      <Icon name="Loader2" size={20} className="mr-2 animate-spin" />
                      Вход...
                    </>
                  ) : 'Подтвердить'}
                </Button>

                <Button 
                  variant="ghost" 
                  onClick={() => {
                    setStep('phone');
                    setCode('');
                    setAttempts(0);
                  }}
                  className="w-full"
                >
                  <Icon name="ArrowLeft" size={16} className="mr-2" />
                  Изменить номер
                </Button>
              </>
            ) : (
              <>
                <div className="space-y-6">
                  <div className="flex justify-center">
                    <div className="w-20 h-20 rounded-full bg-destructive/20 flex items-center justify-center">
                      <Icon name="Ban" size={48} className="text-destructive" />
                    </div>
                  </div>
                  
                  <div className="text-center space-y-2">
                    <h3 className="text-xl font-semibold text-foreground">
                      Слишком много попыток
                    </h3>
                    <p className="text-muted-foreground">
                      Вы ввели неверный код {MAX_ATTEMPTS} раз.
                      <br />
                      Попробуйте снова через:
                    </p>
                    <div className="text-4xl font-display font-bold text-destructive mt-4">
                      {Math.floor(blockTime / 60)}:{String(blockTime % 60).padStart(2, '0')}
                    </div>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Login;