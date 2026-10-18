CREATE INDEX IF NOT EXISTS idx_automation_jobs_processing
    ON t_p83864310_fintech_payment_reco.automation_jobs (locked_until)
    WHERE status = 'processing';