from aiogram.fsm.state import State, StatesGroup


class PrintStates(StatesGroup):
    pages = State()


class ScanStates(StatesGroup):
    session = State()
