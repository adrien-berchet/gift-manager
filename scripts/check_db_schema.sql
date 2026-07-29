-- Script pour vérifier le schéma actuel de la base de données
-- Vérifie les types de colonnes pour les clés primaires et étrangères

-- 1. Vérifier Person et PersonPermission
SELECT
    'Person' as table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'gift_manager_person'
    AND column_name IN ('id', 'person_id')
ORDER BY ordinal_position;

SELECT
    'PersonPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_personpermission'
    AND column_name IN ('id', 'person_id')
ORDER BY ordinal_position;

-- 2. Vérifier PersonGroup et PersonGroupPermission
SELECT
    'PersonGroup' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_persongroup'
    AND column_name IN ('id', 'group_id')
ORDER BY ordinal_position;

SELECT
    'PersonGroupPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_persongrouppermission'
    AND column_name IN ('id', 'group_id')
ORDER BY ordinal_position;

-- 3. Vérifier Gift et GiftPermission
SELECT
    'Gift' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_gift'
    AND column_name IN ('id', 'gift_id')
ORDER BY ordinal_position;

SELECT
    'GiftPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_giftpermission'
    AND column_name IN ('id', 'gift_id')
ORDER BY ordinal_position;

-- 4. Vérifier GiftTag et GiftTagPermission
SELECT
    'GiftTag' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_gifttag'
    AND column_name IN ('id', 'tag_id')
ORDER BY ordinal_position;

SELECT
    'GiftTagPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_gifttagpermission'
    AND column_name IN ('id', 'gift_tag_id')
ORDER BY ordinal_position;

-- 5. Vérifier Event et EventPermission
SELECT
    'Event' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_event'
    AND column_name IN ('id', 'event_id')
ORDER BY ordinal_position;

SELECT
    'EventPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_eventpermission'
    AND column_name IN ('id', 'event_id')
ORDER BY ordinal_position;

-- 6. Vérifier Relation et RelationPermission
SELECT
    'Relation' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_relation'
    AND column_name IN ('id', 'relation_id', 'person_id', 'gift_id', 'event_id', 'group_id')
ORDER BY ordinal_position;

SELECT
    'RelationPermission' as table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'gift_manager_relationpermission'
    AND column_name IN ('id', 'relation_id')
ORDER BY ordinal_position;

-- 7. Vérifier les contraintes de clés primaires
SELECT
    tc.table_name,
    kcu.column_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
    AND tc.table_name LIKE 'gift_manager_%'
    AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY tc.table_name;
