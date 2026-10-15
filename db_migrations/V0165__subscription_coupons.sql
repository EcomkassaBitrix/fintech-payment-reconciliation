CREATE TABLE t_p83864310_fintech_payment_reco.subscription_coupons (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    tariff_id INTEGER NOT NULL REFERENCES t_p83864310_fintech_payment_reco.tariffs(id),
    period VARCHAR(10) NOT NULL DEFAULT 'month',
    usage_type VARCHAR(10) NOT NULL DEFAULT 'single',
    valid_until DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX subscription_coupons_code_uq ON t_p83864310_fintech_payment_reco.subscription_coupons (UPPER(code));

CREATE TABLE t_p83864310_fintech_payment_reco.subscription_coupon_activations (
    id SERIAL PRIMARY KEY,
    coupon_id INTEGER NOT NULL REFERENCES t_p83864310_fintech_payment_reco.subscription_coupons(id),
    company_id INTEGER NOT NULL REFERENCES t_p83864310_fintech_payment_reco.companies(id),
    user_id INTEGER,
    payment_id INTEGER,
    period_end TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX subscription_coupon_activations_uq ON t_p83864310_fintech_payment_reco.subscription_coupon_activations (coupon_id, company_id);