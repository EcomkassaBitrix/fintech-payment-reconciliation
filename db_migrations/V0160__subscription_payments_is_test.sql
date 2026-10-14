ALTER TABLE t_p83864310_fintech_payment_reco.subscription_payments
    ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false;
