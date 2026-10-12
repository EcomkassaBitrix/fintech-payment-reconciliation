ALTER TABLE t_p83864310_fintech_payment_reco.companies
    ADD COLUMN IF NOT EXISTS support_access_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS support_access_until TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS support_access_granted_by INTEGER NULL,
    ADD COLUMN IF NOT EXISTS support_access_granted_at TIMESTAMP NULL;

CREATE TABLE IF NOT EXISTS t_p83864310_fintech_payment_reco.support_access_log (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,
    user_id INTEGER NULL,
    action VARCHAR(20) NOT NULL,
    details TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_support_access_log_company ON t_p83864310_fintech_payment_reco.support_access_log (company_id, created_at DESC);