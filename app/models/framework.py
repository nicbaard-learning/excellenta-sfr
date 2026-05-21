"""Framework and framework-version models."""

from datetime import date, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Framework(Base):
    """A compliance framework (e.g. ISO 27001, NIST CSF, PCI DSS, SCF itself)."""

    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="Short code e.g. ISO27001, NIST-CSF"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Full framework name")
    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="e.g. international, industry, regulatory, internal"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_scf: Mapped[bool] = mapped_column(default=False, comment="True if this is the canonical SCF framework")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relationships
    versions: Mapped[list["FrameworkVersion"]] = relationship(
        "FrameworkVersion", back_populates="framework", cascade="all, delete-orphan"
    )
    jurisdictions: Mapped[list["FrameworkJurisdiction"]] = relationship(
        "FrameworkJurisdiction", back_populates="framework", cascade="all, delete-orphan"
    )
    applicability_rules: Mapped[list["FrameworkApplicabilityRule"]] = relationship(
        "FrameworkApplicabilityRule", back_populates="framework", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Framework id={self.id} code={self.code!r}>"


class FrameworkVersion(Base):
    """A specific versioned release of a framework."""

    __tablename__ = "framework_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_label: Mapped[str] = mapped_column(String(50), nullable=False, comment="e.g. 2022, 4.0, 3.2.1")
    release_date: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="active", comment="active, superseded, draft"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Workbook sheet name this version was imported from"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    framework: Mapped["Framework"] = relationship("Framework", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("framework_id", "version_label", name="uq_framework_version"),
    )

    def __repr__(self) -> str:
        return f"<FrameworkVersion id={self.id} framework_id={self.framework_id} v={self.version_label!r}>"
