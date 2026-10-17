from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)


class TagEdge(Base):
    __tablename__ = "tag_edge"
    __table_args__ = (
        UniqueConstraint("parent_id", "child_id"),
        CheckConstraint("parent_id != child_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), nullable=False
    )
    child_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), nullable=False, index=True
    )

    child: Mapped["Tag"] = relationship(foreign_keys=[child_id])
    parent: Mapped["Tag"] = relationship(foreign_keys=[parent_id])


class App(Base):
    __tablename__ = "app"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)


class TagAlias(Base):
    __tablename__ = "tag_alias"

    __table_args__ = (
        UniqueConstraint("app_id", "alias"),
        UniqueConstraint("app_id", "tag_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("app.id"), nullable=False)
    alias: Mapped[str] = mapped_column(nullable=False)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), nullable=False, index=True
    )

    app: Mapped["App"] = relationship()
    tag: Mapped["Tag"] = relationship()
