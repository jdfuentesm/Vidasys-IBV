# VidaSys-IBV

> Sistema de Gestión Financiera y Académica para el Instituto Bíblico Vida (El Salvador)

[![Estado](https://img.shields.io/badge/estado-en%20desarrollo-yellow)]()
[![Django](https://img.shields.io/badge/Django-6.1-green)]()
[![Python](https://img.shields.io/badge/Python-3.14-blue)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-blue)]()
[![Licencia](https://img.shields.io/badge/licencia-MIT-yellow)]()

## 📖 Descripción

VidaSys-IBV es un sistema de gestión financiera y académica diseñado para el **Instituto Bíblico Vida** (dependencia de Ministerios Vida, San Bartolo, El Salvador). El sistema automatiza los procesos administrativos del instituto, incluyendo:

- **Gestión académica:** matrículas, cursos, sesiones de clase, asistencia y calificaciones.
- **Gestión financiera:** obligaciones (matrícula, mensualidad, graduación), pagos, becas y convenios.
- **Control de acceso:** roles diferenciados (Administrador, Secretaría, Maestro, Dirección, Pastor Principal, Estudiante).
- **Portal estudiantil:** consulta de información académica y financiera.
- **Reportes:** indicadores institucionales para la toma de decisiones.
- **Auditoría:** trazabilidad de operaciones críticas.

Este proyecto se desarrolla como parte del **Servicio Social** para optar al grado de **Técnico Superior Universitario en Desarrollo de Software de Código Abierto**.

## 🎯 Objetivo

Proveer al Instituto Bíblico Vida de una herramienta tecnológica que:

1. **Simplifique** la operación diaria de Secretaría y Dirección.
2. **Automatice** el cálculo de solvencia estudiantil.
3. **Reduzca** errores en la gestión financiera.
4. **Mejore** la experiencia de usuarios con un diseño **simple, claro y accesible** (regla UX-01: máximo 3 clics por tarea).

## 🛠️ Stack Tecnológico

| Componente | Tecnología |
|---|---|
| **Lenguaje** | Python 3.14 |
| **Framework Backend** | Django 6.1 |
| **Base de datos** | PostgreSQL 18 |
| **Frontend** | HTML5, CSS3, JavaScript |
| **Framework CSS** | Bootstrap 5 |
| **Interactividad** | HTMX |
| **Administración BD** | pgAdmin 4 |
| **ORM** | Django ORM |
| **Control de versiones** | Git + GitHub |
| **Editor** | Visual Studio Code |

> **Nota:** Todo el stack está basado en **tecnologías de código abierto**.

## 🚀 Estado del proyecto

El proyecto se encuentra en **fase de desarrollo activo**. Avance actual:

- [x] Análisis de requerimientos (HU-001 a HU-033)
- [x] Diseño de base de datos (25 tablas)
- [x] Modelo Entidad-Relación (ERD)
- [x] Diccionario de datos
- [x] Diagrama de casos de uso
- [x] Custom User Model en Django
- [ ] Autenticación y login personalizado
- [ ] Módulo académico
- [ ] Módulo financiero
- [ ] Portal estudiantil
- [ ] Reportes
- [ ] Auditoría
- [ ] Pruebas con usuarios
- [ ] Despliegue en producción

## 📁 Estructura del proyecto

```
Vidasys-IBV/
├── config/              # Configuración global del proyecto Django
├── core/                # Usuarios, roles, autenticación
├── academico/           # Estudiantes, cursos, matrículas, asistencia
├── financiero/          # Obligaciones, pagos, becas, convenios
├── reportes/            # Consultas y dashboards
├── docs/                # Documentación del proyecto
│   ├── bitacoras/       # Bitácoras semanales
│   ├── diseno/          # ERD, casos de uso, diccionario
│   ├── backlog/         # Backlog en Excel
│   └── manuales/        # Manuales de usuario/técnico
├── venv/                # Entorno virtual (NO se sube a Git)
├── manage.py            # Comandos de Django
├── requirements.txt     # Dependencias del proyecto
├── .env                 # Variables de entorno (NO se sube a Git)
├── .env.example         # Plantilla de variables
├── .gitignore           # Archivos ignorados por Git
└── README.md            # Este archivo
```

## ⚙️ Instalación y uso

### Requisitos previos

- **Python 3.11+** ([descargar](https://www.python.org/downloads/))
- **PostgreSQL 15+** ([descargar](https://www.postgresql.org/download/))
- **Git** ([descargar](https://git-scm.com/downloads))

### Pasos de instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/jdfuentesm/vidasys-IBV.git
cd vidasys-IBV

# 2. Crear el entorno virtual
python -m venv venv

# 3. Activar el entorno virtual
# En Windows:
venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Copiar el archivo de variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 6. Crear la base de datos en PostgreSQL
# (usar pgAdmin o psql para crear "gestion_ibv")

# 7. Aplicar migraciones
python manage.py migrate

# 8. Crear superusuario
python manage.py createsuperuser

# 9. Ejecutar el servidor
python manage.py runserver
```

Abrir el navegador en: **http://127.0.0.1:8000/**

## 🎨 Identidad visual

El sistema usa la paleta institucional del IBV, extraída del logo oficial:

| Color | Hex | Uso |
|---|---|---|
| 🔵 Azul marino | `#1E3A5F` | Color primario, navegación |
| 🔴 Rojo | `#DC2626` | Acento, acciones críticas |
| 🟢 Verde | `#16A34A` | Éxito, solvente |
| 🟡 Dorado | `#F59E0B` | Advertencias |
| ⚪ Blanco | `#FFFFFF` | Fondos |

## 📐 Reglas UX

El sistema sigue 7 reglas de experiencia de usuario vinculantes:

1. **UX-01:** toda tarea frecuente en **≤ 3 clics** desde el dashboard.
2. **UX-02:** una acción principal por pantalla.
3. **UX-03:** mensajes de error en lenguaje humano.
4. **UX-04:** botón de ayuda contextual "?" en pantallas complejas.
5. **UX-05:** atajos de teclado (Ctrl+G para guardar, Esc para cancelar).
6. **UX-06:** confirmación visual tras cada acción exitosa.
7. **UX-07:** cero scroll horizontal en móvil.

## 👥 Roles del sistema

| Rol | Acceso |
|---|---|
| **ADMINISTRADOR** | Acceso total al sistema |
| **SECRETARIA** | Gestión académica y financiera operativa |
| **DIRECTORA** | Supervisión, autorizaciones, reportes |
| **MAESTRO** | Registro de asistencia y calificaciones |
| **PASTOR_PRINCIPAL** | Consulta de indicadores institucionales |
| **ESTUDIANTE** | Consulta de información propia (con restricción de solvencia) |

## 📚 Documentación

- [Casos de uso](docs/diseno/)
- [Diccionario de datos](docs/diseno/)
- [Modelo ERD](docs/diseno/)
- [Backlog del proyecto](docs/backlog/)
- [Bitácoras semanales](docs/bitacoras/)

## 🤝 Contribuciones

Este proyecto es parte de un servicio social académico. Las contribuciones son bienvenidas a través de **Issues** y **Pull Requests** siguiendo las normas del repositorio.

## 📄 Licencia

Este proyecto está licenciado bajo la **Licencia MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

## ✍️ Autor

**José David Fuentes**
Estudiante de Técnico Superior Universitario en Desarrollo de Software de Código Abierto

- GitHub: [@jdfuentesm](https://github.com/jdfuentesm)

## 🏛️ Institución

**Instituto Bíblico Vida**
Dependencia de Ministerios Vida — San Bartolo, El Salvador

## 🙏 Agradecimientos

- A la **Dirección del Instituto Bíblico Vida** por permitir el desarrollo de este sistema.
- A la **Secretaría del IBV** por su colaboración en la definición de requerimientos.
- A los **docentes del TSU** por su acompañamiento académico.

---

**Última actualización:** Octubre 2026

```hecho
