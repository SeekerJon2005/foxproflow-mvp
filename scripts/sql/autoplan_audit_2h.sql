-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\autoplan_audit_2h.sql
-- FoxProFlow — распределение решений автоплана за последние 2 часа

SELECT decision, count(*)
FROM public.autoplan_audit
WHERE ts > now() - interval '2 hours'
GROUP BY 1
ORDER BY 1;
