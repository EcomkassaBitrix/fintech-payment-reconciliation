ALTER TABLE t_p83864310_fintech_payment_reco.user_integrations
  ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMP NULL,
  ADD COLUMN IF NOT EXISTS hidden_prev_status VARCHAR(20) NULL;
ALTER TABLE t_p83864310_fintech_payment_reco.automation_scenarios
  ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMP NULL,
  ADD COLUMN IF NOT EXISTS hidden_prev_status VARCHAR(20) NULL;