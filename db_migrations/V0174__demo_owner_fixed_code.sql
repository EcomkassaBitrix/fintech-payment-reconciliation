UPDATE t_p83864310_fintech_payment_reco.app_users
SET fixed_login_code_hash = encode(sha256(convert_to('79991234567:123456', 'UTF8')), 'hex'), updated_at = NOW()
WHERE phone = '79991234567';