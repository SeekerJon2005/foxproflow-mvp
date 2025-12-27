BEGIN;

-- 1. Политики DevFactory DevOrders (view/manage)
INSERT INTO sec.policies (
    policy_code,
    title,
    description,
    target_domain,
    effect,
    condition,
    is_active,
    decision,
    domain,
    action
)
VALUES
  (
    'devfactory_view_orders',
    'DevFactory: просмотр DevOrders',
    'Просмотр заказов DevFactory (DevOrders), без права изменения',
    'devfactory',           -- target_domain
    'allow',                -- effect
    '{}'::jsonb,            -- condition
    TRUE,                   -- is_active
    'allow',                -- decision
    'devfactory',           -- domain
    'view_orders'           -- action
  ),
  (
    'devfactory_manage_orders',
    'DevFactory: управление DevOrders',
    'Создание и изменение DevOrders, привязка tenant/billing/lead',
    'devfactory',           -- target_domain
    'allow',                -- effect
    '{}'::jsonb,            -- condition
    TRUE,                   -- is_active
    'allow',                -- decision
    'devfactory',           -- domain
    'manage_orders'         -- action
  )
ON CONFLICT (policy_code) DO UPDATE
  SET
    title         = EXCLUDED.title,
    description   = EXCLUDED.description,
    target_domain = EXCLUDED.target_domain,
    effect        = EXCLUDED.effect,
    condition     = EXCLUDED.condition,
    is_active     = EXCLUDED.is_active,
    decision      = EXCLUDED.decision,
    domain        = EXCLUDED.domain,
    action        = EXCLUDED.action;


-- 2. Привязка политик к роли architect
INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
  ('architect', 'devfactory_view_orders'),
  ('architect', 'devfactory_manage_orders')
ON CONFLICT (role_code, policy_code) DO NOTHING;

COMMIT;
