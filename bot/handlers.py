import os
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from . import db
from .utils import BRUTE_FORCE_LIMIT, BRUTE_FORCE_WINDOW, compute_cooldown

router = Router()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def format_timedelta(delta) -> str:
    seconds = int(delta.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes} мин {seconds} сек"
    return f"{seconds} сек"


async def ensure_admin(message: Message) -> bool:
    async with db.SessionLocal() as session:
        if not await db.is_admin_session(session, message.from_user.id):
            await message.answer("Нет доступа. Сначала используйте /admin [пароль].")
            return False
    return True


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "Привет! Используйте /register [ФИО], чтобы зарегистрироваться.\n"
        "Для ввода кодов просто отправляйте их в чат."
    )


@router.message(Command("register"))
async def register(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите ФИО: /register Иванов Иван Иванович")
        return
    fio = args[1].strip()
    async with db.SessionLocal() as session:
        success = await db.register_user(session, message.from_user.id, fio)
    if success:
        await message.answer(
            "Регистрация завершена! Данные менять нельзя, поэтому проверьте ФИО.\n"
            "Теперь отправляйте коды для начисления баллов."
        )
    else:
        await message.answer("Вы уже зарегистрированы.")


@router.message(Command("myscore"))
async def myscore(message: Message) -> None:
    async with db.SessionLocal() as session:
        user = await db.get_user(session, message.from_user.id)
        if not user:
            await message.answer("Сначала зарегистрируйтесь через /register.")
            return
        rank, points = await db.get_ranking(session, user.user_id)
    await message.answer(f"Ваш счёт: {points} балл(ов). Текущая позиция: {rank}.")


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Укажите пароль: /admin пароль")
        return
    password = args[1].strip()
    if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
        await message.answer("Неверный пароль.")
        return
    async with db.SessionLocal() as session:
        await db.set_admin_session(session, message.from_user.id)
        await db.log_action(session, message.from_user.id, None, "success", "admin_login", "admin")
        await session.commit()
    await message.answer("Админ-режим активирован.")


@router.message(Command("addcode"))
async def add_code(message: Message) -> None:
    if not await ensure_admin(message):
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /addcode CODE 1|2")
        return
    code = args[1].strip()
    try:
        points = int(args[2])
    except ValueError:
        await message.answer("Баллы должны быть числом 1 или 2.")
        return
    if points not in {1, 2}:
        await message.answer("Баллы должны быть 1 или 2.")
        return
    async with db.SessionLocal() as session:
        success = await db.add_code(session, code, points)
        await db.log_action(
            session,
            message.from_user.id,
            code,
            "success" if success else "failure",
            "add_code",
            "admin",
        )
        await session.commit()
    if success:
        await message.answer(f"Код {code} добавлен с {points} балл(ами).")
    else:
        await message.answer("Такой код уже существует.")


@router.message(Command("viewstats"))
async def view_stats(message: Message) -> None:
    if not await ensure_admin(message):
        return
    async with db.SessionLocal() as session:
        users = await db.get_all_users(session)
        await db.log_action(session, message.from_user.id, None, "success", "view_stats", "admin")
        await session.commit()
    if not users:
        await message.answer("Список участников пуст.")
        return
    lines = ["Рейтинг участников:"]
    for idx, user in enumerate(users, start=1):
        lines.append(f"{idx}. {user.fio} — {user.total_points} балл(ов) (ID: {user.user_id})")
    await message.answer("\n".join(lines))


@router.message(Command("edituser"))
async def edit_user(message: Message) -> None:
    if not await ensure_admin(message):
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /edituser TG_ID Новое ФИО")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Некорректный TG_ID.")
        return
    fio = args[2].strip()
    async with db.SessionLocal() as session:
        success = await db.edit_user_fio(session, user_id, fio)
        await db.log_action(
            session,
            message.from_user.id,
            None,
            "success" if success else "failure",
            f"edit_user:{user_id}",
            "admin",
        )
        await session.commit()
    if success:
        await message.answer("ФИО обновлено.")
    else:
        await message.answer("Пользователь не найден.")


@router.message(Command("deleteuser"))
async def delete_user(message: Message) -> None:
    if not await ensure_admin(message):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /deleteuser TG_ID")
        return
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("Некорректный TG_ID.")
        return
    async with db.SessionLocal() as session:
        success = await db.delete_user(session, user_id)
        await db.log_action(
            session,
            message.from_user.id,
            None,
            "success" if success else "failure",
            f"delete_user:{user_id}",
            "admin",
        )
        await session.commit()
    if success:
        await message.answer("Пользователь удалён.")
    else:
        await message.answer("Пользователь не найден.")


@router.message(Command("deletecode"))
async def delete_code(message: Message) -> None:
    if not await ensure_admin(message):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /deletecode CODE")
        return
    code = args[1].strip()
    async with db.SessionLocal() as session:
        success = await db.delete_code(session, code)
        await db.log_action(
            session,
            message.from_user.id,
            code,
            "success" if success else "failure",
            "delete_code",
            "admin",
        )
        await session.commit()
    if success:
        await message.answer("Код удалён.")
    else:
        await message.answer("Код не найден.")


@router.message(Command("stop_season"))
async def stop_season(message: Message) -> None:
    if not await ensure_admin(message):
        return
    async with db.SessionLocal() as session:
        winners = await db.stop_season(session)
        await db.log_action(session, message.from_user.id, None, "success", "stop_season", "admin")
        await session.commit()
    if not winners:
        await message.answer("Нет активного сезона.")
        return
    lines = ["Сезон закрыт. Топ-5 участников:"]
    for winner in winners:
        lines.append(f"{winner.rank}. ID {winner.user_id} — {winner.points} балл(ов)")
    lines.append("Используйте /notify_winners [сообщение], чтобы отправить сообщение победителям.")
    await message.answer("\n".join(lines))


@router.message(Command("notify_winners"))
async def notify_winners(message: Message) -> None:
    if not await ensure_admin(message):
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /notify_winners Ваше сообщение")
        return
    notification = args[1].strip()
    async with db.SessionLocal() as session:
        winners = await db.get_winners(session)
        await db.log_action(session, message.from_user.id, None, "success", "notify_winners", "admin")
        await session.commit()
    if not winners:
        await message.answer("Список победителей пуст.")
        return
    for winner in winners:
        try:
            await message.bot.send_message(winner.user_id, notification)
        except Exception:
            continue
    await message.answer("Сообщение отправлено победителям (если они доступны).")


@router.message(Command("new_season"))
async def new_season(message: Message) -> None:
    if not await ensure_admin(message):
        return
    async with db.SessionLocal() as session:
        season = await db.start_new_season(session)
        await db.log_action(session, message.from_user.id, None, "success", "new_season", "admin")
        await session.commit()
    await message.answer(f"Новый сезон запущен (ID {season.season_id}). Баллы обнулены.")


@router.message(F.text)
async def handle_code(message: Message) -> None:
    if not message.text:
        return
    code_value = message.text.strip()
    if code_value.startswith("/"):
        return
    async with db.SessionLocal() as session:
        user = await db.get_user(session, message.from_user.id)
        if not user:
            await db.log_action(session, message.from_user.id, code_value, "failure", "not_registered", "code_entry")
            await session.commit()
            await message.answer("Сначала зарегистрируйтесь через /register.")
            return
        active_season = await db.get_active_season(session)
        if not active_season:
            await db.log_action(session, user.user_id, code_value, "failure", "no_active_season", "code_entry")
            await session.commit()
            await message.answer("Сезон не активен. Ожидайте запуска нового сезона.")
            return
        last_action = await db.get_last_code_action(session, user.user_id)
        cooldown = compute_cooldown(last_action)
        if cooldown:
            await db.log_action(session, user.user_id, code_value, "failure", "cooldown", "code_entry")
            await session.commit()
            await message.answer(f"Попробуйте позже. Осталось ждать: {format_timedelta(cooldown)}.")
            return
        failures = await db.count_recent_failures(
            session, user.user_id, datetime.utcnow() - BRUTE_FORCE_WINDOW
        )
        if failures >= BRUTE_FORCE_LIMIT:
            await db.log_action(session, user.user_id, code_value, "failure", "bruteforce_limit", "code_entry")
            await session.commit()
            await message.answer("Слишком много неудачных попыток. Попробуйте позже.")
            return
        success, reason, points = await db.apply_code(session, user, code_value)
        if not success:
            message_text = "Неверный код." if reason == "invalid_code" else "Этот код уже использован."
            await db.log_action(session, user.user_id, code_value, "failure", reason, "code_entry")
            await session.commit()
            await message.answer(message_text)
            return
        await db.log_action(session, user.user_id, code_value, "success", "code_accepted", "code_entry")
        await session.commit()
        await message.answer(
            f"Код принят! Начислено {points} балл(ов). Ваш счёт: {user.total_points}."
        )
