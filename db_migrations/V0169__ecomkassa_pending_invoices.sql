CREATE TABLE t_p83864310_fintech_payment_reco.ecomkassa_pending_invoices (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL,
    integration_id INTEGER NOT NULL REFERENCES t_p83864310_fintech_payment_reco.user_integrations(id),
    invoice_uuid VARCHAR(255) NOT NULL,
    external_id VARCHAR(255) NULL,
    status VARCHAR(20) NOT NULL,
    amount NUMERIC(15,2) NULL,
    invoice_updated_at TIMESTAMP NULL,
    raw_data JSONB NULL,
    origin VARCHAR(20) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (integration_id, invoice_uuid)
);
CREATE INDEX idx_ecom_pending_invoices_company ON t_p83864310_fintech_payment_reco.ecomkassa_pending_invoices (company_id, invoice_updated_at);