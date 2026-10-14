ALTER TABLE t_p83864310_fintech_payment_reco.platform_settings
    ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50) NULL;
