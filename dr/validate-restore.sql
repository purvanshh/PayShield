-- PostgreSQL restore validation queries

BEGIN;

SELECT '=== Backup Restore Validation ===' AS validation_start;

-- Count records in critical tables
SELECT 'transactions' AS table_name, COUNT(*) AS row_count FROM transactions
UNION ALL
SELECT 'rules', COUNT(*) FROM rules
UNION ALL
SELECT 'models', COUNT(*) FROM models
UNION ALL
SELECT 'investigations', COUNT(*) FROM investigations
UNION ALL
SELECT 'feedback', COUNT(*) FROM feedback;

-- Check table completeness
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- Check for NULL primary keys
SELECT 'transactions: NULL IDs' AS check_name, COUNT(*) AS issue_count FROM transactions WHERE id IS NULL
UNION ALL
SELECT 'rules: NULL IDs', COUNT(*) FROM rules WHERE id IS NULL
UNION ALL
SELECT 'models: NULL IDs', COUNT(*) FROM models WHERE id IS NULL;

-- Foreign key integrity checks
SELECT 'orphan transaction rules' AS check_name, COUNT(*) AS issue_count
FROM transactions t
LEFT JOIN rules r ON t.rule_id = r.id
WHERE r.id IS NULL;

-- Check recent data exists
SELECT 'recent_transactions' AS check_name, MAX(created_at) AS last_record FROM transactions
UNION ALL
SELECT 'recent_rules', MAX(created_at) FROM rules;

-- Schema version check
SELECT 'schema_version' AS check_name, version_num FROM alembic_version;

COMMIT;
