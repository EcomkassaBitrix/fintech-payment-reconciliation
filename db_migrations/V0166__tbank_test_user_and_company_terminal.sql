ALTER TABLE t_p83864310_fintech_payment_reco.companies
    ADD COLUMN IF NOT EXISTS test_terminal_key VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS test_terminal_password VARCHAR(200) NULL,
    ADD COLUMN IF NOT EXISTS test_terminal_updated_at TIMESTAMP NULL;

ALTER TABLE t_p83864310_fintech_payment_reco.app_users
    ADD COLUMN IF NOT EXISTS fixed_login_code_hash VARCHAR(64) NULL;

INSERT INTO t_p83864310_fintech_payment_reco.app_users (phone, full_name, status, fixed_login_code_hash)
SELECT '79999999999', 'Тестовый пользователь Т-Банка', 'active',
       encode(sha256(convert_to('79999999999:123456', 'UTF8')), 'hex')
WHERE NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.app_users WHERE phone = '79999999999');

UPDATE t_p83864310_fintech_payment_reco.app_users
SET fixed_login_code_hash = encode(sha256(convert_to('79999999999:123456', 'UTF8')), 'hex'), status = 'active'
WHERE phone = '79999999999';

INSERT INTO t_p83864310_fintech_payment_reco.company_users (company_id, user_id, role_id, status, joined_at, created_at, updated_at)
SELECT 4, u.id, 2, 'active', NOW(), NOW(), NOW()
FROM t_p83864310_fintech_payment_reco.app_users u
WHERE u.phone = '79999999999'
  AND NOT EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.company_users cu WHERE cu.company_id = 4 AND cu.user_id = u.id);