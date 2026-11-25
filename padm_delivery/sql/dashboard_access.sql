USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

-- One-time seed: who can open the PADM dashboard (checked against CURRENT_USER() in streamlit_app.py).
-- Run once only — do not re-run (re-running re-inserts existing rows; use UPDATE to revoke access instead).
INSERT INTO DM_PADM_DASHBOARD_ACCESS (EMAIL) VALUES
    ('MADHUPRIYA.ALLAM@CREDITONE.COM'),
    ('JENNIFER.MASON@CREDITONE.COM'),
    ('MISHA.OBERG@CREDITONE.COM'),
    ('JESSICA.ANDERSON@CREDITONE.COM'),
    ('NINA.NGUYEN@CREDITONE.COM'),
    ('BIANCA.BIN@CREDITONE.COM');

-- To add someone later:  INSERT INTO DM_PADM_DASHBOARD_ACCESS (EMAIL) VALUES ('new.person@creditone.com');
-- To remove someone:     UPDATE DM_PADM_DASHBOARD_ACCESS SET ACTIVE_FLAG = FALSE WHERE EMAIL = 'name@creditone.com';
