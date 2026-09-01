# Scrint — Scrum Execution and Process Analytics Platform

Scrint is an open-source platform that extends [Taiga](https://github.com/taigaio) with specialized modules for Scrum execution, collaborative estimation, sprint coordination, impediment management, and process analytics. It is designed to support Scrum adoption in both educational and professional contexts.

## Overview

Existing project management platforms provide limited native support for Scrum-specific activities. Scrint bridges this gap by adding the following capabilities on top of Taiga's project management infrastructure:

- **Planning Poker** — collaborative effort estimation with automatic consensus validation
- **Sprint capacity validation** — real-time workload assessment against team velocity and focus factor
- **Digital Daily Scrum** — structured reporting of completed work, planned tasks, and impediments
- **Impediment management** — identification, escalation, and resolution tracking notified via Server-Sent Events
- **Sprint Review and Retrospective** — structured feedback collection and improvement action tracking
- **Process analytics** — automated generation of velocity, burndown charts, focus factor, and participation metrics
- **Data export** — CSV and Excel export of all process data for external analysis

## Repository Structure

```
scrint/
├── backend/
│   └── sprint_execution/      # Django REST Framework extension modules
│       ├── models.py           # PlanningSession, Participant, Estimation, Impediment
│       ├── views.py            # API endpoints
│       ├── serializers.py      # DRF serializers with Fibonacci validation
│       ├── urls.py             # URL routing
│       ├── permissions.py      # Role-based access control
│       ├── utils.py            # Capacity and focus factor computation
│       ├── sse.py              # Server-Sent Events for real-time sync
│       └── migrations/         # Database migrations
└── frontend/
    └── modules/
        ├── planning-poker/     # CoffeeScript + Jade estimation UI
        ├── daily-scrum/        # Daily Scrum reporting interface
        ├── lightboxes/         # Modal dialogs
        └── project-navigation/ # Navigation component (TypeScript)
```

## Requirements

| Component | Version |
|---|---|
| Python | 3.8 |
| Node.js | 18 |
| PostgreSQL | 13+ |
| RabbitMQ | 3.8+ |
| Redis | 6+ |

Operating system: Linux (Ubuntu 20.04 recommended)

## Installation

Scrint extends the full Taiga stack. Follow these steps:

### 1. Clone the repository

```bash
git clone https://github.com/Esmeraldacc97/scrint.git
cd scrint
```

### 2. Backend setup

```bash
cd taiga-back
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata initial_project_templates
python manage.py runserver
```

### 3. Frontend setup

```bash
cd taiga-front
npm install
cp conf/conf.example.json conf/conf.json   # edit API URL if needed
npx gulp
```

### 4. Events service setup

```bash
cd taiga-events
npm install
cp config.example.json config.json         # edit AMQP connection settings
node index.js
```

## Usage

Once deployed, navigate to `http://localhost:9001` (or your configured host). Create a project in Taiga and access the Scrint modules through the project sidebar:

- **Planning Poker** — available to Scrum Masters for creating estimation sessions
- **Daily Scrum** — accessible to all team members for daily progress reporting
- **Sprint Dashboard** — shows real-time velocity, burndown, and impediment status
- **Reports** — exportable analytics at sprint and project level

## Empirical Evaluation

Scrint was evaluated in two contexts:

- **Academic**: 35 undergraduate engineering students (Computer and Mechanical Engineering, IPN Mexico). Scrint users showed ~40% improvement in Scrum comprehension, ~75% knowledge retention at follow-up, and required ~60% less time to reach operational Scrum competence compared to conventional tools.
- **Professional**: 15 software developers at the *Poder Judicial de la Ciudad de México*. Scrint reduced mid-sprint scope injection by 35%, cut retrospective documentation overhead by 42%, and achieved a System Usability Scale score of 88.5 (Excellent) vs. 64.2 for commercial alternatives.

## License

Scrint is distributed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**, consistent with the license of the Taiga components it extends. See [LICENSE](LICENSE) for details.

## Citation

If you use Scrint in your research, please cite:

> Chavarria Cabello EY, Orantes Jiménez SD, Vilches-Blázquez LM. Scrint: An Extensible Platform for Scrum Execution, Team Coordination and Process Analytics. *SoftwareX*. 2026. https://github.com/Esmeraldacc97/scrint

## Contact

For questions or support, contact: echavarriac2023@cic.ipn.mx

Centro de Investigación en Computación (CIC), Instituto Politécnico Nacional, Mexico City, Mexico.
