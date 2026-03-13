from aiogram.fsm.state import State, StatesGroup


class AddMoveFlow(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_note = State()
    waiting_for_tags = State()


class EditMoveNoteFlow(StatesGroup):
    waiting_for_note = State()


class MoveSearchFlow(StatesGroup):
    waiting_for_query = State()
