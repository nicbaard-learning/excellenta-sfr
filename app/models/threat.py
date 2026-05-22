"""Threat model – threats cataloged in the SCF Threat Catalog sheet."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Threat(Base):
    """A threat entry from the SCF Threat Catalog."""

    __tablename__ = "threats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    threat_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True, comment="Threat # from the catalog"
    )
    threat_grouping: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Threat Grouping category"
    )
    threat_title: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Threat name / title"
    )
    threat_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Threat description"
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
        return f"<Threat id={self.id} num={self.threat_number!r}>"


class ThreatControlLink(Base):
    """Many-to-many link between threats and controls."""

    __tablename__ = "threat_control_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    threat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("threats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("threat_id", "control_id", name="uq_threat_control"),
    )

    def __repr__(self) -> str:
        return f"<ThreatControlLink threat={self.threat_id} control={self.control_id}>"
