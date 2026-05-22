"""Domain, Principle, and Control models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Domain(Base):
    """SCF Domain – a top-level grouping of controls."""

    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="e.g. AC, AU, IA"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Domain name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    controls: Mapped[list["Control"]] = relationship("Control", back_populates="domain")

    def __repr__(self) -> str:
        return f"<Domain id={self.id} code={self.code!r}>"


class Principle(Base):
    """SCF Principle – a sub-grouping within a domain."""

    __tablename__ = "principles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("domains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Principle code e.g. AC-01, AU-02"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    domain: Mapped[Domain | None] = relationship("Domain")
    controls: Mapped[list["Control"]] = relationship("Control", back_populates="principle")

    def __repr__(self) -> str:
        return f"<Principle id={self.id} code={self.code!r}>"


class Control(Base):
    """A canonical SCF control – the core entity of the repository."""

    __tablename__ = "controls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scf_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="SCF # e.g. AC-01-01"
    )
    domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("domains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    principle_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("principles.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="Control title / name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    conformity_cadence: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Conformity Validation Cadence"
    )
    relative_weighting: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Relative Control Weighting"
    )
    relative_weight: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Relative weight integer value"
    )
    pptdf_applicability: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="PPTDF Applicability classification"
    )
    evidence_request_list_refs: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Evidence Request List (ERL) # references, comma-separated"
    )
    applicability_context: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Free-text applicability / context notes"
    )

    # Firm-size solution columns (from Possible Solutions & Considerations)
    solutions_micro_small: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Solutions for Micro-Small organizations"
    )
    solutions_small: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Solutions for Small organizations"
    )
    solutions_medium: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Solutions for Medium organizations"
    )
    solutions_large: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Solutions for Large organizations"
    )
    solutions_enterprise: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Solutions for Enterprise organizations"
    )

    # SCR-CMM Maturity level columns
    cmm_level_0: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 0 - Incomplete"
    )
    cmm_level_1: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 1 - Performed"
    )
    cmm_level_2: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 2 - Managed"
    )
    cmm_level_3: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 3 - Defined"
    )
    cmm_level_4: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 4 - Quantitatively Managed"
    )
    cmm_level_5: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="SCR-CMM Level 5 - Optimizing"
    )
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Workbook sheet name"
    )
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Row number in source sheet")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    domain: Mapped[Domain | None] = relationship("Domain", back_populates="controls")
    principle: Mapped[Principle | None] = relationship("Principle", back_populates="controls")
    mappings: Mapped[list["ControlMapping"]] = relationship(
        "ControlMapping", back_populates="control", cascade="all, delete-orphan"
    )
    assessment_objectives: Mapped[list["AssessmentObjective"]] = relationship(
        "AssessmentObjective", back_populates="control", cascade="all, delete-orphan"
    )
    evidence_artifacts: Mapped[list["EvidenceArtifact"]] = relationship(
        "EvidenceArtifact", back_populates="control", cascade="all, delete-orphan"
    )
    compensating_links: Mapped[list["CompensatingControlLink"]] = relationship(
        "CompensatingControlLink", back_populates="control", cascade="all, delete-orphan"
    )

    @property
    def principle_code(self) -> str | None:
        """Derive principle code from the related principle, if loaded."""
        return self.principle.code if self.principle else None

    def __repr__(self) -> str:
        return f"<Control id={self.id} scf_id={self.scf_id!r}>"
