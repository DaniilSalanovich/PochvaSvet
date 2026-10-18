"""Telegram-бот «ПочваСвет»: интерактивная брошюра по результатам тестов почвы.

Запуск:
    pip install -r requirements.txt
    export BOT_TOKEN=123456:ABC...          # токен от @BotFather
    export WEBAPP_URL=https://.../index.html  # необязательно: адрес мини-приложения
    python bot.py

Вся логика экранов — в screens.py, правила — в rules.json, расчёты — в engine.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           MenuButtonWebApp, Message, WebAppInfo)

import screens as S

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL") or None

router = Router()


class Calc(StatesGroup):
    dose = State()


# ---------- утилиты ----------

def kb(rows: list[list[tuple]]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows:
        buttons = []
        for text, action in row:
            if isinstance(action, dict) and "web_app" in action:
                buttons.append(InlineKeyboardButton(text=text, web_app=WebAppInfo(url=action["web_app"])))
            else:
                buttons.append(InlineKeyboardButton(text=text, callback_data=action))
        keyboard.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def show(target: Message | CallbackQuery, screen: S.Screen, edit: bool = True) -> None:
    markup = kb(screen.buttons) if screen.buttons else None
    if isinstance(target, CallbackQuery):
        await target.answer()
        if edit:
            try:
                await target.message.edit_text(screen.text, reply_markup=markup)
                return
            except Exception:  # сообщение нельзя изменить (слишком старое и т. п.)
                pass
        await target.message.answer(screen.text, reply_markup=markup)
    else:
        await target.answer(screen.text, reply_markup=markup)


# ---------- меню ----------

@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show(message, S.main_menu(WEBAPP_URL))


@router.message(Command("brochure"))
async def cmd_brochure(message: Message) -> None:
    await show(message, S.brochure_root())


@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext) -> None:
    await state.set_data({"answers": {}, "q": 0})
    await show(message, S.question_screen(0, {}))


@router.message(Command("calc"))
async def cmd_calc(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show(message, S.calc_ferts())


@router.callback_query(F.data == "m")
async def cb_menu(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(cq, S.main_menu(WEBAPP_URL))


# ---------- брошюра ----------

@router.callback_query(F.data == "b")
async def cb_brochure(cq: CallbackQuery) -> None:
    await show(cq, S.brochure_root())


@router.callback_query(F.data.startswith("bi:"))
async def cb_indicator(cq: CallbackQuery) -> None:
    await show(cq, S.brochure_indicator(cq.data[3:]))


@router.callback_query(F.data.startswith("bl:"))
async def cb_level(cq: CallbackQuery) -> None:
    await show(cq, S.brochure_level(cq.data[3:]))


@router.callback_query(F.data.startswith("bo:"))
async def cb_organics(cq: CallbackQuery) -> None:
    await show(cq, S.brochure_organics(cq.data[3:]))


@router.callback_query(F.data == "bc")
async def cb_combos(cq: CallbackQuery) -> None:
    await show(cq, S.combos_list())


@router.callback_query(F.data.startswith("bk:"))
async def cb_combo(cq: CallbackQuery) -> None:
    await show(cq, S.combo_card(cq.data[3:]))


@router.callback_query(F.data.startswith("bx:"))
async def cb_extra(cq: CallbackQuery) -> None:
    await show(cq, S.extra(cq.data[3:]))


# ---------- мастер «мои результаты» ----------

@router.callback_query(F.data == "w:start")
async def cb_wizard_start(cq: CallbackQuery, state: FSMContext) -> None:
    await state.set_data({"answers": {}, "q": 0})
    await show(cq, S.question_screen(0, {}))


@router.callback_query(F.data == "w:back")
async def cb_wizard_back(cq: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    q = max(0, data.get("q", 0) - 1)
    answers = data.get("answers", {})
    answers.pop(S.QUESTIONS[q]["id"], None)
    await state.update_data(q=q, answers=answers)
    await show(cq, S.question_screen(q, answers))


@router.callback_query(F.data.startswith("w:"))
async def cb_wizard_answer(cq: CallbackQuery, state: FSMContext) -> None:
    _, qid, value = cq.data.split(":", 2)
    data = await state.get_data()
    answers: dict = data.get("answers", {})
    if value != "-":
        answers[qid] = value
    else:
        answers.pop(qid, None)
    q = next(i for i, x in enumerate(S.QUESTIONS) if x["id"] == qid) + 1
    await state.update_data(answers=answers, q=q)
    if q < len(S.QUESTIONS):
        await show(cq, S.question_screen(q, answers))
        return
    await cq.answer("Готовлю рекомендации…")
    messages, buttons = S.run_report(answers, datetime.now().month)
    for i, text in enumerate(messages):
        markup = kb(buttons) if i == len(messages) - 1 else None
        await cq.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("wk:"))
async def cb_report_combo(cq: CallbackQuery) -> None:
    await show(cq, S.combo_card(cq.data[3:], back="m"), edit=False)


# ---------- калькулятор ----------

@router.callback_query(F.data == "c:start")
async def cb_calc(cq: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(cq, S.calc_ferts())


@router.callback_query(F.data.startswith("cf:"))
async def cb_calc_fert(cq: CallbackQuery, state: FSMContext) -> None:
    fert_id = cq.data[3:]
    await state.set_state(Calc.dose)
    await state.update_data(fert=fert_id)
    await show(cq, S.calc_ask_dose(fert_id))


@router.message(StateFilter(Calc.dose))
async def msg_calc_dose(message: Message, state: FSMContext) -> None:
    try:
        dose = float((message.text or "").replace(",", ".").strip())
        if not 0 < dose <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("Напишите дозу числом, например 60.")
        return
    data = await state.get_data()
    await state.set_state(None)
    await show(message, S.calc_ask_area(data["fert"], dose))


@router.callback_query(F.data.startswith("cd:"))
async def cb_calc_dose(cq: CallbackQuery, state: FSMContext) -> None:
    _, fert_id, dose = cq.data.split(":")
    await state.set_state(None)
    await show(cq, S.calc_ask_area(fert_id, float(dose)))


@router.callback_query(F.data.startswith("ca:"))
async def cb_calc_area(cq: CallbackQuery) -> None:
    _, fert_id, dose, area = cq.data.split(":")
    await show(cq, S.calc_result(fert_id, float(dose), float(area)))


# ---------- данные из мини-приложения ----------

@router.message(F.web_app_data)
async def msg_webapp(message: Message) -> None:
    """Мини-приложение, открытое кнопкой клавиатуры, может прислать ответы мастера."""
    import json
    try:
        answers = json.loads(message.web_app_data.data)
    except (ValueError, TypeError):
        return
    messages, buttons = S.run_report(answers, datetime.now().month)
    for i, text in enumerate(messages):
        await message.answer(text, reply_markup=kb(buttons) if i == len(messages) - 1 else None)


@router.message()
async def fallback(message: Message) -> None:
    await show(message, S.main_menu(WEBAPP_URL))


# ---------- запуск ----------

async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Задайте переменную окружения BOT_TOKEN (токен от @BotFather).")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="check", description="Разобрать мои результаты"),
        BotCommand(command="brochure", description="Брошюра по тестам"),
        BotCommand(command="calc", description="Пересчёт дозы удобрения"),
    ])
    if WEBAPP_URL:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Брошюра", web_app=WebAppInfo(url=WEBAPP_URL)))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
