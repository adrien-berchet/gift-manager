-- Script SQL pour nettoyer les duplicatas manuellement
-- À exécuter AVANT d'appliquer les migrations qui convertissent les UUID en primary_key

-- 1. Identifier les duplicatas Person
SELECT person_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_person
GROUP BY person_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 2. Identifier les duplicatas PersonGroup
SELECT group_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_persongroup
GROUP BY group_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 3. Identifier les duplicatas GiftTag
SELECT tag_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_gifttag
GROUP BY tag_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 4. Identifier les duplicatas Gift
SELECT gift_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_gift
GROUP BY gift_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 5. Identifier les duplicatas Event
SELECT event_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_event
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY count DESC;

-- 6. Identifier les duplicatas Relation
SELECT relation_id, COUNT(*) as count,
       STRING_AGG(id::text, ', ') as ids
FROM gift_manager_relation
GROUP BY relation_id
HAVING COUNT(*) > 1
ORDER BY count DESC;
