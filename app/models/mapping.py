"""Control-mapping and authoritative-source models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ControlMapping(Base):
    """Many-to-many mapping from a canonical SCF control to an external framework reference."""

    __tablename__ = "control_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    framework_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mapped_control_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="The identifier in the target framework (e.g. A.9.1.1)"
    )
    mapped_control_title: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Title in the target framework"
    )
    mapping_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="equivalent", comment="equivalent, related, broader, narrower"
    )
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Workbook sheet name this was imported from"
    )
    source_column: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Column header in the source workbook"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    control: Mapped["Control"] = relationship("Control", back_populates="mappings")
    framework: Mapped["Framework"] = relationship("Framework")

    __table_args__ = (
        UniqueConstraint("control_id", "framework_id", "mapped_control_id", name="uq_control_mapping"),
    )

    def __repr__(self) -> str:
        return f"<ControlMapping ctrl={self.control_id} fw={self.framework_id} -> {self.mapped_control_id!r}>"


class AuthoritativeSource(Base):
    """An authoritative source document referenced by the SCF."""

    __tablename__ = "authoritative_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AuthoritativeSource id={self.id} title={self.source_title!r}>"
