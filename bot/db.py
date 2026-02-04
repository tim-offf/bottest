import os
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fio: Mapped[str] = mapped_column(String(255), nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Code(Base):
    __tablename__ = "codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)


class Season(Base):
    __tablename__ = "seasons"

    season_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")


class Winner(Base):
    __tablename__ = "winners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, ForeignKey("seasons.season_id"))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    return SessionLocal()


async def ensure_active_season(session: AsyncSession) -> Season:
    result = await session.execute(select(Season).where(Season.status == "active"))
    season = result.scalars().first()
    if season:
        return season
    season = Season()
    session.add(season)
    await session.commit()
    return season


async def get_active_season(session: AsyncSession) -> Optional[Season]:
    result = await session.execute(select(Season).where(Season.status == "active"))
    return result.scalars().first()


async def register_user(session: AsyncSession, user_id: int, fio: str) -> bool:
    existing = await session.get(User, user_id)
    if existing:
        return False
    user = User(user_id=user_id, fio=fio)
    session.add(user)
    await log_action(session, user_id, None, "success", "registration", "register")
    await session.commit()
    return True


async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
    return await session.get(User, user_id)


async def add_code(session: AsyncSession, code: str, points: int) -> bool:
    existing = await session.get(Code, code)
    if existing:
        return False
    session.add(Code(code=code, points=points))
    await session.commit()
    return True


async def delete_code(session: AsyncSession, code: str) -> bool:
    existing = await session.get(Code, code)
    if not existing:
        return False
    await session.delete(existing)
    await session.commit()
    return True


async def set_admin_session(session: AsyncSession, user_id: int) -> None:
    existing = await session.get(AdminSession, user_id)
    if not existing:
        session.add(AdminSession(user_id=user_id))
    else:
        existing.activated_at = utcnow()
    await session.commit()


async def is_admin_session(session: AsyncSession, user_id: int) -> bool:
    existing = await session.get(AdminSession, user_id)
    return existing is not None


async def log_action(
    session: AsyncSession,
    user_id: Optional[int],
    code: Optional[str],
    result: str,
    reason: str,
    action: str,
) -> None:
    entry = History(user_id=user_id, code=code, result=result, reason=reason, action=action)
    session.add(entry)


async def get_last_code_action(session: AsyncSession, user_id: int) -> Optional[History]:
    result = await session.execute(
        select(History)
        .where(History.user_id == user_id, History.action == "code_entry")
        .order_by(History.timestamp.desc())
        .limit(1)
    )
    return result.scalars().first()


async def count_recent_failures(session: AsyncSession, user_id: int, since: datetime) -> int:
    result = await session.execute(
        select(func.count(History.id)).where(
            History.user_id == user_id,
            History.action == "code_entry",
            History.result == "failure",
            History.timestamp >= since,
        )
    )
    return int(result.scalar() or 0)


async def apply_code(session: AsyncSession, user: User, code_value: str) -> tuple[bool, str, int]:
    code = await session.get(Code, code_value)
    if not code:
        return False, "invalid_code", 0
    if code.is_used:
        return False, "code_used", 0
    points = code.points
    code.is_used = True
    user.total_points += points
    await session.commit()
    return True, "ok", points


async def get_ranking(session: AsyncSession, user_id: int) -> tuple[int, int]:
    result = await session.execute(select(User).order_by(User.total_points.desc(), User.created_at))
    users = result.scalars().all()
    for idx, user in enumerate(users, start=1):
        if user.user_id == user_id:
            return idx, user.total_points
    return 0, 0


async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.total_points.desc(), User.created_at))
    return list(result.scalars().all())


async def edit_user_fio(session: AsyncSession, user_id: int, fio: str) -> bool:
    user = await session.get(User, user_id)
    if not user:
        return False
    user.fio = fio
    await session.commit()
    return True


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    user = await session.get(User, user_id)
    if not user:
        return False
    await session.execute(delete(History).where(History.user_id == user_id))
    await session.execute(delete(Winner).where(Winner.user_id == user_id))
    await session.delete(user)
    await session.commit()
    return True


async def stop_season(session: AsyncSession) -> list[Winner]:
    active = await get_active_season(session)
    if not active:
        return []
    active.status = "closed"
    active.end_date = utcnow()
    await session.execute(delete(Winner).where(Winner.season_id == active.season_id))
    result = await session.execute(select(User).order_by(User.total_points.desc(), User.created_at).limit(5))
    winners = []
    for idx, user in enumerate(result.scalars().all(), start=1):
        winner = Winner(
            season_id=active.season_id,
            user_id=user.user_id,
            rank=idx,
            points=user.total_points,
        )
        session.add(winner)
        winners.append(winner)
    await session.commit()
    return winners


async def start_new_season(session: AsyncSession) -> Season:
    await session.execute(delete(Code))
    await session.execute(delete(Winner))
    result = await session.execute(select(User))
    for user in result.scalars().all():
        user.total_points = 0
    result = await session.execute(select(Season).where(Season.status == "active"))
    for season in result.scalars().all():
        season.status = "closed"
        season.end_date = utcnow()
    season = Season()
    session.add(season)
    await session.commit()
    return season


async def get_winners(session: AsyncSession, season_id: Optional[int] = None) -> list[Winner]:
    query = select(Winner)
    if season_id is not None:
        query = query.where(Winner.season_id == season_id)
    result = await session.execute(query.order_by(Winner.rank))
    return list(result.scalars().all())


async def get_recent_actions(session: AsyncSession, user_id: int, since: datetime) -> list[History]:
    result = await session.execute(
        select(History).where(History.user_id == user_id, History.timestamp >= since)
    )
    return list(result.scalars().all())
