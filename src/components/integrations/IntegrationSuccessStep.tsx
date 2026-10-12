import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Icon from '@/components/ui/icon';
import { Provider, acceptsIncomingWebhook, suggestsReceiptScenario, MOYKLASS_STAGE_HINTS, RK_STAGE_TITLES } from './providerFieldsConfig';

interface IntegrationSuccessStepProps {
  selectedProvider: Provider;
  stage?: string;
  webhookUrl: string;
  onCopyWebhookUrl: () => void;
  onFinish: () => void;
  onSetupReceipts?: () => void;
  autoWebhook?: boolean;
}

const IntegrationSuccessStep = ({
  selectedProvider,
  stage,
  webhookUrl,
  onCopyWebhookUrl,
  onFinish,
  onSetupReceipts,
  autoWebhook
}: IntegrationSuccessStepProps) => {
  const offerReceipts = !!onSetupReceipts && suggestsReceiptScenario(selectedProvider.slug);
  return (
    <div className="space-y-4">
      <div className="bg-success/10 p-4 rounded-lg">
        <div className="flex items-center gap-2 mb-2">
          <Icon name="CheckCircle" className="text-success" size={20} />
          <span className="font-semibold text-success">
            Интеграция создана!
          </span>
        </div>
      </div>

      {autoWebhook ? (
        <div className="bg-info/10 p-4 rounded-lg">
          <div className="flex items-start gap-2">
            <Icon name="Info" className="text-info mt-0.5" size={18} />
            <p className="text-sm text-muted-foreground">
              Уведомления об оплатах по платёжным ссылкам Точка будет присылать сама — настраивать вебхук не нужно.
              Для чеков передавайте товары (Items) при создании платёжной ссылки
            </p>
          </div>
        </div>
      ) : acceptsIncomingWebhook(selectedProvider.slug) ? (
        <>
          <div>
            <Label>Ваш уникальный URL для вебхуков</Label>
            <div className="flex gap-2 mt-1">
              <Input value={webhookUrl} readOnly className="font-mono text-sm" />
              <Button onClick={onCopyWebhookUrl} variant="outline" size="icon">
                <Icon name="Copy" size={16} />
              </Button>
            </div>
          </div>

          <div className="bg-info/10 p-4 rounded-lg space-y-3">
            <div className="flex items-start gap-2">
              <Icon name="Info" className="text-info mt-0.5" size={18} />
              <div className="text-sm">
                <p className="font-semibold text-foreground mb-2">
                  Инструкция по настройке:
                </p>
                {selectedProvider.slug === 'realtycalendar' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>RealtyCalendar → Настройки → CRM-интеграции → поле «Введите URL нового Webhook»: вставьте этот URL и нажмите «Запустить»</li>
                    <li>Этот адрес обрабатывает только этап «{RK_STAGE_TITLES[stage || 'income']}». Для другого этапа подключите ещё одну интеграцию — RealtyCalendar поддерживает несколько адресов</li>
                    <li>RealtyCalendar списывает плату по своему тарифу «за интеграцию с внешними системами»</li>
                    <li>Чек: {stage === 'refund' ? 'возврат предоплаты' : 'предоплата за проживание'}, название — объект и даты, контакт — телефон или почта гостя</li>
                  </ol>
                ) : selectedProvider.slug === 'moyklass' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>«Мой Класс» → Настройки → API и webhooks → вкладка «Webhooks» → «+ Webhook»: вставьте этот URL и сохраните</li>
                    <li>Настройки → Сценарии → сценарий по событию «{MOYKLASS_STAGE_HINTS[stage || 'payment_new']?.event}» → действие «Отправить вебхук» с этим вебхуком</li>
                    <li>Этот адрес принимает только этап «{MOYKLASS_STAGE_HINTS[stage || 'payment_new']?.title}». Другие события сюда не отправляйте — для них подключите отдельную интеграцию</li>
                    <li>
                      {stage === 'debit_new'
                        ? 'Чек: полный расчёт за услугу с зачётом аванса на сумму списания, контакт — телефон или почта ученика'
                        : 'Чек: предоплата за услугу, название — вид абонемента, контакт — телефон или почта ученика'}
                    </li>
                  </ol>
                ) : selectedProvider.slug === 'tochka_acquiring' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>Вебхук в Точке создаётся через API (метод Create Webhook) с этим URL</li>
                    <li>Событие — acquiringInternetPayment (оплаты по платёжным ссылкам)</li>
                    <li>Для чеков передавайте товары (Items) при создании платёжной ссылки</li>
                    <li>Подпись каждого вебхука проверяем ключом Точки автоматически</li>
                  </ol>
                ) : selectedProvider.slug === 'cloudpayments' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>ЛК CloudPayments → Сайты → ваш сайт → Настройки → блок «Уведомления»</li>
                    <li>Вставьте этот URL в уведомления Pay, Fail, Refund и Cancel (при двухстадийной оплате — ещё Confirm). Check не включайте</li>
                    <li>Метод — POST, кодировка — UTF-8, формат — CloudPayments</li>
                    <li>Подпись каждого уведомления проверяем по API Secret, оплату дополнительно сверяем с CloudPayments</li>
                    <li>Для чека с товарами передавайте состав чека (CustomerReceipt) в данные платежа, иначе — одна позиция на сумму с назначением платежа. Почта покупателя — из уведомления или из шаблона действия</li>
                  </ol>
                ) : selectedProvider.slug === 'yookassa' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>ЮKassa → Интеграция → HTTP-уведомления: вставьте этот URL в поле «URL для уведомлений»</li>
                    <li>Отметьте события: payment.succeeded, refund.succeeded (по желанию — payment.waiting_for_capture и payment.canceled) и сохраните</li>
                    <li>Каждое уведомление сверяем с ЮKassa по shopId и секретному ключу — поддельные не примутся</li>
                    <li>Почты покупателя в уведомлении ЮKassa нет: укажите «Почту по умолчанию» в шаблоне действия сценария чеков</li>
                    <li>Если магазин отправляет чеки через ЮKassa, позиции чека берём оттуда, иначе — одна позиция на сумму с описанием платежа</li>
                  </ol>
                ) : selectedProvider.slug === 'alfabank' ? (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>Напишите в поддержку интернет-эквайринга Альфа-Банка</li>
                    <li>Попросите включить callback-уведомления и пришлите им этот URL</li>
                    <li>Метод GET или POST — подойдёт любой</li>
                    <li>Нужны операции: deposited (оплата), approved, reversed, refunded — для карт и СБП они одинаковые</li>
                    <li>Для чеков магазин должен передавать корзину (orderBundle) при регистрации заказа</li>
                  </ol>
                ) : (
                  <ol className="list-decimal list-inside space-y-1 text-muted-foreground">
                    <li>Откройте личный кабинет сервиса</li>
                    <li>Перейдите в раздел уведомлений / вебхуков</li>
                    <li>Вставьте скопированный URL в поле "URL для уведомлений"</li>
                    <li>Выберите метод: POST</li>
                    <li>Сохраните настройки</li>
                  </ol>
                )}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="bg-info/10 p-4 rounded-lg space-y-2">
          <div className="flex items-start gap-2">
            <Icon name="Info" className="text-info mt-0.5" size={18} />
            <p className="text-sm text-muted-foreground">
              Интеграция подключена и начнёт синхронизацию данных автоматически.
              Дополнительных действий на вашей стороне не требуется.
            </p>
          </div>
        </div>
      )}

      {offerReceipts && (
        <div className="rounded-lg border border-primary/40 bg-primary/5 p-4 space-y-1">
          <div className="flex items-center gap-2 font-semibold text-foreground">
            <Icon name="Receipt" size={18} className="text-primary" />
            Чеки сами не пробиваются
          </div>
          <p className="text-sm text-muted-foreground">
            Платежи и корзины будут сохраняться, но чтобы по каждой оплате пробивался чек в кассе,
            нужен сценарий в «Автоматизации». Мы заполним его за вас — останется выбрать кассу и запустить.
          </p>
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        {offerReceipts ? (
          <>
            <Button variant="outline" onClick={onFinish}>
              Позже
            </Button>
            <Button onClick={onSetupReceipts}>
              <Icon name="Receipt" size={16} className="mr-2" />
              Настроить чеки
            </Button>
          </>
        ) : (
          <Button onClick={onFinish}>
            Готово
          </Button>
        )}
      </div>
    </div>
  );
};

export default IntegrationSuccessStep;
