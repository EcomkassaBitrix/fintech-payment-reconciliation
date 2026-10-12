ALTER TABLE t_p83864310_fintech_payment_reco.platform_crm_settings
    ADD COLUMN IF NOT EXISTS channel_field VARCHAR(150) NULL,
    ADD COLUMN IF NOT EXISTS channel_field_type VARCHAR(50) NULL;
ALTER TABLE t_p83864310_fintech_payment_reco.platform_crm_events
    ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;