ALTER TABLE t_p83864310_fintech_payment_reco.platform_payment_providers
    ADD COLUMN IF NOT EXISTS terminal_key VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS terminal_password TEXT NULL,
    ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb;

INSERT INTO t_p83864310_fintech_payment_reco.platform_payment_providers (slug, name, description, auth_type, sort_order)
VALUES ('tbank', 'Т‑Банк', 'Оплата подписки картой с сохранением карты и автопродлением (рекуррентные платежи интернет-эквайринга).', 'terminal', 2)
ON CONFLICT (slug) DO NOTHING;

CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.subscription_cards (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES t_p83864310_fintech_payment_reco.companies(id),
    provider_slug VARCHAR(50) NOT NULL,
    rebill_id VARCHAR(100) NOT NULL,
    card_id VARCHAR(100) NULL,
    pan VARCHAR(30) NULL,
    exp_date VARCHAR(10) NULL,
    customer_key VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by INTEGER NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subscription_cards_company ON t_p83864310_fintech_payment_reco.subscription_cards (company_id, is_active);

ALTER TABLE t_p83864310_fintech_payment_reco.subscriptions
    ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS renew_period VARCHAR(10) NOT NULL DEFAULT 'month',
    ADD COLUMN IF NOT EXISTS card_id INTEGER NULL;

ALTER TABLE t_p83864310_fintech_payment_reco.subscription_payments
    ADD COLUMN IF NOT EXISTS provider_slug VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS provider_payment_id VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS order_id VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS payment_url TEXT NULL,
    ADD COLUMN IF NOT EXISTS keep_data JSONB NULL,
    ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS error_message TEXT NULL,
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_subscription_payments_provider ON t_p83864310_fintech_payment_reco.subscription_payments (provider_slug, provider_payment_id);
