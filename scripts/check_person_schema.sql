-- Vérifier l'état de Person et PersonPermission
SELECT
    'Person columns' as info,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_person'
ORDER BY ordinal_position;

SELECT
    'PersonPermission columns' as info,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_personpermission'
ORDER BY ordinal_position;

-- Vérifier s'il y a des données dans PersonPermission
SELECT COUNT(*) as permission_count FROM gift_manager_personpermission;

-- Vérifier les clés primaires
SELECT
    tc.table_name,
    kcu.column_name,
    c.data_type
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.columns c
    ON c.table_name = tc.table_name
    AND c.column_name = kcu.column_name
WHERE tc.table_schema = 'public'
    AND tc.table_name IN ('gift_manager_person', 'gift_manager_personpermission')
    AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY tc.table_name;
