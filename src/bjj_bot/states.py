from aiogram.fsm.state import State, StatesGroup


class AddMoveFlow(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_note = State()
    waiting_for_tags = State()


class EditMoveNoteFlow(StatesGroup):
    waiting_for_note = State()


class EditMoveFlow(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_tags = State()
    waiting_for_note = State()


class EditSessionFlow(StatesGroup):
    waiting_for_date = State()


class EditPromotionFlow(StatesGroup):
    waiting_for_date = State()


class MoveSearchFlow(StatesGroup):
    waiting_for_query = State()


class CustomDateFlow(StatesGroup):
    waiting_for_date = State()


class RankEmojiCaptureFlow(StatesGroup):
    waiting_for_custom_emoji = State()
