UPDATE t_p83864310_fintech_payment_reco.integration_providers
SET status = 'active',
    name = 'ЮKassa',
    description = 'Приём платежей через ЮKassa: HTTP-уведомления об оплатах и возвратах + чек по платежу',
    webhook_enabled = true
WHERE slug = 'yookassa';