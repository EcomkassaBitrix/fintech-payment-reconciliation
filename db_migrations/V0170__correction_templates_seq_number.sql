UPDATE t_p83864310_fintech_payment_reco.automation_action_templates
SET correction_base_number = '{порядковый номер}'
WHERE receipt_type = 'correction' AND code IN ('correction', 'correction_copy');