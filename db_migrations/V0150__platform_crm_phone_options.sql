ALTER TABLE t_p83864310_fintech_payment_reco.platform_crm_settings
    ADD COLUMN IF NOT EXISTS phone_field_type VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS phone_to_contact BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS inn_field_type VARCHAR(50) NULL;