SELECT domain_code, code, name
FROM flowmeta.entity
WHERE domain_code IN ('devfactory','logistics','flowworld','eri','robots')
ORDER BY domain_code, code;
