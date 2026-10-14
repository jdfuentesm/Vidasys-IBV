CREATE OR REPLACE VIEW vw_acceso_portal_estudiante AS
WITH base AS (
    SELECT
        e.id_estudiante,
        e.codigo_estudiante,
        e.nombres,
        e.apellidos,
        u.id_usuario,
        u.numero_usuario,
        u.correo_acceso,
        u.rol,
        u.estado_cuenta,
        CASE
            WHEN estudiante_esta_solvente(e.id_estudiante)
                THEN 'SOLVENTE'
            ELSE 'INSOLVENTE'
        END AS solvencia_actual
    FROM estudiante e
    LEFT JOIN usuario u
        ON u.id_usuario = e.id_usuario
)
SELECT
    id_estudiante,
    codigo_estudiante,
    nombres,
    apellidos,
    id_usuario,
    numero_usuario,
    correo_acceso,
    rol,
    estado_cuenta,
    solvencia_actual,

    CASE
        WHEN id_usuario IS NULL THEN FALSE
        WHEN rol <> 'ESTUDIANTE' THEN FALSE
        WHEN estado_cuenta <> 'ACTIVA' THEN FALSE
        WHEN solvencia_actual <> 'SOLVENTE' THEN FALSE
        ELSE TRUE
    END AS puede_consultar_academico,

    CASE
        WHEN id_usuario IS NULL
            THEN 'SIN_CUENTA'
        WHEN rol <> 'ESTUDIANTE'
            THEN 'ROL_NO_AUTORIZADO'
        WHEN estado_cuenta <> 'ACTIVA'
            THEN 'CUENTA_NO_ACTIVA'
        WHEN solvencia_actual <> 'SOLVENTE'
            THEN 'RESTRINGIDO_POR_INSOLVENCIA'
        ELSE 'PERMITIDO'
    END AS estado_acceso,

    CASE
        WHEN id_usuario IS NULL
            THEN 'El estudiante todavía no posee una cuenta de acceso.'
        WHEN rol <> 'ESTUDIANTE'
            THEN 'La cuenta no posee el rol estudiantil requerido.'
        WHEN estado_cuenta <> 'ACTIVA'
            THEN 'La cuenta se encuentra temporalmente inactiva.'
        WHEN solvencia_actual <> 'SOLVENTE'
            THEN 'La consulta académica está temporalmente restringida. Comuníquese con Secretaría para verificar su estado de cuenta.'
        ELSE
            'Acceso académico permitido.'
    END AS mensaje_acceso

FROM base;