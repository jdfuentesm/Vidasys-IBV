-- ============================================================
-- VidaSYS-IBV
-- Script 20: Catálogo académico inicial
-- Maestros y materias oficiales del Instituto Bíblico Vida
-- ============================================================
BEGIN;
-- ============================================================
-- 1. PLANTA DOCENTE
-- Este bloque puede ejecutarse nuevamente sin duplicar maestros.
-- ============================================================
INSERT INTO maestro (
        nombres,
        apellidos,
        pais,
        estado
    )
SELECT datos.nombres,
    datos.apellidos,
    'ESTADOS UNIDOS',
    'ACTIVO'
FROM (
        VALUES ('MARVIN', 'GONZALEZ'),
            ('MARITZA', 'GONZALEZ'),
            ('MIGUEL', 'GONZALEZ'),
            ('MIGUEL', 'MURILLO'),
            ('OSCAR', 'MARTINEZ'),
            ('JUAN CARLOS', 'AGUIRRE'),
            ('SAMUEL', 'MOZ'),
            ('RAUL', 'ZAMORA'),
            ('ANA', 'VASQUEZ'),
            ('XIOMARA', 'MORA')
    ) AS datos(nombres, apellidos)
WHERE NOT EXISTS (
        SELECT 1
        FROM maestro existente
        WHERE UPPER(TRIM(existente.nombres)) = datos.nombres
            AND UPPER(TRIM(existente.apellidos)) = datos.apellidos
    );
-- Uniformar los datos de todos los maestros
UPDATE maestro
SET nombres = UPPER(TRIM(nombres)),
    apellidos = UPPER(TRIM(apellidos)),
    pais = 'ESTADOS UNIDOS'
WHERE estado = 'ACTIVO';
-- ============================================================
-- 2. CATÁLOGO DE MATERIAS
-- Los códigos identifican la materia, no el orden de impartición.
-- ============================================================
INSERT INTO materia (codigo_materia, nombre, estado)
SELECT datos.codigo_materia,
    datos.nombre,
    'ACTIVA'
FROM (
        VALUES -- Materias correspondientes al ciclo I
            ('IBV-DOC1', 'DOCTRINA I'),
            ('IBV-PEDC', 'PEDAGOGIA CRISTIANA'),
            ('IBV-TEOP', 'TEOLOGIA PASTORAL'),
            ('IBV-AT1', 'ANTIGUO TESTAMENTO I'),
            ('IBV-CTH', 'COSTUMBRES Y TRADICIONES HEBREAS'),
            ('IBV-LID', 'LIDERAZGO'),
            -- Materias correspondientes al ciclo II
            ('IBV-HERJ', 'CRISTIANISMO Y SUS HEREJIAS'),
            ('IBV-DOC2', 'DOCTRINA II'),
            ('IBV-AT2', 'ANTIGUO TESTAMENTO II'),
            ('IBV-MEV', 'METODOLOGIA DE EVANGELISMO'),
            ('IBV-HER', 'HERMENEUTICA'),
            ('IBV-HIC', 'HISTORIA DE LA IGLESIA CRISTIANA'),
            -- Materias correspondientes al ciclo III
            ('IBV-NT1', 'NUEVO TESTAMENTO I'),
            ('IBV-TIP', 'TIPOLOGIA'),
            ('IBV-ETR', 'ETICA Y RELACIONES'),
            ('IBV-DESP', 'DISCIPLINAS ESPIRITUALES'),
            ('IBV-DOC3', 'DOCTRINA III'),
            ('IBV-CONP', 'CONSEJERIA PASTORAL'),
            -- Materias correspondientes al ciclo IV
            ('IBV-MIS', 'MISIONOLOGIA'),
            ('IBV-ORH', 'ORATORIA Y HOMILETICA'),
            ('IBV-CRI', 'CRISTOLOGIA'),
            ('IBV-DOC4', 'DOCTRINA IV'),
            ('IBV-NT2', 'NUEVO TESTAMENTO II'),
            ('IBV-ROM', 'ROMANOS')
    ) AS datos(codigo_materia, nombre)
WHERE NOT EXISTS (
        SELECT 1
        FROM materia existente
        WHERE UPPER(TRIM(existente.codigo_materia)) = datos.codigo_materia
            OR UPPER(TRIM(existente.nombre)) = datos.nombre
    );
-- Uniformar los registros del catálogo
UPDATE materia
SET codigo_materia = UPPER(TRIM(codigo_materia)),
    nombre = UPPER(TRIM(nombre)),
    estado = 'ACTIVA';
COMMIT;
-- Comprobación
SELECT id_maestro,
    nombres,
    apellidos,
    pais,
    estado
FROM maestro
ORDER BY apellidos,
    nombres;
