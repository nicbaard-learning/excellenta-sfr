# Shared Framework Repository (SFR) – Overview

## What is SFR?

The Shared Framework Repository (SFR) is a standalone compliance data service designed to centralize, normalize, and expose metadata about security, privacy, and risk frameworks. It provides:
- Canonical framework definitions (e.g., NIST, ISO, SOC2, GDPR, etc.)
- Canonical controls and cross-framework mappings
- Assessment objectives and evidence requirements
- Compensating controls and applicability metadata
- Jurisdiction and business model tagging

SFR is built for use in Third-Party Risk Management (TPRM), Governance/Risk/Compliance (GRC), and automated compliance tooling.

## What Information Does SFR Contain?

- **Frameworks**: Metadata for 100+ global frameworks, including code, name, category, jurisdiction, and business model relevance.
- **Controls**: Canonical SCF controls, with domain, description, and mapping to other frameworks.
- **Mappings**: Crosswalks between SCF controls and mapped controls in other frameworks (e.g., NIST, ISO, PCI-DSS).
- **Assessment Objectives**: Objective statements for each control, supporting audit and assessment workflows.
- **Evidence Artifacts**: Evidence request items linked to controls for audit readiness.
- **Compensating Controls**: Alternative controls for risk mitigation.
- **Jurisdictions**: Country/region tags for frameworks and controls.
- **Business Models**: Applicability rules for SaaS, IaaS, MSP, MSSP, etc.

All data is loaded from the canonical SCF workbook and reference seeders, and is normalized for API and MCP access.

## What Does SFR Do?

- **Centralizes** compliance framework data for easy access and integration.
- **Normalizes** cross-framework mappings for comparison, gap analysis, and deduplication.
- **Supports** automated recommendations based on jurisdiction, business model, and context.
- **Enables** GRC and TPRM workflows with rich metadata and evidence requirements.
- **Exposes** a modern REST API and Model Context Protocol (MCP) interface for integration with other tools.

## API Overview

SFR exposes a RESTful API for all major data types:

### Frameworks
- `GET /api/frameworks` – List all frameworks
- `GET /api/frameworks/{id}` – Framework detail
- `GET /api/frameworks/{id}/versions` – Version history
- `GET /api/frameworks/{id}/related` – Related frameworks
- `GET /api/frameworks/{id}/controls` – Controls for a framework

### Controls & Mappings
- `GET /api/controls/{id}` – Control detail
- `GET /api/controls/{id}/mappings` – Framework mappings
- `GET /api/controls/{id}/objectives` – Assessment objectives
- `GET /api/controls/{id}/evidence` – Evidence artifacts
- `GET /api/controls/{id}/compensating-controls` – Compensating controls

### Comparison & GRC
- `POST /api/compare/frameworks` – Full comparison (overlap + gaps)
- `POST /api/compare/intersection` – Common controls only
- `POST /api/compare/differences` – Framework-to-framework differences
- `POST /api/compare/common-controls` – Deduplicated common control set

### Recommendation & Reference
- `POST /api/recommend/frameworks` – Context-based framework recommendations
- `GET /api/jurisdictions` – List jurisdictions
- `GET /api/business-models` – List business models
- `GET /api/domains` – List SCF domains

All endpoints return JSON and are documented via OpenAPI at `/docs`.

## MCP (Model Context Protocol) Support

SFR is designed to be MCP-ready, exposing its business logic as callable MCP tools:
- **Tooling**: Each service (e.g., recommendation, comparison, mapping) is exposed as an MCP tool.
- **Integration**: External AI agents and automation platforms can call SFR’s MCP tools for compliance reasoning, recommendations, and data extraction.
- **Authentication**: Supports API key authentication for secure MCP and API access.
- **Extensibility**: New tools can be added for custom compliance workflows, evidence collection, or reporting.

## Example Use Cases

- **Vendor Assessment**: Automatically map a vendor’s controls to required frameworks for a given jurisdiction and business model.
- **GRC Automation**: Compare frameworks, identify gaps, and generate deduplicated control sets for audits.
- **AI Reasoning**: Use MCP tools to power AI agents that answer compliance questions, recommend frameworks, or generate evidence requests.

## Technology Stack
- Python 3.12+
- FastAPI (REST API)
- SQLAlchemy (ORM)
- Alembic (migrations)
- PostgreSQL (database)
- pandas/openpyxl (workbook import)
- Pydantic v2 (schema validation)

---

For more details, see the main README or API docs at `/docs` after starting the service.
