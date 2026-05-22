"""Risk model – risks cataloged in the SCF Risk Catalog sheet."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Risk(Base):
    """A risk entry from the SCF Risk Catalog."""

    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="Risk # from the catalog"
    )
    risk_grouping: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Risk Grouping category"
    )
    risk_title: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Risk name / title"
    )
    risk_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Description of possible risk due to control deficiency"
    )
    nist_csf_function: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="NIST CSF Function mapping"
    )
    materiality_considerations: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Materiality impact considerations"
    )
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Source workbook sheet name"
    )
    source_row: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Row number in source sheet"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Risk id={self.id} num={self.risk_number!r}>"


class RiskControlLink(Base):
    """Many-to-many link between risks and controls."""

    __tablename__ = "risk_control_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("risk_id", "control_id", name="uq_risk_control"),
    )

    def __repr__(self) -> str:
        return f"<RiskControlLink risk={self.risk_id} control={self.control_id}>"
