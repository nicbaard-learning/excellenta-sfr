# PROJECT_DETAILS_TPRM

Excellenta SFR (Shared Framework Repository) is a standalone compliance data service that centralizes, normalizes, and exposes metadata about security, privacy, and risk frameworks. The system supports canonical framework definitions (e.g., NIST, ISO, SOC 2, GDPR), cross-framework control mappings, assessment objectives, evidence requirements, compensating controls, and jurisdiction/business-model applicability rules. It is built for use in Third-Party Risk Management (TPRM) vendor assessment workflows, Governance/Risk/Compliance (GRC) framework comparison, and automated compliance tooling — giving risk, procurement, and compliance teams a shared, API-driven repository of authoritative control data.

## Tech Stack and Requirements

- Backend: FastAPI (Python), SQLAlchemy 2.0 (ORM), Pydantic v2 (schema validation)
- Frontend: Jinja2 templates, Bootstrap 5, vanilla JavaScript, custom CSS
- Database: PostgreSQL 15+
- Data Import: pandas/openpyxl-based SCF workbook ingestion pipeline
- AI Integration: Model Context Protocol (MCP) server for AI-agent tool access; GitHub-backed SCF version tracking
- Security: CORS protection, DNS rebinding protection (MCP host/origin validation), structured error handling, environment-based secrets management
- Migrations: Alembic for database schema versioning

### Runtime and Setup Requirements

- Python 3.12+
- Virtual environment support (`venv` recommended)
- Git
- PostgreSQL 15+
- Environment variable configuration for:
  - `DATABASE_URL` – PostgreSQL connection string
  - `MCP_API_KEY` – API key for MCP tool access
  - Application title and version metadata
  - Allowed host/origin lists for MCP transport security

## Deployment

Deployment follows a Git-driven flow through GitHub and onto Render:

- Source control is maintained in Git (GitHub: `nicbaard-learning/excellenta-sfr`).
- Code changes are pushed to the GitHub repository as the central integration point.
- From GitHub, Render auto-deploys via connected repository and blueprint configuration (`render.yaml`).
- Render runs the production instance, using `gunicorn` with `uvicorn` workers to serve the FastAPI application.
- Database migrations (`alembic upgrade head`) run automatically as part of the startup command.
- Health checks are handled via the `/health` endpoint.
- The `Procfile` and `start.sh` provide alternative startup paths for different deployment targets.

This flow provides a controlled path from development to production, with versioned history in Git and operational deployment on Render.
