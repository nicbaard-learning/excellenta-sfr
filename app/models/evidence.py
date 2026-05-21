"""Evidence Artifact model – evidence request items linked to controls."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EvidenceArtifact(Base):
    """An evidence request item / artifact linked to a control."""

    __tablename__ = "evidence_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    erl_number: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="ERL # from the workbook (e.g. ERL-001)"
    )
    evidence_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="e.g. policy, report, screenshot, log"
    )
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Workbook sheet name"
    )
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    control: Mapped["Control"] = relationship("Control", back_populates="evidence_artifacts")

    def __repr__(self) -> str:
        return f"<EvidenceArtifact id={self.id} erl={self.erl_number!r}>"
