UPDATE t_p83864310_fintech_payment_reco.automation_documents d
SET receipt_id = ekr.id, status = 'done', updated_at = NOW()
FROM t_p83864310_fintech_payment_reco.ecomkassa_receipts ekr
WHERE d.status = 'wait' AND d.receipt_id IS NULL
  AND ekr.integration_id = d.kassa_integration_id AND ekr.order_id = d.ecom_uuid
  AND ekr.status = 'done' AND ekr.removed_at IS NULL;

UPDATE t_p83864310_fintech_payment_reco.automation_jobs j
SET status = 'done', step = 'done', last_error = NULL, locked_until = NULL, updated_at = NOW()
WHERE j.status IN ('error', 'new', 'ready') AND j.step = 'action'
  AND EXISTS (SELECT 1 FROM t_p83864310_fintech_payment_reco.automation_documents d
              WHERE d.job_id = j.id AND d.status = 'done' AND d.ecom_uuid IS NOT NULL);