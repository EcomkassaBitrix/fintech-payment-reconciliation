UPDATE t_p83864310_fintech_payment_reco.automation_action_templates
SET correction_date_source = 'client', correction_base_date = NULL
WHERE receipt_type = 'correction' AND code IN ('correction', 'correction_copy');