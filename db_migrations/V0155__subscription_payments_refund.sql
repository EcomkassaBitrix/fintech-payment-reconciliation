ALTER TABLE t_p83864310_fintech_payment_reco.subscription_payments
    ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS refunded_by INTEGER NULL,
    ADD COLUMN IF NOT EXISTS refund_amount NUMERIC(12,2) NULL;
CREATE INDEX IF NOT EXISTS idx_subscription_payments_created ON t_p83864310_fintech_payment_reco.subscription_payments (created_at DESC);
