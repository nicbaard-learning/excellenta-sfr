"""SFR database models – import all so Alembic can discover them."""

from app.models.framework import Framework, FrameworkVersion  # noqa: F401
from app.models.control import Control, Domain, Principle  # noqa: F401
from app.models.mapping import ControlMapping, AuthoritativeSource  # noqa: F401
from app.models.assessment import AssessmentObjective  # noqa: F401
from app.models.evidence import EvidenceArtifact  # noqa: F401
from app.models.compensating import CompensatingControlLink  # noqa: F401
from app.models.jurisdiction import Jurisdiction, FrameworkJurisdiction  # noqa: F401
from app.models.business_model import BusinessModel  # noqa: F401
from app.models.applicability import FrameworkApplicabilityRule  # noqa: F401
from app.models.import_run import ImportRun  # noqa: F401
from app.models.threat import Threat, ThreatControlLink  # noqa: F401
from app.models.risk import Risk, RiskControlLink  # noqa: F401
