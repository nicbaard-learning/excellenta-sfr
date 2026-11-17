"""Framework requirement model – the text of a framework's own provisions.

SCF mappings only name a provision ("22", "Art 33"). This table holds the
provision itself (section, regulation, article) with its official text, so a
framework page can show the law next to the SCF controls mapped to it.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FrameworkRequirement(Base):
    """One provision of a framework (a chapter, part, section, regulation or article)."""

    __tablename__ = "framework_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Unique reference within the framework, e.g. s22, r4, ch3"
    )
    instrument: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Document the provision belongs to, e.g. Act, Regulations"
    )
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="chapter, part, section, regulation, article, recital"
    )
    number: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="Number as printed in the instrument, e.g. 22, 4, 3A"
    )
    parent_ref: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="ref of the enclosing chapter or part"
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Provision text as published")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version_label: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Text version, e.g. 'as amended to 2020-07-01'"
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="in_force",
        comment="in_force, not_in_force, pending_amendment, repealed",
    )
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    framework: Mapped["Framework"] = relationship("Framework")

    __table_args__ = (
        UniqueConstraint("framework_id", "ref", name="uq_framework_requirement_ref"),
    )

    def __repr__(self) -> str:
        return f"<FrameworkRequirement fw={self.framework_id} ref={self.ref!r}>"
