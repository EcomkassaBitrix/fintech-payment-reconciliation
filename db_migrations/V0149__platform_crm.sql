CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.platform_crm_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    provider VARCHAR(30) NOT NULL DEFAULT 'bitrix24',
    webhook_url TEXT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT false,
    entity VARCHAR(10) NOT NULL DEFAULT 'deal',
    stage_id VARCHAR(100) NULL,
    phone_field VARCHAR(150) NOT NULL DEFAULT 'contact.PHONE',
    inn_field VARCHAR(150) NOT NULL DEFAULT 'requisite',
    title_template VARCHAR(255) NOT NULL DEFAULT 'Регистрация в Сверке: {name}',
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by INTEGER NULL
);
INSERT INTO t_p83864310_fintech_payment_reco.platform_crm_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.platform_crm_events (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(30) NOT NULL,
    user_id INTEGER NULL,
    company_id INTEGER NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT NULL,
    result JSONB NULL,
    next_attempt_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_platform_crm_events_status ON t_p83864310_fintech_payment_reco.platform_crm_events (status, next_attempt_at);

CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.platform_crm_links (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,
    object_id INTEGER NOT NULL,
    crm_contact_id VARCHAR(30) NULL,
    crm_entity VARCHAR(10) NULL,
    crm_entity_id VARCHAR(30) NULL,
    crm_company_id VARCHAR(30) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (object_type, object_id)
);