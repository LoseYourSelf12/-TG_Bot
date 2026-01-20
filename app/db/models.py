from __future__ import annotations

import uuid
from datetime import date, time, datetime
from typing import Optional

from sqlalchemy import (
    Text,
    Date,
    Time,
    ForeignKey,
    Numeric,
    Integer,
    BigInteger,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, CITEXT


SCHEMA = "nutrition_bot"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    tg_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(Text)
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    language_code: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profile"
    __table_args__ = {"schema": SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True)
    timezone_iana: Mapped[str] = mapped_column(Text, nullable=False, server_default="Europe/Moscow")
    utc_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="180")

    sex: Mapped[Optional[str]] = mapped_column(Text)
    age: Mapped[Optional[int]] = mapped_column(Integer)
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    goal: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")


class ProductRef(Base):
    __tablename__ = "products_ref"
    __table_args__ = (
        UniqueConstraint("name", "brand", name="uq_products_ref_name_brand"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(CITEXT)

    kcal_per_100g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    protein_100g: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    fat_100g: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    carbs_100g: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ProductSynonym(Base):
    __tablename__ = "product_synonyms"
    __table_args__ = (
        UniqueConstraint("product_ref_id", "synonym", name="uq_product_synonyms"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    product_ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.products_ref.id", ondelete="CASCADE"), nullable=False)
    synonym: Mapped[str] = mapped_column(CITEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)

    meal_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_time: Mapped[time] = mapped_column(Time, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    items: Mapped[list["MealItem"]] = relationship(back_populates="meal", cascade="all, delete-orphan")
    photos: Mapped[list["MealPhoto"]] = relationship(back_populates="meal", cascade="all, delete-orphan")


class MealItem(Base):
    __tablename__ = "meal_items"
    __table_args__ = (
        CheckConstraint("position > 0", name="meal_items_position_positive"),
        CheckConstraint("NOT (product_ref_id IS NOT NULL AND user_product_id IS NOT NULL)", name="chk_meal_items_single_mapping"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    meal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.meals.id", ondelete="CASCADE"), nullable=False)

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_name: Mapped[str] = mapped_column(Text, nullable=False)

    product_ref_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.products_ref.id", ondelete="SET NULL"))
    user_product_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.products_user.id", ondelete="SET NULL"))

    grams: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    kcal_total: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    meal: Mapped[Meal] = relationship(back_populates="items")


class MealPhoto(Base):
    __tablename__ = "meal_photos"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    meal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.meals.id", ondelete="CASCADE"), nullable=False)

    tg_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    tg_file_unique_id: Mapped[Optional[str]] = mapped_column(Text)

    local_path: Mapped[Optional[str]] = mapped_column(Text)
    mime_type: Mapped[Optional[str]] = mapped_column(Text)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    meal: Mapped[Meal] = relationship(back_populates="photos")
