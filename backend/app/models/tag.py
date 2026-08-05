import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

TAG_ENTITY_TYPEN = ("kunde", "anlage", "vorgang", "material")


class Tag(SoftDeleteMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("mandant_id", "label", name="uq_tags_mandant_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    farbe: Mapped[str | None] = mapped_column(Text)
    system_tag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TagAssignment(Base):
    __tablename__ = "tag_assignments"
    __table_args__ = (
        CheckConstraint(
            f"entity_type IN {TAG_ENTITY_TYPEN}", name="ck_tag_assignments_entity_type_valid"
        ),
    )

    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
