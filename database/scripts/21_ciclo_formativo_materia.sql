-- ============================================================
-- VidaSYS-IBV
-- Script 21: Ciclo formativo de cada materia
-- No representa el orden de impartición.
-- ============================================================
BEGIN;
ALTER TABLE materia
ADD COLUMN IF NOT EXISTS numero_ciclo_formativo SMALLINT;
-- Ciclo I
UPDATE materia
SET numero_ciclo_formativo = 1
WHERE codigo_materia IN (
        'IBV-DOC1',
        'IBV-PEDC',
        'IBV-TEOP',
        'IBV-AT1',
        'IBV-CTH',
        'IBV-LID'
    );
-- Ciclo II
UPDATE materia
SET numero_ciclo_formativo = 2
WHERE codigo_materia IN (
        'IBV-HERJ',
        'IBV-DOC2',
        'IBV-AT2',
        'IBV-MEV',
        'IBV-HER',
        'IBV-HIC'
    );
-- Ciclo III
UPDATE materia
SET numero_ciclo_formativo = 3
WHERE codigo_materia IN (
        'IBV-NT1',
        'IBV-TIP',
        'IBV-ETR',
        'IBV-DESP',
        'IBV-DOC3',
        'IBV-CONP'
    );
-- Ciclo IV
UPDATE materia
SET numero_ciclo_formativo = 4
WHERE codigo_materia IN (
        'IBV-MIS',
        'IBV-ORH',
        'IBV-CRI',
        'IBV-DOC4',
        'IBV-NT2',
        'IBV-ROM'
    );
-- Impedir materias sin ciclo formativo
ALTER TABLE materia
ALTER COLUMN numero_ciclo_formativo
SET NOT NULL;
-- Aceptar únicamente los cuatro ciclos de la carrera
ALTER TABLE materia DROP CONSTRAINT IF EXISTS ck_materia_ciclo_formativo;
ALTER TABLE materia
ADD CONSTRAINT ck_materia_ciclo_formativo CHECK (
        numero_ciclo_formativo BETWEEN 1 AND 4
    );
COMMIT;
-- Comprobación: deben aparecer seis materias por ciclo
SELECT numero_ciclo_formativo,
    COUNT(*) AS cantidad_materias
FROM materia
GROUP BY numero_ciclo_formativo
ORDER BY numero_ciclo_formativo;
-- Listado detallado
SELECT numero_ciclo_formativo,
    codigo_materia,
    nombre
FROM materia
ORDER BY numero_ciclo_formativo,
    nombre;
