ALTER TABLE t_p83864310_fintech_payment_reco.platform_crm_settings
    ADD COLUMN IF NOT EXISTS channel_map JSONB NOT NULL DEFAULT '{}'::jsonb;
