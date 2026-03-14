from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.enums import MessageEntityType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bjj_bot.config import Settings
from bjj_bot.keyboards import (
    arsenal_menu_keyboard,
    category_picker_keyboard,
    confirm_delete_category_keyboard,
    confirm_delete_promotion_keyboard,
    confirm_delete_session_keyboard,
    confirm_delete_move_keyboard,
    date_picker_keyboard,
    history_keyboard,
    library_edit_keyboard,
    main_menu_actions_keyboard,
    me_menu_keyboard,
    move_edit_keyboard,
    move_details_keyboard,
    moves_keyboard,
    prompt_keyboard,
    promotion_details_keyboard,
    rank_picker_keyboard,
    session_saved_keyboard,
    upgrade_keyboard,
    upgrade_history_keyboard,
    session_details_keyboard,
    session_builder_keyboard,
)
from bjj_bot.services import arsenal as arsenal_service
from bjj_bot.services import history as history_service
from bjj_bot.services import promotions as promotion_service
from bjj_bot.services import rank as rank_service
from bjj_bot.services import sessions as session_service
from bjj_bot.services import users as user_service
from bjj_bot.states import (
    AddMoveFlow,
    CustomDateFlow,
    EditMoveFlow,
    EditPromotionFlow,
    EditSessionFlow,
    LibCatFlow,
    MoveSearchFlow,
    RankEmojiCaptureFlow,
)
from bjj_bot.visuals import belt_emoji_for, build_rank_text, get_rank_visual, get_sticker_id, rank_key
from bjj_bot.models import ArsenalMove, Belt, Promotion


router = Router()


@router.error()
async def _suppress_message_not_modified(event: ErrorEvent) -> bool:
    if isinstance(event.exception, TelegramBadRequest) and "message is not modified" in str(
        event.exception
    ):
        if event.update.callback_query:
            await event.update.callback_query.answer()
        return True
    return False


def _short_date(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def _history_date(value: date) -> str:
    return value.strftime("%d %B, %Y")


def _parse_user_date(raw_value: str) -> date:
    return datetime.strptime(raw_value, "%d-%m-%Y").date()


def _timezone(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _today(settings: Settings) -> date:
    return datetime.now(_timezone(settings)).date()



def _duration_parts(start_date: date, end_date: date) -> tuple[int, int, int]:
    years = end_date.year - start_date.year
    months = end_date.month - start_date.month
    days = end_date.day - start_date.day
    if days < 0:
        months -= 1
        previous_month_last_day = end_date.replace(day=1) - timedelta(days=1)
        days += previous_month_last_day.day
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


def _format_duration(start_date: date, end_date: date) -> str:
    years, months, days = _duration_parts(start_date, end_date)
    year_label = "year" if years == 1 else "years"
    month_label = "month" if months == 1 else "months"
    day_label = "day" if days == 1 else "days"
    return f"{years} {year_label}, {months} {month_label}, {days} {day_label}"


def _format_rank_history_lines(
    *,
    start_date: date,
    promotions: list[tuple[date, str, int]],
    belt_emoji_map: dict[str, str],
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> list[str]:
    lines = [f"{_history_date(start_date)} {build_rank_text(Belt.WHITE.value, 0, belt_emoji_map, rank_custom_emoji_map)}"]
    for promotion_date, belt, stripes in promotions:
        lines.append(f"{_history_date(promotion_date)} {build_rank_text(belt, stripes, belt_emoji_map, rank_custom_emoji_map)}")
    return lines


def _upgrade_option_label(
    belt: str,
    stripes: int,
    belt_emoji_map: dict[str, str],
    rank_custom_emoji_map: dict[str, str] | None = None,
) -> str:
    return build_rank_text(belt, stripes, belt_emoji_map, rank_custom_emoji_map)


async def _send_me_info(
    *,
    message: Message,
    telegram_user,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    edit: bool = False,
) -> None:
    today = _today(settings)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        progress = await user_service.get_progress(session, user.id)
        first_logged_date = await session_service.first_session_date(session, user_id=user.id)
        sessions_last_30 = await session_service.count_sessions_since(
            session,
            user_id=user.id,
            since_date=today - timedelta(days=29),
        )
        promotion_rows = await session.execute(
            select(Promotion.promotion_date, Promotion.belt, Promotion.stripes)
            .where(Promotion.user_id == user.id)
            .order_by(Promotion.promotion_date, Promotion.created_at)
        )
        promotions = [(row[0], row[1], row[2]) for row in promotion_rows.all()]
        total_moves = await arsenal_service.count_total_moves(session, user.id)

    is_black = progress.belt == Belt.BLACK.value
    visual = get_rank_visual(
        progress.belt,
        progress.stripes,
        settings.rank_stickers,
        settings.belt_emojis,
        settings.rank_custom_emojis,
        competitor=progress.competitor,
    )
    if visual.sticker_id:
        await message.answer_sticker(visual.sticker_id)

    started_on = first_logged_date or user.created_at.date()
    progress_lines = _format_rank_history_lines(
        start_date=started_on,
        promotions=promotions,
        belt_emoji_map=settings.belt_emojis,
        rank_custom_emoji_map=settings.rank_custom_emojis,
    )
    text = "\n".join(
        [
            f"Current level: {visual.text}",
            "",
            f"You are doing BJJ for {_format_duration(started_on, today)}",
            f"Total sessions: {progress.total_sessions}",
            f"Sessions in last 30 days: {sessions_last_30}",
            f"Techniques in arsenal: {total_moves}",
            "",
            "Progress history:",
            *progress_lines,
        ]
    )
    keyboard = me_menu_keyboard(
        belt_emoji=belt_emoji_for(progress.belt, settings.belt_emojis),
        is_black_belt=is_black,
        competitor=progress.competitor,
    )
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


async def _show_session_history_page(
    *,
    target_message: Message,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    offset: int,
    edit: bool = True,
) -> bool:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        items = await history_service.get_session_history(session, user_id=user.id, offset=offset, limit=10)
        has_next = len(await history_service.get_session_history(session, user_id=user.id, offset=offset + 10, limit=1)) > 0
    if not items:
        return False
    text = _render_history_text(items)
    session_rows = [(f"logged_session:view:{item.entity_id}", f"✏️ Edit {_history_date(item.date)}") for item in items]
    keyboard = history_keyboard(
        session_rows,
        offset=offset,
        has_previous=offset > 0,
        has_next=has_next,
        back_callback="menu:me",
    )
    if edit:
        await target_message.edit_text(text, reply_markup=keyboard)
    else:
        await target_message.answer(text, reply_markup=keyboard)
    return True


async def _show_upgrade_history_page(
    *,
    target_message: Message,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    settings: Settings,
    offset: int,
    edit: bool = True,
) -> bool:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        items = await history_service.get_promotion_history(
            session,
            user_id=user.id,
            offset=offset,
            limit=10,
            belt_emoji_map=settings.belt_emojis,
            rank_custom_emoji_map=settings.rank_custom_emojis,
        )
        has_next = len(
            await history_service.get_promotion_history(
                session,
                user_id=user.id,
                offset=offset + 10,
                limit=1,
                belt_emoji_map=settings.belt_emojis,
                rank_custom_emoji_map=settings.rank_custom_emojis,
            )
        ) > 0
    if not items:
        return False
    text = _render_history_text(items)
    item_rows = [
        (f"promotion:view:{item.entity_id}", f"✏️ Edit {_history_date(item.date)}")
        for item in items
    ]
    keyboard = upgrade_history_keyboard(
        item_rows,
        offset=offset,
        has_previous=offset > 0,
        has_next=has_next,
    )
    if edit:
        await target_message.edit_text(text, reply_markup=keyboard)
    else:
        await target_message.answer(text, reply_markup=keyboard)
    return True


def _log_session_picker_markup(settings: Settings):
    return date_picker_keyboard(
        "session_date",
        today=_today(settings),
        custom_target="session",
        back_callback="menu:home",
    )


async def _show_log_session_menu(message: Message, settings: Settings) -> None:
    await message.edit_text("📝 Which day?", reply_markup=_log_session_picker_markup(settings))


async def _show_home_menu(message: Message) -> None:
    await message.edit_text("🏠 Menu", reply_markup=main_menu_actions_keyboard())


async def _send_home_menu(message: Message) -> None:
    await message.answer("🏠 Menu", reply_markup=main_menu_actions_keyboard())


async def _show_move_details_message(
    *,
    target_message: Message,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    move_id: int,
    edit: bool = True,
) -> bool:
    payload = await _build_move_details(
        session_maker=session_maker,
        telegram_user=telegram_user,
        move_id=move_id,
    )
    if payload is None:
        return False
    text, resolved_move_id = payload
    if edit:
        await target_message.edit_text(text, reply_markup=move_details_keyboard(resolved_move_id))
    else:
        await target_message.answer(text, reply_markup=move_details_keyboard(resolved_move_id))
    return True


async def _show_promotion_details_message(
    *,
    target_message: Message,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    settings: Settings,
    promotion_id: int,
    edit: bool = True,
) -> bool:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        promotion = await promotion_service.get_promotion(session, user_id=user.id, promotion_id=promotion_id)
    if promotion is None:
        return False
    text = "\n".join(
        [
            f"🥋 {build_rank_text(promotion.belt, promotion.stripes, settings.belt_emojis, settings.rank_custom_emojis)}",
            f"Date: {_history_date(promotion.promotion_date)}",
            f"Earned at session {promotion.session_number}",
        ]
    )
    if edit:
        await target_message.edit_text(text, reply_markup=promotion_details_keyboard(promotion.id))
    else:
        await target_message.answer(text, reply_markup=promotion_details_keyboard(promotion.id))
    return True


@router.message(F.text.in_(["Menu", "/start", "/menu"]))
async def menu_router(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await _send_home_menu(message)


@router.message(F.text == "/rankemojiids")
async def start_rank_emoji_capture(message: Message, state: FSMContext) -> None:
    await state.set_state(RankEmojiCaptureFlow.waiting_for_custom_emoji)
    await message.answer(
        "Send one rank custom emoji per message\n"
        "I will reply with its custom_emoji_id\n"
        "Send /done when finished"
    )


@router.message(RankEmojiCaptureFlow.waiting_for_custom_emoji, F.text == "/done")
async def finish_rank_emoji_capture(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_home_menu(message)


@router.message(RankEmojiCaptureFlow.waiting_for_custom_emoji)
async def capture_rank_emoji_id(message: Message) -> None:
    custom_emoji_ids = [
        entity.custom_emoji_id
        for entity in (message.entities or [])
        if entity.type == MessageEntityType.CUSTOM_EMOJI and entity.custom_emoji_id
    ]
    if not custom_emoji_ids:
        await message.answer("Send one custom emoji")
        return
    if len(custom_emoji_ids) > 1:
        await message.answer("Send one custom emoji at a time")
        return
    await message.answer(custom_emoji_ids[0])


@router.callback_query(F.data == "menu:home")
async def menu_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_home_menu(callback.message)
    await callback.answer()


@router.callback_query(F.data == "menu:me")
async def menu_me_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await state.clear()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        progress = await user_service.get_progress(session, user.id)
    is_black = progress.belt == Belt.BLACK.value
    await callback.message.edit_text(
        "🥷 Me",
        reply_markup=me_menu_keyboard(
            belt_emoji=belt_emoji_for(progress.belt, settings.belt_emojis),
            is_black_belt=is_black,
            competitor=progress.competitor,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:arsenal")
async def menu_arsenal_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🥋 Arsenal", reply_markup=arsenal_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:log_session")
async def menu_log_session_callback(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await _show_log_session_menu(callback.message, settings)
    await callback.answer()


async def _start_session_move_picker(
    *,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    raw_date: str,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
    await state.update_data(session_date=raw_date, selected_move_ids=[], session_user_id=user.id)
    if callback is not None:
        await _render_session_picker(callback, session_maker, user.id, state)
    elif message is not None:
        label, keyboard = await _build_session_picker_markup(
            session_maker=session_maker,
            user_id=user.id,
            state=state,
        )
        await message.answer(label, reply_markup=keyboard)


async def _render_session_picker(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    state: FSMContext,
    category_code: str | None = None,
    recent: bool = False,
) -> None:
    label, keyboard = await _build_session_picker_markup(
        session_maker=session_maker,
        user_id=user_id,
        state=state,
        category_code=category_code,
        recent=recent,
    )
    await callback.message.edit_text(label, reply_markup=keyboard)
    await callback.answer()


async def _build_session_picker_markup(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    state: FSMContext,
    category_code: str | None = None,
    recent: bool = False,
) -> tuple[str, object]:
    data = await state.get_data()
    selected_ids = set(data.get("selected_move_ids", []))
    update_payload = {
        "current_session_category": category_code,
        "current_session_recent": recent,
    }
    if category_code:
        update_payload["last_session_category"] = category_code
    await state.update_data(**update_payload)
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, category_code, user_id=user_id)
        moves = []
        if category_code:
            direct_moves = await arsenal_service.list_moves_in_category(session, user_id, category_code)
            moves = [(move.id, move.name, move.id in selected_ids) for move in direct_moves]
        recent_moves = None
        if recent:
            recent_rows = await arsenal_service.list_recent_moves(session, user_id)
            recent_moves = [(move.id, move.name, move.id in selected_ids) for move in recent_rows]
        keyboard = session_builder_keyboard(
            selected_count=len(selected_ids),
            category_nodes=categories,
            moves=moves,
            category_code=category_code,
            recent_moves=recent_moves,
            recent=recent,
        )
    label = "🥋 Pick practiced moves"
    if category_code:
        label = "🥋 Pick practiced moves in this group"
    elif recent:
        label = "🕘 Recent practiced moves"
    return label, keyboard


async def _render_arsenal_browser(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    category_code: str | None,
) -> None:
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, category_code, user_id=user_id)
        if category_code:
            moves = await arsenal_service.list_moves_in_category(session, user_id, category_code)
            move_rows = [(move.id, move.name) for move in moves]
            category = await arsenal_service.get_category(session, category_code)
            heading = category.name if category else "Arsenal"
            if move_rows:
                await callback.message.edit_text(
                    heading,
                    reply_markup=moves_keyboard("move:view", move_rows, back_callback=f"arsenal:back:{category_code}"),
                )
                await callback.answer()
                return
        parent_slug = category_code or "root"
        keyboard = category_picker_keyboard(
            category_nodes=categories,
            current_code=category_code,
            open_action="arsenal:browse",
            back_action="arsenal:back",
            root_back_callback="menu:arsenal",
            edit_layout_callback=f"libcat:edit:{parent_slug}",
        )
    await callback.message.edit_text("📚 Library", reply_markup=keyboard)
    await callback.answer()


async def _build_move_details(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    move_id: int,
) -> tuple[str, int] | None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        move = await arsenal_service.get_move(session, user.id, move_id)
        if move is None:
            return None
        category = await arsenal_service.get_category(session, move.category_code)
    return arsenal_service.format_move_details(move, category.name if category else None), move.id


async def _build_session_details(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    session_id: int,
) -> tuple[str, int] | None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        training_session = await session_service.get_session(session, user_id=user.id, session_id=session_id)
        if training_session is None:
            return None
        move_ids = [row.move_id for row in training_session.practiced_moves]
        moves = []
        if move_ids:
            query = await session.execute(select(ArsenalMove.name).where(ArsenalMove.id.in_(move_ids)))
            moves = [row[0] for row in query.all()]
    move_label = "move" if len(move_ids) == 1 else "moves"
    text_lines = [
        f"{_history_date(training_session.session_date)}",
        f"Practiced {len(move_ids)} {move_label}",
    ]
    if moves:
        text_lines.extend(f"- {move_name}" for move_name in moves)
    text = "\n".join(text_lines)
    return text, training_session.id


def _render_history_text(items: list[history_service.HistoryItem]) -> str:
    rendered: list[str] = []
    for item in items:
        rendered.append(f"{_history_date(item.date)}\n{item.text}")
    return "\n\n".join(rendered)


async def _show_recent_moves(
    *,
    target_message: Message,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
    edit: bool = True,
) -> bool:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        moves = await arsenal_service.list_recent_moves(session, user.id)
    if not moves:
        return False
    markup = moves_keyboard(
        "move:view",
        [(move.id, move.name) for move in moves],
        back_callback="arsenal:home",
    )
    if edit:
        await target_message.edit_text("🕘 Recent moves", reply_markup=markup)
    else:
        await target_message.answer("🕘 Recent moves", reply_markup=markup)
    return True


@router.message(F.text == "Info")
async def me_info(message: Message, session_maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    await _send_me_info(
        message=message,
        telegram_user=message.from_user,
        session_maker=session_maker,
        settings=settings,
    )


@router.callback_query(F.data == "me:info")
async def me_info_callback(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await _send_me_info(
        message=callback.message,
        telegram_user=callback.from_user,
        session_maker=session_maker,
        settings=settings,
        edit=True,
    )
    await callback.answer()


@router.callback_query(F.data == "me:show_belt")
async def show_belt_callback(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        progress = await user_service.get_progress(session, user.id)
    sticker_id = get_sticker_id(
        progress.belt,
        progress.stripes,
        settings.rank_stickers,
        competitor=progress.competitor,
    )
    if sticker_id:
        await callback.message.answer_sticker(sticker_id)
    else:
        await callback.answer("No sticker for this belt", show_alert=True)
        return
    await callback.answer()


@router.message(F.text == "Upgrade")
async def upgrade_menu(message: Message, session_maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        progress = await user_service.get_progress(session, user.id)
    current = rank_service.RankState(belt=progress.belt, stripes=progress.stripes)
    options = [
        (
            rank_key(option.belt, option.stripes),
            _upgrade_option_label(option.belt, option.stripes, settings.belt_emojis, settings.rank_custom_emojis),
        )
        for option in rank_service.next_rank_choices(current)
    ]
    if not options:
        await message.answer("You are already at the highest configured rank", reply_markup=me_menu_keyboard())
        return
    await message.answer("⬆️ Pick your new level", reply_markup=upgrade_keyboard(options))


@router.callback_query(F.data == "me:upgrade")
async def upgrade_menu_callback(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        progress = await user_service.get_progress(session, user.id)
    current = rank_service.RankState(belt=progress.belt, stripes=progress.stripes)
    options = [
        (
            rank_key(option.belt, option.stripes),
            _upgrade_option_label(option.belt, option.stripes, settings.belt_emojis, settings.rank_custom_emojis),
        )
        for option in rank_service.next_rank_choices(current)
    ]
    if not options:
        await callback.message.edit_text("You are already at the highest configured rank", reply_markup=me_menu_keyboard())
        await callback.answer()
        return
    await callback.message.edit_text("⬆️ Pick your new level", reply_markup=upgrade_keyboard(options))
    await callback.answer()


@router.callback_query(F.data.startswith("upgrade:set:"))
async def apply_upgrade(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    _, _, raw_rank = callback.data.split(":", 2)
    belt, raw_stripes = raw_rank.split(":", 1)
    stripes = int(raw_stripes)

    # When upgrading to a black belt rank, ask competitor/non-competitor first
    if belt == Belt.BLACK.value:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🥋 Regular", callback_data=f"upgrade:comp:0:{belt}:{stripes}")],
                [InlineKeyboardButton(text="🏆 Competitor", callback_data=f"upgrade:comp:1:{belt}:{stripes}")],
            ]
        )
        await callback.message.edit_text("Which type of black belt?", reply_markup=keyboard)
        await callback.answer()
        return

    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        try:
            promotion = await promotion_service.set_promotion_rank(
                session,
                user_id=user.id,
                promotion_date=_today(settings),
                belt=belt,
                stripes=stripes,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        progress = await user_service.get_progress(session, user.id)
    visual = get_rank_visual(
        progress.belt,
        progress.stripes,
        settings.rank_stickers,
        settings.belt_emojis,
        settings.rank_custom_emojis,
        competitor=progress.competitor,
    )
    sticker_id = get_sticker_id(progress.belt, progress.stripes, settings.rank_stickers, competitor=progress.competitor)
    if sticker_id:
        await callback.message.answer_sticker(sticker_id)
    await callback.message.answer(
        f"👏 Congrats\n{visual.text}\nLogged on {_history_date(promotion.promotion_date)}",
        reply_markup=me_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("upgrade:comp:"))
async def apply_upgrade_with_competitor(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    # upgrade:comp:{0|1}:{belt}:{stripes}
    parts = callback.data.split(":")
    competitor = parts[2] == "1"
    belt = parts[3]
    stripes = int(parts[4])

    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        try:
            promotion = await promotion_service.set_promotion_rank(
                session,
                user_id=user.id,
                promotion_date=_today(settings),
                belt=belt,
                stripes=stripes,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await user_service.set_competitor(session, user.id, competitor)
        progress = await user_service.get_progress(session, user.id)
    visual = get_rank_visual(
        progress.belt,
        progress.stripes,
        settings.rank_stickers,
        settings.belt_emojis,
        settings.rank_custom_emojis,
        competitor=progress.competitor,
    )
    sticker_id = get_sticker_id(progress.belt, progress.stripes, settings.rank_stickers, competitor=progress.competitor)
    if sticker_id:
        await callback.message.answer_sticker(sticker_id)
    is_black = progress.belt == Belt.BLACK.value
    await callback.message.answer(
        f"👏 Congrats\n{visual.text}\nLogged on {_history_date(promotion.promotion_date)}",
        reply_markup=me_menu_keyboard(
            belt_emoji=belt_emoji_for(progress.belt, settings.belt_emojis),
            is_black_belt=is_black,
            competitor=progress.competitor,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "me:toggle_competitor")
async def toggle_competitor_callback(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        progress = await user_service.get_progress(session, user.id)
        new_value = not progress.competitor
        await user_service.set_competitor(session, user.id, new_value)
        progress = await user_service.get_progress(session, user.id)
    visual = get_rank_visual(
        progress.belt,
        progress.stripes,
        settings.rank_stickers,
        settings.belt_emojis,
        settings.rank_custom_emojis,
        competitor=progress.competitor,
    )
    label = "Competitor" if progress.competitor else "Regular"
    await callback.message.edit_text(
        f"Belt type: {label}\n{visual.text}",
        reply_markup=me_menu_keyboard(
            belt_emoji=belt_emoji_for(progress.belt, settings.belt_emojis),
            is_black_belt=True,
            competitor=progress.competitor,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "me:upgrades")
async def show_upgrade_history_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await state.clear()
    shown = await _show_upgrade_history_page(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        settings=settings,
        offset=0,
    )
    if not shown:
        await callback.message.edit_text("No upgrades yet", reply_markup=me_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "me:sessions")
async def show_session_history_from_me(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    shown = await _show_session_history_page(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        offset=0,
    )
    if not shown:
        await callback.message.edit_text("No sessions yet", reply_markup=me_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("promotion_history:"))
async def paginate_upgrade_history(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await state.clear()
    _, raw_offset = callback.data.split(":", 1)
    offset = int(raw_offset)
    shown = await _show_upgrade_history_page(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        settings=settings,
        offset=offset,
    )
    if not shown:
        await callback.answer("Nothing more")
        return
    await callback.answer()


@router.callback_query(F.data.startswith("promotion:view:"))
async def promotion_view(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    promotion_id = int(raw_id)
    await state.clear()
    shown = await _show_promotion_details_message(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        settings=settings,
        promotion_id=promotion_id,
    )
    if not shown:
        await callback.message.edit_text("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
    await callback.answer()


@router.callback_query(F.data.startswith("promotion:rank:"))
async def promotion_rank_menu(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    promotion_id = int(raw_id)
    await state.update_data(edit_promotion_id=promotion_id)
    options = [
        (
            rank_key(option.belt, option.stripes),
            _upgrade_option_label(option.belt, option.stripes, settings.belt_emojis, settings.rank_custom_emojis),
        )
        for option in rank_service.all_rank_states()
    ]
    await callback.message.edit_text(
        "🥋 Pick the correct level",
        reply_markup=rank_picker_keyboard(
            options=options,
            callback_prefix=f"promotion:set:{promotion_id}",
            back_callback=f"promotion:view:{promotion_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promotion:set:"))
async def promotion_set_rank(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    _, _, raw_id, belt, raw_stripes = callback.data.split(":", 4)
    promotion_id = int(raw_id)
    stripes = int(raw_stripes)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        try:
            updated = await promotion_service.update_promotion(
                session,
                user_id=user.id,
                promotion_id=promotion_id,
                belt=belt,
                stripes=stripes,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
    await state.clear()
    if updated is None:
        await callback.message.edit_text("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
        await callback.answer()
        return
    shown = await _show_promotion_details_message(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        settings=settings,
        promotion_id=promotion_id,
    )
    if not shown:
        await callback.message.edit_text("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
    await callback.answer("Upgrade updated")


@router.callback_query(F.data.startswith("promotion:date:"))
async def promotion_date_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    promotion_id = int(raw_id)
    await state.update_data(edit_promotion_id=promotion_id)
    await state.set_state(EditPromotionFlow.waiting_for_date)
    await callback.message.edit_text(
        "🗓️ Send date as DD-MM-YYYY",
        reply_markup=prompt_keyboard(back_callback=f"promotion:view:{promotion_id}"),
    )
    await callback.answer()


@router.message(EditPromotionFlow.waiting_for_date)
async def promotion_date_submit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    raw_date = (message.text or "").strip()
    data = await state.get_data()
    promotion_id = data.get("edit_promotion_id")
    try:
        chosen_date = _parse_user_date(raw_date)
    except ValueError:
        await message.answer(
            "Use DD-MM-YYYY",
            reply_markup=prompt_keyboard(back_callback=f"promotion:view:{promotion_id}" if promotion_id else "me:upgrades"),
        )
        return

    if promotion_id is None:
        await state.clear()
        await message.answer("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
        return

    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        updated = await promotion_service.update_promotion(
            session,
            user_id=user.id,
            promotion_id=promotion_id,
            promotion_date=chosen_date,
        )
    await state.clear()
    if updated is None:
        await message.answer("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
        return
    shown = await _show_promotion_details_message(
        target_message=message,
        session_maker=session_maker,
        telegram_user=message.from_user,
        settings=settings,
        promotion_id=promotion_id,
        edit=False,
    )
    if not shown:
        await message.answer("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))


@router.callback_query(F.data.startswith("promotion:delete:"))
async def promotion_delete_prompt(callback: CallbackQuery) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    promotion_id = int(raw_id)
    await callback.message.edit_text(
        "Delete this upgrade?",
        reply_markup=confirm_delete_promotion_keyboard(promotion_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promotion:delete_confirm:"))
async def promotion_delete_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    promotion_id = int(raw_id)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        deleted = await promotion_service.delete_promotion(session, user_id=user.id, promotion_id=promotion_id)
    await state.clear()
    if not deleted:
        await callback.message.edit_text("Upgrade not found", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
        await callback.answer()
        return
    await callback.message.edit_text("🗑️ Upgrade deleted", reply_markup=prompt_keyboard(back_callback="me:upgrades"))
    await callback.answer()


@router.callback_query(F.data.startswith("custom_date:"))
async def custom_date_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, target = callback.data.split(":", 1)
    await state.update_data(custom_date_target=target)
    await state.set_state(CustomDateFlow.waiting_for_date)
    back_callback = "menu:log_session" if target == "session" else "menu:home"
    await callback.message.edit_text("🗓️ Send date as DD-MM-YYYY", reply_markup=prompt_keyboard(back_callback=back_callback))
    await callback.answer()


@router.callback_query(F.data.startswith("session_date:"))
async def choose_session_date(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, raw_date = callback.data.split(":", 1)
    await _start_session_move_picker(
        state=state,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        raw_date=raw_date,
        callback=callback,
    )


@router.message(CustomDateFlow.waiting_for_date)
async def custom_date_submit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_date = (message.text or "").strip()
    try:
        chosen_date = _parse_user_date(raw_date)
    except ValueError:
        await message.answer("Use DD-MM-YYYY", reply_markup=prompt_keyboard(back_callback="menu:log_session"))
        return

    data = await state.get_data()
    target = data.get("custom_date_target")
    if target == "session":
        await state.set_state(None)
        await _start_session_move_picker(
            state=state,
            session_maker=session_maker,
            telegram_user=message.from_user,
            raw_date=chosen_date.isoformat(),
            message=message,
        )
        return

    await state.clear()
    await _send_home_menu(message)


@router.callback_query(F.data == "session:recent")
async def session_recent(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    await _render_session_picker(callback, session_maker, data["session_user_id"], state, recent=True)


@router.callback_query(F.data == "session:root")
async def session_root(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    await _render_session_picker(callback, session_maker, data["session_user_id"], state)


@router.callback_query(F.data == "session:return_to_picker")
async def session_return_to_picker(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    await state.set_state(None)
    await _render_session_picker(
        callback,
        session_maker,
        data["session_user_id"],
        state,
        category_code=data.get("current_session_category"),
        recent=bool(data.get("current_session_recent")),
    )


@router.callback_query(F.data.startswith("session:open:"))
async def session_open_category(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    data = await state.get_data()
    await state.update_data(current_session_category=code)
    await _render_session_picker(callback, session_maker, data["session_user_id"], state, category_code=code)


@router.callback_query(F.data.startswith("session:back:"))
async def session_back_category(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, current_code = callback.data.split(":", 2)
    async with session_maker() as session:
        category = await arsenal_service.get_category(session, current_code)
    parent_code = category.parent_code if category else None
    data = await state.get_data()
    await state.update_data(current_session_category=parent_code)
    await _render_session_picker(callback, session_maker, data["session_user_id"], state, category_code=parent_code)


@router.callback_query(F.data.startswith("session:toggle:"))
async def session_toggle_move(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    data = await state.get_data()
    selected = list(data.get("selected_move_ids", []))
    if move_id in selected:
        selected.remove(move_id)
    else:
        selected.append(move_id)
    await state.update_data(selected_move_ids=selected)
    await _render_session_picker(
        callback,
        session_maker,
        data["session_user_id"],
        state,
        category_code=data.get("current_session_category"),
        recent=bool(data.get("current_session_recent")),
    )


@router.callback_query(F.data == "session:add_move")
async def session_add_move(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        add_move_origin="session",
        add_move_category=None,
        add_move_prompt_back="session:return_to_picker",
    )
    await state.set_state(AddMoveFlow.waiting_for_name)
    await callback.message.edit_text("➕ Move name?", reply_markup=prompt_keyboard(back_callback="session:return_to_picker"))
    await callback.answer()


@router.callback_query(F.data == "session:save")
async def session_save(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    async with session_maker() as session:
        if data.get("edit_session_id") is not None:
            training_session = await session_service.update_session(
                session,
                user_id=data["session_user_id"],
                session_id=data["edit_session_id"],
                session_date=date.fromisoformat(data["session_date"]),
                move_ids=data.get("selected_move_ids", []),
            )
            if training_session is None:
                await state.clear()
                await callback.message.edit_text("Session not found", reply_markup=prompt_keyboard(back_callback="menu:log_session"))
                await callback.answer()
                return
        else:
            training_session = await session_service.log_session(
                session,
                user_id=data["session_user_id"],
                session_date=date.fromisoformat(data["session_date"]),
                move_ids=data.get("selected_move_ids", []),
            )
        move_count = await session_service.count_practiced_moves(session, training_session.id)
        progress = await user_service.get_progress(session, data["session_user_id"])
    await state.clear()
    move_label = "move" if move_count == 1 else "moves"
    await callback.message.edit_text(
        f"{'Updated' if data.get('edit_session_id') is not None else 'Logged'} {_history_date(training_session.session_date)}\nTotal sessions: {progress.total_sessions}\nPracticed {move_count} {move_label}",
        reply_markup=session_saved_keyboard(training_session.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:"))
async def paginate_history(callback: CallbackQuery, session_maker: async_sessionmaker[AsyncSession]) -> None:
    _, raw_offset = callback.data.split(":", 1)
    offset = int(raw_offset)
    shown = await _show_session_history_page(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        offset=offset,
    )
    if not shown:
        await callback.answer("Nothing more")
        return
    await callback.answer()


@router.callback_query(F.data.startswith("logged_session:view:"))
async def view_logged_session(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    session_id = int(raw_id)
    await state.clear()
    payload = await _build_session_details(
        session_maker=session_maker,
        telegram_user=callback.from_user,
        session_id=session_id,
    )
    if payload is None:
        await callback.answer("Session not found", show_alert=True)
        return
    text, resolved_session_id = payload
    await callback.message.edit_text(text, reply_markup=session_details_keyboard(resolved_session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("logged_session:date:"))
async def edit_logged_session_date(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    session_id = int(raw_id)
    await state.update_data(edit_session_id=session_id)
    await state.set_state(EditSessionFlow.waiting_for_date)
    await callback.message.edit_text(
        "🗓️ Send date as DD-MM-YYYY",
        reply_markup=prompt_keyboard(back_callback=f"logged_session:view:{session_id}"),
    )
    await callback.answer()


@router.message(EditSessionFlow.waiting_for_date)
async def save_logged_session_date(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_date = (message.text or "").strip()
    try:
        chosen_date = _parse_user_date(raw_date)
    except ValueError:
        session_id = (await state.get_data()).get("edit_session_id")
        await message.answer(
            "Use DD-MM-YYYY",
            reply_markup=prompt_keyboard(back_callback=f"logged_session:view:{session_id}" if session_id else "me:sessions"),
        )
        return
    data = await state.get_data()
    session_id = data.get("edit_session_id")
    if session_id is None:
        await state.clear()
        await message.answer("Session not found", reply_markup=prompt_keyboard(back_callback="me:sessions"))
        return
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        updated = await session_service.update_session(
            session,
            user_id=user.id,
            session_id=session_id,
            session_date=chosen_date,
        )
    await state.clear()
    if updated is None:
        await message.answer("Session not found", reply_markup=prompt_keyboard(back_callback="me:sessions"))
        return
    payload = await _build_session_details(
        session_maker=session_maker,
        telegram_user=message.from_user,
        session_id=updated.id,
    )
    if payload is None:
        await message.answer("Session not found", reply_markup=prompt_keyboard(back_callback="me:sessions"))
        return
    text, resolved_session_id = payload
    await message.answer(text, reply_markup=session_details_keyboard(resolved_session_id))


@router.callback_query(F.data.startswith("logged_session:moves:"))
async def edit_logged_session_moves(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    session_id = int(raw_id)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        training_session = await session_service.get_session(session, user_id=user.id, session_id=session_id)
        if training_session is None:
            await callback.answer("Session not found", show_alert=True)
            return
        move_ids = await session_service.get_session_move_ids(session, user_id=user.id, session_id=session_id)
    await state.update_data(
        edit_session_id=session_id,
        session_user_id=user.id,
        session_date=training_session.session_date.isoformat(),
        selected_move_ids=move_ids,
        current_session_category=None,
        current_session_recent=False,
    )
    await _render_session_picker(callback, session_maker, user.id, state)


@router.callback_query(F.data.startswith("logged_session:delete:"))
async def delete_logged_session_prompt(callback: CallbackQuery) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    session_id = int(raw_id)
    await callback.message.edit_text(
        "Delete this session?",
        reply_markup=confirm_delete_session_keyboard(session_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("logged_session:delete_confirm:"))
async def delete_logged_session_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    session_id = int(raw_id)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        deleted = await session_service.delete_session(session, user_id=user.id, session_id=session_id)
        progress = await user_service.get_progress(session, user.id)
    await state.clear()
    if not deleted:
        await callback.message.edit_text("Session not found", reply_markup=prompt_keyboard(back_callback="me:sessions"))
        await callback.answer()
        return
    await callback.message.edit_text(
        f"🗑️ Session deleted\nTotal sessions: {progress.total_sessions}",
        reply_markup=prompt_keyboard(back_callback="me:sessions"),
    )
    await callback.answer()


@router.message(F.text == "Library")
async def arsenal_browse_groups(message: Message, session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        categories = await arsenal_service.list_child_categories(session, None, user_id=user.id)
    await message.answer(
        "📚 Library",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=None,
            open_action="arsenal:browse",
            back_action="arsenal:back",
            root_back_callback="menu:arsenal",
        ),
    )


@router.callback_query(F.data == "arsenal:home")
async def arsenal_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🥋 Arsenal", reply_markup=arsenal_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "arsenal:add")
async def arsenal_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(add_move_origin="arsenal", add_move_prompt_back="arsenal:home")
    await state.set_state(AddMoveFlow.waiting_for_name)
    await callback.message.edit_text("➕ Move name?", reply_markup=prompt_keyboard(back_callback="arsenal:home"))
    await callback.answer()


@router.message(F.text == "Add Move")
async def arsenal_add(message: Message, state: FSMContext) -> None:
    await state.update_data(add_move_origin="arsenal", add_move_prompt_back="arsenal:home")
    await state.set_state(AddMoveFlow.waiting_for_name)
    await message.answer("➕ Move name?", reply_markup=prompt_keyboard(back_callback="arsenal:home"))


@router.message(AddMoveFlow.waiting_for_name)
async def add_move_name(message: Message, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    raw_name = (message.text or "").strip()
    if not raw_name:
        back_callback = (await state.get_data()).get("add_move_prompt_back", "arsenal:home")
        await message.answer("Send a move name", reply_markup=prompt_keyboard(back_callback=back_callback))
        return
    data = await state.get_data()
    await state.update_data(add_move_name=raw_name)
    if data.get("add_move_category"):
        await state.set_state(AddMoveFlow.waiting_for_note)
        await message.answer(
            "📝 Any note? Send one line or type skip",
            reply_markup=prompt_keyboard(back_callback=data.get("add_move_prompt_back", "arsenal:home")),
        )
        return
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        categories = await arsenal_service.list_child_categories(session, None, user_id=user.id)
    await state.set_state(AddMoveFlow.waiting_for_category)
    root_back = "session:return_to_picker" if data.get("add_move_origin") == "session" else "arsenal:home"
    await message.answer(
        "🗂️ Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=None,
            open_action="pickcat:open",
            back_action="pickcat:back",
            root_back_callback=root_back,
            select_leaf_action="pickcat:select",
        ),
    )


@router.callback_query(F.data.startswith("pickcat:open"))
async def pick_category_open(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        categories = await arsenal_service.list_child_categories(session, code, user_id=user.id)
        category = await arsenal_service.get_category(session, code)
    await state.set_state(AddMoveFlow.waiting_for_category)
    data = await state.get_data()
    root_back = "session:return_to_picker" if data.get("add_move_origin") == "session" else "arsenal:home"
    await callback.message.edit_text(
        category.name if category else "🗂️ Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=code,
            open_action="pickcat:open",
            back_action="pickcat:back",
            root_back_callback=root_back,
            select_leaf_action="pickcat:select",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pickcat:back"))
async def pick_category_back(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        category = await arsenal_service.get_category(session, code)
        parent_code = category.parent_code if category else None
        categories = await arsenal_service.list_child_categories(session, parent_code, user_id=user.id)
    await state.set_state(AddMoveFlow.waiting_for_category)
    data = await state.get_data()
    root_back = "session:return_to_picker" if data.get("add_move_origin") == "session" else "arsenal:home"
    await callback.message.edit_text(
        "🗂️ Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=parent_code,
            open_action="pickcat:open",
            back_action="pickcat:back",
            root_back_callback=root_back,
            select_leaf_action="pickcat:select",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pickcat:select"))
async def pick_category_select(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, code = callback.data.split(":", 2)
    await state.update_data(add_move_category=code, add_move_prompt_back=f"pickcat:back:{code}")
    await state.set_state(AddMoveFlow.waiting_for_note)
    await callback.message.edit_text(
        "📝 Any note? Send one line or type skip",
        reply_markup=prompt_keyboard(back_callback=f"pickcat:back:{code}"),
    )
    await callback.answer()


@router.message(AddMoveFlow.waiting_for_note)
async def add_move_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if note.lower() == "skip":
        note = ""
    await state.update_data(add_move_note=note)
    await state.set_state(AddMoveFlow.waiting_for_tags)
    back_callback = (await state.get_data()).get("add_move_prompt_back", "arsenal:home")
    await message.answer(
        "🔖 Any tags? Send comma-separated tags or type skip",
        reply_markup=prompt_keyboard(back_callback=back_callback),
    )


@router.message(AddMoveFlow.waiting_for_tags)
async def finalize_move_creation(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_tags = (message.text or "").strip()
    tags = [] if raw_tags.lower() == "skip" else arsenal_service.normalize_tags(raw_tags)
    data = await state.get_data()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        move = await arsenal_service.create_move(
            session,
            user_id=user.id,
            name=data["add_move_name"],
            category_code=data["add_move_category"],
            note=data.get("add_move_note", ""),
            tags=tags,
        )
    origin = data.get("add_move_origin")
    if origin == "session":
        selected = list(data.get("selected_move_ids", []))
        if move.id not in selected:
            selected.append(move.id)
        category_code = data.get("add_move_category")
        await state.update_data(
            selected_move_ids=selected,
            current_session_category=category_code,
            current_session_recent=False,
            add_move_origin=None,
            add_move_name=None,
            add_move_category=None,
            add_move_note=None,
        )
        await state.set_state(None)
        label, keyboard = await _build_session_picker_markup(
            session_maker=session_maker,
            user_id=user.id,
            state=state,
            category_code=category_code,
        )
        await message.answer(f"Added {move.name} and selected it\n{label}", reply_markup=keyboard)
        return
    await state.clear()
    await message.answer(f"Added {move.name}", reply_markup=arsenal_menu_keyboard())


@router.message(F.text == "Search")
async def arsenal_search_start(message: Message, state: FSMContext) -> None:
    await state.set_state(MoveSearchFlow.waiting_for_query)
    await message.answer("🔎 Search by move name", reply_markup=prompt_keyboard(back_callback="arsenal:home"))


@router.callback_query(F.data == "arsenal:search")
async def arsenal_search_start_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(MoveSearchFlow.waiting_for_query)
    await callback.message.edit_text("🔎 Search by move name", reply_markup=prompt_keyboard(back_callback="arsenal:home"))
    await callback.answer()


@router.message(MoveSearchFlow.waiting_for_query)
async def arsenal_search_query(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Send a move name", reply_markup=prompt_keyboard(back_callback="arsenal:home"))
        return
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        moves = await arsenal_service.search_moves(session, user.id, query)
    await state.clear()
    if not moves:
        await message.answer("No matches", reply_markup=arsenal_menu_keyboard())
        return
    await message.answer(
        "🔎 Matches",
        reply_markup=moves_keyboard("move:view", [(move.id, move.name) for move in moves], back_callback="arsenal:home"),
    )


@router.callback_query(F.data.startswith("arsenal:browse"))
async def browse_arsenal(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    parts = callback.data.split(":")
    category_code = None if parts[-1] == "root" else parts[-1]
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
    await _render_arsenal_browser(callback, session_maker, user.id, category_code)


@router.callback_query(F.data.startswith("arsenal:back"))
async def browse_arsenal_back(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        category = await arsenal_service.get_category(session, code)
        parent_code = category.parent_code if category else None
        user = await user_service.ensure_user(session, callback.from_user)
    await _render_arsenal_browser(callback, session_maker, user.id, parent_code)


@router.message(F.text == "Recent Moves")
async def arsenal_recent(message: Message, session_maker: async_sessionmaker[AsyncSession]) -> None:
    shown = await _show_recent_moves(
        target_message=message,
        session_maker=session_maker,
        telegram_user=message.from_user,
        edit=False,
    )
    if not shown:
        await message.answer("No moves yet", reply_markup=arsenal_menu_keyboard())


@router.callback_query(F.data == "arsenal:recent")
async def arsenal_recent_callback(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    await state.clear()
    shown = await _show_recent_moves(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
    )
    if not shown:
        await callback.message.edit_text("No moves yet", reply_markup=arsenal_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("move:view:"))
async def move_details(callback: CallbackQuery, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    await state.clear()
    shown = await _show_move_details_message(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        move_id=move_id,
    )
    if not shown:
        await callback.answer("Move not found", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("move:edit:"))
async def move_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    await state.update_data(edit_move_id=move_id)
    await callback.message.edit_text("✏️ Choose what to edit", reply_markup=move_edit_keyboard(move_id))
    await callback.answer()


@router.callback_query(F.data.startswith("move:edit_name:"))
async def start_move_name_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    await state.update_data(edit_move_id=int(raw_id))
    await state.set_state(EditMoveFlow.waiting_for_name)
    await callback.message.edit_text("🏷️ Send the new name", reply_markup=prompt_keyboard(back_callback=f"move:view:{raw_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("move:edit_tags:"))
async def start_move_tags_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    await state.update_data(edit_move_id=int(raw_id))
    await state.set_state(EditMoveFlow.waiting_for_tags)
    await callback.message.edit_text(
        "🔖 Send comma-separated tags or type skip",
        reply_markup=prompt_keyboard(back_callback=f"move:view:{raw_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("move:edit_note:"))
async def start_move_note_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    await state.update_data(edit_move_id=int(raw_id))
    await state.set_state(EditMoveFlow.waiting_for_note)
    await callback.message.edit_text("📝 Send the new note", reply_markup=prompt_keyboard(back_callback=f"move:view:{raw_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("move:edit_group:"))
async def start_move_group_edit(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    await state.update_data(edit_move_id=move_id)
    await state.set_state(EditMoveFlow.waiting_for_category)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        categories = await arsenal_service.list_child_categories(session, None, user_id=user.id)
    await callback.message.edit_text(
        "🗂️ Pick a new group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=None,
            open_action="movegroup:open",
            back_action="movegroup:back",
            root_back_callback=f"move:view:{move_id}",
            select_leaf_action="movegroup:select",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("movegroup:open:"))
async def move_group_open(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        categories = await arsenal_service.list_child_categories(session, code, user_id=user.id)
        category = await arsenal_service.get_category(session, code)
    move_id = (await state.get_data()).get("edit_move_id")
    await callback.message.edit_text(
        category.name if category else "🗂️ Pick a new group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=code,
            open_action="movegroup:open",
            back_action="movegroup:back",
            root_back_callback=f"move:view:{move_id}" if move_id else "arsenal:home",
            select_leaf_action="movegroup:select",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("movegroup:back:"))
async def move_group_back(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        category = await arsenal_service.get_category(session, code)
        parent_code = category.parent_code if category else None
        categories = await arsenal_service.list_child_categories(session, parent_code, user_id=user.id)
    move_id = (await state.get_data()).get("edit_move_id")
    await callback.message.edit_text(
        "🗂️ Pick a new group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=parent_code,
            open_action="movegroup:open",
            back_action="movegroup:back",
            root_back_callback=f"move:view:{move_id}" if move_id else "arsenal:home",
            select_leaf_action="movegroup:select",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("movegroup:select:"))
async def move_group_select(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    data = await state.get_data()
    move_id = data.get("edit_move_id")
    if move_id is None:
        await state.clear()
        await callback.message.edit_text("Move not found", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        move = await arsenal_service.update_move(
            session,
            user_id=user.id,
            move_id=move_id,
            category_code=code,
        )
    await state.clear()
    if move is None:
        await callback.message.edit_text("Move not found", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    shown = await _show_move_details_message(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        move_id=move.id,
    )
    if not shown:
        await callback.message.edit_text("Move not found", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    await callback.answer("Group saved")


@router.callback_query(F.data.startswith("move:delete:"))
async def delete_move_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    await state.update_data(edit_move_id=move_id)
    await callback.message.edit_text("Delete this move?", reply_markup=confirm_delete_move_keyboard(move_id))
    await callback.answer()


@router.callback_query(F.data.startswith("move:delete_confirm:"))
async def delete_move_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        deleted = await arsenal_service.delete_move(session, user_id=user.id, move_id=move_id)
    await state.clear()
    if not deleted:
        await callback.message.edit_text("Move not found", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    await callback.message.edit_text("🗑️ Move deleted", reply_markup=arsenal_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "move:edit_cancel")
async def cancel_move_edit(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    move_id = data.get("edit_move_id")
    await state.clear()
    if move_id is None:
        await callback.message.edit_text("🥋 Arsenal", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    shown = await _show_move_details_message(
        target_message=callback.message,
        session_maker=session_maker,
        telegram_user=callback.from_user,
        move_id=move_id,
    )
    if not shown:
        await callback.message.edit_text("Move not found", reply_markup=arsenal_menu_keyboard())
        await callback.answer()
        return
    await callback.answer()


@router.message(EditMoveFlow.waiting_for_name)
async def save_move_name_edit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    new_name = (message.text or "").strip()
    if not new_name:
        move_id = (await state.get_data()).get("edit_move_id")
        await message.answer(
            "Send a move name",
            reply_markup=prompt_keyboard(back_callback=f"move:view:{move_id}" if move_id else "arsenal:home"),
        )
        return
    data = await state.get_data()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        move = await arsenal_service.update_move(
            session,
            user_id=user.id,
            move_id=data["edit_move_id"],
            name=new_name,
        )
    await state.clear()
    if move is None:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return
    shown = await _show_move_details_message(
        target_message=message,
        session_maker=session_maker,
        telegram_user=message.from_user,
        move_id=move.id,
        edit=False,
    )
    if not shown:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return


@router.message(EditMoveFlow.waiting_for_tags)
async def save_move_tags_edit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    raw_tags = (message.text or "").strip()
    tags = [] if raw_tags.lower() == "skip" else arsenal_service.normalize_tags(raw_tags)
    data = await state.get_data()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        move = await arsenal_service.update_move(
            session,
            user_id=user.id,
            move_id=data["edit_move_id"],
            tags=tags,
        )
    await state.clear()
    if move is None:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return
    shown = await _show_move_details_message(
        target_message=message,
        session_maker=session_maker,
        telegram_user=message.from_user,
        move_id=move.id,
        edit=False,
    )
    if not shown:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return


@router.message(EditMoveFlow.waiting_for_note)
async def save_move_note_edit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        move = await arsenal_service.update_move(
            session,
            user_id=user.id,
            move_id=data["edit_move_id"],
            note=message.text or "",
        )
    await state.clear()
    if move is None:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return
    shown = await _show_move_details_message(
        target_message=message,
        session_maker=session_maker,
        telegram_user=message.from_user,
        move_id=move.id,
        edit=False,
    )
    if not shown:
        await message.answer("Move not found", reply_markup=arsenal_menu_keyboard())
        return


# ---------------------------------------------------------------------------
# Library layout editing (add / delete groups)
# ---------------------------------------------------------------------------

async def _render_libcat_edit(
    target_message,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    parent_slug: str,
) -> None:
    parent_code = None if parent_slug == "root" else parent_slug
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, parent_code, user_id=user_id)
        if parent_code:
            cat = await arsenal_service.get_category(session, parent_code)
            heading = f"✏️ Edit: {cat.name}" if cat else "✏️ Edit Layout"
            back_callback = f"libcat:edit:{cat.parent_code}" if cat and cat.parent_code else "libcat:edit:root"
        else:
            heading = "✏️ Edit Layout"
            back_callback = "menu:arsenal"
    await target_message.edit_text(
        heading,
        reply_markup=library_edit_keyboard(
            category_nodes=categories,
            parent_slug=parent_slug,
            back_callback=back_callback,
        ),
    )


@router.callback_query(F.data.startswith("libcat:edit:"))
async def libcat_edit_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, slug = callback.data.split(":", 2)
    async with session_maker() as session:
        u = await user_service.ensure_user(session, callback.from_user)
    await state.clear()
    await _render_libcat_edit(callback.message, session_maker, u.id, slug)
    await callback.answer()


@router.callback_query(F.data.startswith("libcat:add:"))
async def libcat_add_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    _, _, parent_slug = callback.data.split(":", 2)
    await state.clear()
    await state.update_data(libcat_parent_slug=parent_slug)
    await state.set_state(LibCatFlow.waiting_for_name)
    await callback.message.edit_text(
        "➕ Group name?",
        reply_markup=prompt_keyboard(back_callback=f"libcat:edit:{parent_slug}"),
    )
    await callback.answer()


@router.message(LibCatFlow.waiting_for_name)
async def libcat_add_name(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    name = (message.text or "").strip()
    if not name:
        data = await state.get_data()
        parent_slug = data.get("libcat_parent_slug", "root")
        await message.answer(
            "Send a group name",
            reply_markup=prompt_keyboard(back_callback=f"libcat:edit:{parent_slug}"),
        )
        return
    data = await state.get_data()
    parent_slug = data.get("libcat_parent_slug", "root")
    parent_code = None if parent_slug == "root" else parent_slug
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        await arsenal_service.create_category(session, name=name, parent_code=parent_code)
        categories = await arsenal_service.list_child_categories(session, parent_code, user_id=user.id)
        if parent_code:
            cat = await arsenal_service.get_category(session, parent_code)
            heading = f"✏️ Edit: {cat.name}" if cat else "✏️ Edit Layout"
            back_callback = f"libcat:edit:{cat.parent_code}" if cat and cat.parent_code else "libcat:edit:root"
        else:
            heading = "✏️ Edit Layout"
            back_callback = "menu:arsenal"
    await state.clear()
    await message.answer(
        heading,
        reply_markup=library_edit_keyboard(
            category_nodes=categories,
            parent_slug=parent_slug,
            back_callback=back_callback,
        ),
    )


@router.callback_query(F.data.startswith("libcat:delete:"))
async def libcat_delete_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        cat = await arsenal_service.get_category(session, code)
    if cat is None:
        await callback.answer("Group not found")
        return
    parent_slug = cat.parent_code or "root"
    await state.update_data(libcat_delete_parent_slug=parent_slug)
    await callback.message.edit_text(
        f"Delete group \"{cat.name}\"?\nThis will also delete all moves and sub-groups inside it.",
        reply_markup=confirm_delete_category_keyboard(code, back_callback=f"libcat:edit:{parent_slug}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("libcat:delete_confirm:"))
async def libcat_delete_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    data = await state.get_data()
    parent_slug = data.get("libcat_delete_parent_slug", "root")
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        await arsenal_service.delete_category(session, code)
    await state.clear()
    await _render_libcat_edit(callback.message, session_maker, user.id, parent_slug)
    await callback.answer("Deleted")
