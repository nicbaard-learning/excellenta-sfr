# SFR – Shared Framework Repository

A standalone compliance repository service that stores framework metadata, canonical controls, cross-framework mappings, assessment objectives, evidence request items, compensating controls, and applicability metadata.

Supports **TPRM** (vendor assessment) and **GRC** (framework comparison) use cases.

## Architecture

```
sfr/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Pydantic settings
│   ├── database.py          # SQLAlchemy engine & session
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── framework.py     # Framework, FrameworkVersion
│   │   ├── control.py       # Domain, Principle, Control
│   │   ├── mapping.py       # ControlMapping, AuthoritativeSource
│   │   ├── assessment.py    # AssessmentObjective
│   │   ├── evidence.py      # EvidenceArtifact
│   │   ├── compensating.py  # CompensatingControlLink
│   │   ├── jurisdiction.py  # Jurisdiction, FrameworkJurisdiction
│   │   ├── business_model.py# BusinessModel
│   │   ├── applicability.py # FrameworkApplicabilityRule
│   │   └── import_run.py    # ImportRun
│   ├── schemas/             # Pydantic request/response schemas
│   ├── api/                 # FastAPI route handlers
│   ├── services/            # Business logic service layer
│   ├── importers/           # Workbook import pipeline
│   │   └── load_scf.py      # CLI import orchestrator
│   └── seed/                # Reference data seeders
├── alembic/                 # Database migrations
├── alembic.ini
├── pyproject.toml
├── requirements.txt
└── .env
```

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL 15+

### Install dependencies

```bash
pip install -r requirements.txt
```

### Database setup

```bash
# Create the database
createdb sfr

# Run migrations
alembic upgrade head

# Or let the app auto-create tables (dev mode)
# The app will call Base.metadata.create_all() on startup
```

### Configuration

Copy `.env` and adjust as needed:

```bash
DATABASE_URL=postgresql://sfr:sfr@localhost:5432/sfr
```

## Running the service

```bash
# Start the API server
uvicorn app.main:app --reload --port 8000

# Open API docs at http://localhost:8000/docs
```

## Loading the SCF workbook

Place the workbook file in the project root, then run:

```bash
python -m app.importers.load_scf --file secure-controls-framework-scf-2026-1.xlsx
```

The importer is designed to be safely re-runnable (skips existing records on conflict).

## Seeding reference data

```bash
python -m app.seed.run_seeds
```

This populates:
- **Jurisdictions**: 60+ countries/regions (EU, NA, APAC, LATAM, MEA)
- **Business models**: 35+ TPRM vendor categories (SaaS, IaaS, MSP, MSSP, etc.)

## API Endpoints

### Framework browsing
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/frameworks` | List all frameworks |
| GET | `/api/frameworks/{id}` | Framework detail |
| GET | `/api/frameworks/{id}/versions` | Version history |
| GET | `/api/frameworks/{id}/related` | Related frameworks |
| GET | `/api/frameworks/{id}/controls` | Controls for framework |

### Control and mapping access
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/controls/{id}` | Control detail |
| GET | `/api/controls/{id}/mappings` | Framework mappings |
| GET | `/api/controls/{id}/objectives` | Assessment objectives |
| GET | `/api/controls/{id}/evidence` | Evidence artifacts |
| GET | `/api/controls/{id}/compensating-controls` | Compensating controls |

### Comparison & GRC
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/compare/frameworks` | Full comparison (overlap + gaps) |
| POST | `/api/compare/intersection` | Common controls only |
| POST | `/api/compare/differences` | Framework-to-framework differences |
| POST | `/api/compare/common-controls` | Deduplicated common control set |

### Recommendation & Reference
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/recommend/frameworks` | Context-based framework recommendations |
| GET | `/api/jurisdictions` | List jurisdictions |
| GET | `/api/business-models` | List business models |
| GET | `/api/domains` | List SCF domains |

## MCP Readiness

The service layer (`app/services/`) contains all business logic and can be directly wrapped as MCP tools. Each service is instantiated with a database session, making it straightforward to expose methods as callable tools via the MCP protocol.

## Technology

- **Python 3.12+**
- **FastAPI** – REST API framework
- **SQLAlchemy 2.0** – ORM with modern mapped_column syntax
- **Alembic** – Database migrations
- **PostgreSQL** – Primary database
- **pandas / openpyxl** – Excel workbook import
- **Pydantic v2** – Schema validation
