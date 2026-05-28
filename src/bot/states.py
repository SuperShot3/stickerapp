from aiogram.fsm.state import State, StatesGroup


class StickerFlow(StatesGroup):
    awaiting_photo = State()
    choosing_style = State()
    editing = State()
    preview = State()
