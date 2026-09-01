# Scrint

Extensión de la plataforma open source **Taiga** (MPL 2.0 / AGPL en taiga-front-next),
adaptada para docencia de Scrum.

## Módulos añadidos
- `taiga-back/planning_poker/` – sesiones de Planning Poker
- `taiga-back/sprint_execution/` – ejecución de sprint, selección de tareas, SSE
- `taiga-back/scripts_python/` – carga de datos de prueba (`manage.py shell`)
- `UserStory.in_sprint_backlog` + validaciones en `clean()`
- `taiga-front`: módulos `planningpoker`, `dailyscrum`, `sprintreview`, `sprintretrospective`
- Rebrand visible Taiga → Scrint

## Puesta en marcha (otro equipo)
Requisitos: Python 3.8, Node 18, PostgreSQL, RabbitMQ, Redis. Ver commits base en `UPSTREAM.md`.

### Backend
    cd taiga-back
    python3.8 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    cp settings/config.py.dev.example settings/local.py   # editar SECRET_KEY, EVENTS, etc.
    export TAIGA_DB_PASSWORD=...
    python manage.py migrate
    python manage.py runserver

### Frontend
    cd taiga-front
    npm install
    cp conf/conf.example.json dist/conf.json   # editar api / eventsUrl
    npx gulp deploy

### Events
    cd taiga-events
    npm install
    cp config.example.json config.json   # url amqp + secret (== SECRET_KEY del back)
    node index.coffee

## Notas
- `settings/common.py` tiene `DEBUG=True` y `PAGE_SIZE=3` a propósito (entorno de trabajo).
- `scripts_python/` crea usuarios de prueba con contraseñas triviales: solo desarrollo.
