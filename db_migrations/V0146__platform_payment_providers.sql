CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.platform_payment_providers (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    auth_type VARCHAR(20) NOT NULL DEFAULT 'oauth',
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    sort_order INTEGER NOT NULL DEFAULT 0,
    access_token TEXT NULL,
    shop_id VARCHAR(100) NULL,
    is_test BOOLEAN NOT NULL DEFAULT false,
    token_expires_at TIMESTAMP NULL,
    connected_at TIMESTAMP NULL,
    connected_by INTEGER NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO t_p83864310_fintech_payment_reco.platform_payment_providers (slug, name, description, auth_type, sort_order)
VALUES ('yookassa', 'ЮKassa', 'Приём оплаты подписок картой, СБП, SberPay и ЮMoney. Подключение через партнёрское приложение ЮKassa', 'oauth', 1)
ON CONFLICT (slug) DO NOTHING;