from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bjj_bot.config import Settings
from bjj_bot.keyboards import (
    arsenal_root_keyboard,
    category_picker_keyboard,
    date_picker_keyboard,
    history_keyboard,
    main_menu_keyboard,
    move_details_keyboard,
    moves_keyboard,
    promotion_keyboard,
    session_builder_keyboard,
)
from bjj_bot.services import arsenal as arsenal_service
from bjj_bot.services import history as history_service
from bjj_bot.services import promotions as promotion_service
from bjj_bot.services import sessions as session_service
from bjj_bot.services import users as user_service
from bjj_bot.states import AddMoveFlow, EditMoveNoteFlow, MoveSearchFlow
from bjj_bot.visuals import get_rank_visual


router = Router()


def _short_date(value: date) -> str:
    return value.strftime("%b %d, %Y")


async def _load_user_context(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telegram_user,
):
    async with session_maker() as session:
        user = await user_service.ensure_user(session, telegram_user)
        progress = await user_service.get_progress(session, user.id)
    return user, progress


async def _send_rank_snapshot(message: Message, settings: Settings, belt: str, stripes: int, total_sessions: int) -> None:
    visual = get_rank_visual(belt, stripes, settings.rank_stickers)
    if visual.sticker_id:
        await message.answer_sticker(visual.sticker_id)
    await message.answer(f"{visual.text}\nsessions: {total_sessions}", reply_markup=main_menu_keyboard())


async def _render_session_picker(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    state: FSMContext,
    category_code: str | None = None,
    recent: bool = False,
) -> None:
    data = await state.get_data()
    selected_ids = set(data.get("selected_move_ids", []))
    await state.update_data(current_session_category=category_code, current_session_recent=recent)
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, category_code)
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
        )
    label = "Pick practiced moves"
    if category_code:
        label = "Pick practiced moves in this group"
    await callback.message.edit_text(label, reply_markup=keyboard)
    await callback.answer()


async def _render_arsenal_browser(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    category_code: str | None,
) -> None:
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, category_code)
        if category_code:
            moves = await arsenal_service.list_moves_in_category(session, user_id, category_code)
            move_rows = [(move.id, move.name) for move in moves]
            category = await arsenal_service.get_category(session, category_code)
            heading = category.name if category else "Arsenal"
            if move_rows:
                await callback.message.edit_text(heading, reply_markup=moves_keyboard("move:view", move_rows))
                await callback.answer()
                return
        keyboard = category_picker_keyboard(
            category_nodes=categories,
            current_code=category_code,
            use_action="arsenal:noop",
            open_action="arsenal:browse",
            back_action="arsenal:back",
        )
    await callback.message.edit_text("Browse your groups", reply_markup=keyboard)
    await callback.answer()


@router.message(F.text == "/start")
async def start(message: Message, session_maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    user, progress = await _load_user_context(session_maker=session_maker, telegram_user=message.from_user)
    await message.answer("Ready", reply_markup=main_menu_keyboard())
    await _send_rank_snapshot(message, settings, progress.belt, progress.stripes, progress.total_sessions)


@router.message(F.text == "My Progress")
async def my_progress(message: Message, session_maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    user, progress = await _load_user_context(session_maker=session_maker, telegram_user=message.from_user)
    async with session_maker() as session:
        history = await history_service.get_history(session, user_id=user.id, limit=1)
    latest = history[0].text if history else "no activity yet"
    visual = get_rank_visual(progress.belt, progress.stripes, settings.rank_stickers)
    if visual.sticker_id:
        await message.answer_sticker(visual.sticker_id)
    await message.answer(
        f"{visual.text}\nsessions: {progress.total_sessions}\nlatest: {latest}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == "Upgrade")
async def upgrade_menu(message: Message) -> None:
    await message.answer("What changed?", reply_markup=promotion_keyboard())


@router.callback_query(F.data.startswith("upgrade:"))
async def choose_upgrade(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    _prefix, kind = callback.data.split(":", 1)
    await state.update_data(promotion_kind=kind)
    await callback.message.edit_text("When did it happen?", reply_markup=date_picker_keyboard("promotion_date"))
    await callback.answer()


@router.callback_query(F.data.startswith("promotion_date:"))
async def apply_upgrade(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    _, raw_date = callback.data.split(":", 1)
    data = await state.get_data()
    kind = data.get("promotion_kind")
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        try:
            promotion = await promotion_service.apply_promotion(
                session,
                user_id=user.id,
                promotion_date=date.fromisoformat(raw_date),
                kind=kind,
            )
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        progress = await user_service.get_progress(session, user.id)

    visual = get_rank_visual(progress.belt, progress.stripes, settings.rank_stickers)
    if visual.sticker_id:
        await callback.message.answer_sticker(visual.sticker_id)
    await callback.message.answer(
        f"{visual.text}\nlogged on {_short_date(promotion.promotion_date)} at session {promotion.session_number}",
        reply_markup=main_menu_keyboard(),
    )
    await state.update_data(promotion_kind=None)
    await callback.answer()


@router.message(F.text == "Log Session")
async def start_session_log(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Which day?", reply_markup=date_picker_keyboard("session_date"))


@router.callback_query(F.data.startswith("session_date:"))
async def choose_session_date(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, raw_date = callback.data.split(":", 1)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
    await state.update_data(session_date=raw_date, selected_move_ids=[], session_user_id=user.id)
    await _render_session_picker(callback, session_maker, user.id, state)


@router.callback_query(F.data == "session:recent")
async def session_recent(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    await _render_session_picker(callback, session_maker, data["session_user_id"], state, recent=True)


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
    await state.update_data(add_move_origin="session")
    await state.set_state(AddMoveFlow.waiting_for_name)
    await callback.message.answer("New move name?")
    await callback.answer()


@router.callback_query(F.data == "session:save")
async def session_save(
    callback: CallbackQuery,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    async with session_maker() as session:
        training_session = await session_service.log_session(
            session,
            user_id=data["session_user_id"],
            session_date=date.fromisoformat(data["session_date"]),
            move_ids=data.get("selected_move_ids", []),
        )
        move_count = await session_service.count_practiced_moves(session, training_session.id)
        progress = await user_service.get_progress(session, data["session_user_id"])
    await state.clear()
    await callback.message.answer(
        f"Logged {_short_date(training_session.session_date)}\nsessions: {progress.total_sessions}\nmoves: {move_count}",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.message(F.text == "History")
async def show_history(message: Message, session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        items = await history_service.get_history(session, user_id=user.id, offset=0, limit=10)
    if not items:
        await message.answer("No history yet", reply_markup=main_menu_keyboard())
        return
    text = "\n".join(f"{_short_date(item.date)} · {item.text}" for item in items)
    await message.answer(text, reply_markup=history_keyboard(10))


@router.callback_query(F.data.startswith("history:"))
async def paginate_history(callback: CallbackQuery, session_maker: async_sessionmaker[AsyncSession]) -> None:
    _, raw_offset = callback.data.split(":", 1)
    offset = int(raw_offset)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        items = await history_service.get_history(session, user_id=user.id, offset=offset, limit=10)
    if not items:
        await callback.answer("Nothing more")
        return
    text = "\n".join(f"{_short_date(item.date)} · {item.text}" for item in items)
    await callback.message.answer(text, reply_markup=history_keyboard(offset + 10))
    await callback.answer()


@router.message(F.text == "Arsenal")
async def arsenal_home(message: Message) -> None:
    await message.answer("Your arsenal", reply_markup=arsenal_root_keyboard())


@router.callback_query(F.data == "arsenal:home")
async def arsenal_home_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Your arsenal", reply_markup=arsenal_root_keyboard())
    await callback.answer()


@router.callback_query(F.data == "arsenal:add")
async def arsenal_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(add_move_origin="arsenal")
    await state.set_state(AddMoveFlow.waiting_for_name)
    await callback.message.answer("Move name?")
    await callback.answer()


@router.message(AddMoveFlow.waiting_for_name)
async def add_move_name(message: Message, state: FSMContext, session_maker: async_sessionmaker[AsyncSession]) -> None:
    raw_name = (message.text or "").strip()
    if not raw_name:
        await message.answer("Send a move name")
        return
    await state.update_data(add_move_name=raw_name)
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, None)
    await state.set_state(AddMoveFlow.waiting_for_category)
    await message.answer(
        "Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=None,
            use_action="pickcat:use",
            open_action="pickcat:open",
            back_action="pickcat:back",
        ),
    )


@router.callback_query(F.data.startswith("pickcat:open"))
async def pick_category_open(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        categories = await arsenal_service.list_child_categories(session, code)
        category = await arsenal_service.get_category(session, code)
    await callback.message.edit_text(
        category.name if category else "Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=code,
            use_action="pickcat:use",
            open_action="pickcat:open",
            back_action="pickcat:back",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pickcat:back"))
async def pick_category_back(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        category = await arsenal_service.get_category(session, code)
        parent_code = category.parent_code if category else None
        categories = await arsenal_service.list_child_categories(session, parent_code)
    await callback.message.edit_text(
        "Pick a group",
        reply_markup=category_picker_keyboard(
            category_nodes=categories,
            current_code=parent_code,
            use_action="pickcat:use",
            open_action="pickcat:open",
            back_action="pickcat:back",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pickcat:use"))
async def pick_category_use(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, code = callback.data.split(":", 2)
    await state.update_data(add_move_category=code)
    await state.set_state(AddMoveFlow.waiting_for_note)
    await callback.message.answer("Any note? Send one line or type skip")
    await callback.answer()


@router.message(AddMoveFlow.waiting_for_note)
async def add_move_note(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    if note.lower() == "skip":
        note = ""
    await state.update_data(add_move_note=note)
    await state.set_state(AddMoveFlow.waiting_for_tags)
    await message.answer("Any tags? Send comma-separated tags or type skip")


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
        selected.append(move.id)
        await state.update_data(selected_move_ids=selected)
        await state.set_state(None)
        await message.answer(f"Added {move.name} and selected it")
        return
    await state.clear()
    await message.answer(f"Added {move.name}", reply_markup=arsenal_root_keyboard())


@router.callback_query(F.data == "arsenal:search")
async def arsenal_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MoveSearchFlow.waiting_for_query)
    await callback.message.answer("Search by move name")
    await callback.answer()


@router.message(MoveSearchFlow.waiting_for_query)
async def arsenal_search_query(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Send a move name")
        return
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        moves = await arsenal_service.search_moves(session, user.id, query)
    await state.clear()
    if not moves:
        await message.answer("No matches", reply_markup=arsenal_root_keyboard())
        return
    await message.answer(
        "Matches",
        reply_markup=moves_keyboard("move:view", [(move.id, move.name) for move in moves]),
    )


@router.callback_query(F.data.startswith("arsenal:browse"))
async def browse_arsenal(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    parts = callback.data.split(":")
    category_code = None if parts[-1] == "root" else parts[-1]
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
    await _render_arsenal_browser(callback, session_maker, user.id, category_code)


@router.callback_query(F.data.startswith("arsenal:back"))
async def browse_arsenal_back(
    callback: CallbackQuery,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    _, _, code = callback.data.split(":", 2)
    async with session_maker() as session:
        category = await arsenal_service.get_category(session, code)
        parent_code = category.parent_code if category else None
        user = await user_service.ensure_user(session, callback.from_user)
    await _render_arsenal_browser(callback, session_maker, user.id, parent_code)


@router.callback_query(F.data == "arsenal:recent")
async def arsenal_recent(callback: CallbackQuery, session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        moves = await arsenal_service.list_recent_moves(session, user.id)
    if not moves:
        await callback.answer("No moves yet")
        return
    await callback.message.edit_text(
        "Recent moves",
        reply_markup=moves_keyboard("move:view", [(move.id, move.name) for move in moves]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("move:view:"))
async def move_details(callback: CallbackQuery, session_maker: async_sessionmaker[AsyncSession]) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    move_id = int(raw_id)
    async with session_maker() as session:
        user = await user_service.ensure_user(session, callback.from_user)
        move = await arsenal_service.get_move(session, user.id, move_id)
        if move is None:
            await callback.answer("Move not found", show_alert=True)
            return
        category = await arsenal_service.get_category(session, move.category_code)
    await callback.message.edit_text(
        arsenal_service.format_move_details(move, category.name if category else None),
        reply_markup=move_details_keyboard(move.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("move:note:"))
async def start_note_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id = callback.data.split(":", 2)
    await state.update_data(edit_move_id=int(raw_id))
    await state.set_state(EditMoveNoteFlow.waiting_for_note)
    await callback.message.answer("Send the new note")
    await callback.answer()


@router.message(EditMoveNoteFlow.waiting_for_note)
async def save_note_edit(
    message: Message,
    state: FSMContext,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    async with session_maker() as session:
        user = await user_service.ensure_user(session, message.from_user)
        move = await arsenal_service.update_move_note(
            session,
            user_id=user.id,
            move_id=data["edit_move_id"],
            note=message.text or "",
        )
    await state.clear()
    if move is None:
        await message.answer("Move not found", reply_markup=arsenal_root_keyboard())
        return
    await message.answer("Note saved", reply_markup=arsenal_root_keyboard())
