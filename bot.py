import asyncio
import json
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
import gspread
from google.oauth2.service_account import Credentials

BOT_TOKEN = "8908059153:AAEuBbZPYmusgn8_VWu80uXkJagkXN58iE4"
SPREADSHEET_ID = "1p8ODuCSlw75Engag5vndCqrtD0ucxxgxWo05BgwYYA8"
ADMIN_ID = 1745733903

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def get_sheets_client():
    import base64
    # 1. Base64 usuli (eng ishonchli)
    b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
    if b64:
        creds_dict = json.loads(base64.b64decode(b64).decode())
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=SCOPES))
    # 2. JSON string usuli
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if raw:
        raw = raw.strip().replace('\\"', '"')
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        creds_dict = json.loads(raw)
        return gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=SCOPES))
    # 3. Lokal fayl
    return gspread.authorize(Credentials.from_service_account_file("credentials.json", scopes=SCOPES))


def get_or_create_sheet(spreadsheet, name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
        sheet.append_row(headers)
    return sheet


def init_spreadsheet():
    client = get_sheets_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    get_or_create_sheet(sp, "Foydalanuvchilar", ["Telegram_ID", "Ism", "Ro'yxat_sanasi"])
    get_or_create_sheet(sp, "Operatsiyalar", ["Sana", "Telegram_ID", "Ism", "Tur", "Summa", "Izoh", "Qoldiq"])
    return sp


def get_user(user_id: int):
    """Foydalanuvchini topish"""
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Foydalanuvchilar")
        rows = sheet.get_all_values()[1:]
        for row in rows:
            if row and str(row[0]) == str(user_id):
                return {"id": row[0], "ism": row[1]}
        return None
    except Exception:
        return None


def register_user(user_id: int, ism: str):
    """Foydalanuvchini ro'yxatdan o'tkazish"""
    client = get_sheets_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    sheet = sp.worksheet("Foydalanuvchilar")
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    sheet.append_row([str(user_id), ism, sana])


def get_user_qoldiq(user_id: int):
    """Foydalanuvchining shaxsiy qoldig'ini hisoblash"""
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = sheet.get_all_values()[1:]
        qoldiq = 0.0
        for r in rows:
            if len(r) > 4 and str(r[1]) == str(user_id) and r[4]:
                try:
                    qoldiq += float(r[4])
                except ValueError:
                    pass
        return qoldiq
    except Exception:
        return 0.0


def get_all_users_qoldiq():
    """Barcha foydalanuvchilarning qoldiqlari"""
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)

        # Foydalanuvchilar
        f_sheet = sp.worksheet("Foydalanuvchilar")
        users = {}
        for row in f_sheet.get_all_values()[1:]:
            if row:
                users[str(row[0])] = row[1]

        # Operatsiyalar
        o_sheet = sp.worksheet("Operatsiyalar")
        qoldiqlar = {}
        for r in o_sheet.get_all_values()[1:]:
            if len(r) > 4 and r[1] and r[4]:
                uid = str(r[1])
                try:
                    qoldiqlar[uid] = qoldiqlar.get(uid, 0.0) + float(r[4])
                except ValueError:
                    pass

        result = []
        for uid, ism in users.items():
            result.append({"id": uid, "ism": ism, "qoldiq": qoldiqlar.get(uid, 0.0)})
        return result
    except Exception as e:
        log.error("get_all_users_qoldiq xatosi: %s", e)
        return []


# ─── FSM ──────────────────────────────────────────────────────────────────────
class RegisterStates(StatesGroup):
    ism = State()


class KirimStates(StatesGroup):
    summa = State()
    izoh  = State()


class ChiqimStates(StatesGroup):
    summa = State()
    izoh  = State()


# ─── KLAVIATURALAR ────────────────────────────────────────────────────────────
MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Kirim"),   KeyboardButton(text="➖ Chiqim")],
        [KeyboardButton(text="💰 Qoldiq"),  KeyboardButton(text="📊 Hisobot")],
        [KeyboardButton(text="ℹ️ Yordam")],
    ],
    resize_keyboard=True,
)

BEKOR_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Bekor")]],
    resize_keyboard=True,
)

HISOBOT_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📅 Bugungi",  callback_data="h_bugun")],
    [InlineKeyboardButton(text="📆 Oylik",    callback_data="h_oy")],
])

router = Router()


def qoldiq_emoji(q):
    if q > 0: return "🟢"
    if q < 0: return "🔴"
    return "⚪"


# ─── START ────────────────────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(msg: Message, state: FSMContext):
    user = get_user(msg.from_user.id)
    if user:
        qoldiq = get_user_qoldiq(msg.from_user.id)
        await msg.answer(
            f"👋 Salom, <b>{user['ism']}</b>!\n\n"
            f"{qoldiq_emoji(qoldiq)} Sizning qoldig'ingiz: <b>{qoldiq:,.0f} so'm</b>",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    else:
        await state.set_state(RegisterStates.ism)
        await msg.answer(
            "👋 Xush kelibsiz!\n\n"
            "Ro'yxatdan o'tish uchun <b>ism va familiyangizni</b> kiriting:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )


@router.message(RegisterStates.ism)
async def register_ism(msg: Message, state: FSMContext):
    ism = msg.text.strip()
    if len(ism) < 2:
        await msg.answer("⚠️ Iltimos, to'liq ism kiriting:")
        return
    await state.clear()
    try:
        register_user(msg.from_user.id, ism)
        await msg.answer(
            f"✅ <b>{ism}</b>, ro'yxatdan o'tdingiz!\n\n"
            f"Endi o'z kassangizni yurita olasiz.",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}")


# ─── YORDAM ───────────────────────────────────────────────────────────────────
@router.message(F.text == "ℹ️ Yordam")
async def cmd_yordam(msg: Message):
    await msg.answer(
        "📌 <b>Buyruqlar:</b>\n\n"
        "➕ <b>Kirim</b> — kassaga pul kirishi\n"
        "➖ <b>Chiqim</b> — kassadan pul chiqishi\n"
        "💰 <b>Qoldiq</b> — joriy qoldig'ingiz\n"
        "📊 <b>Hisobot</b> — shaxsiy hisobotingiz\n\n"
        "⚠️ Har bir foydalanuvchi faqat o'z kassasini ko'radi.",
        parse_mode="HTML",
    )


# ─── QOLDIQ ───────────────────────────────────────────────────────────────────
@router.message(F.text == "💰 Qoldiq")
async def qoldiq_korish(msg: Message):
    user = get_user(msg.from_user.id)
    if not user:
        await msg.answer("⚠️ Avval /start orqali ro'yxatdan o'ting.")
        return
    qoldiq = get_user_qoldiq(msg.from_user.id)
    await msg.answer(
        f"{qoldiq_emoji(qoldiq)} <b>Sizning qoldig'ingiz: {qoldiq:,.0f} so'm</b>",
        parse_mode="HTML",
    )


# ─── KIRIM ────────────────────────────────────────────────────────────────────
@router.message(F.text == "➕ Kirim")
async def kirim_boshlash(msg: Message, state: FSMContext):
    user = get_user(msg.from_user.id)
    if not user:
        await msg.answer("⚠️ Avval /start orqali ro'yxatdan o'ting.")
        return
    await state.set_state(KirimStates.summa)
    await msg.answer("💵 Kirim summasini kiriting (so'm):", reply_markup=BEKOR_KB)


@router.message(KirimStates.summa, F.text == "❌ Bekor")
@router.message(ChiqimStates.summa, F.text == "❌ Bekor")
async def bekor(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Bekor qilindi.", reply_markup=MAIN_KB)


@router.message(KirimStates.summa)
async def kirim_summa(msg: Message, state: FSMContext):
    text = msg.text.strip().replace(" ", "").replace(",", ".")
    try:
        summa = float(text)
        if summa <= 0: raise ValueError
    except ValueError:
        await msg.answer("⚠️ To'g'ri summa kiriting (masalan: 500000)")
        return
    await state.update_data(summa=summa)
    await state.set_state(KirimStates.izoh)
    await msg.answer("📝 Izoh kiriting (ixtiyoriy — '-' yozing):")


@router.message(KirimStates.izoh)
async def kirim_izoh(msg: Message, state: FSMContext):
    izoh = "" if msg.text.strip() == "-" else msg.text.strip()
    data = await state.get_data()
    await state.clear()
    user = get_user(msg.from_user.id)
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        summa = abs(data["summa"])
        qoldiq_old = get_user_qoldiq(msg.from_user.id)
        yangi_qoldiq = qoldiq_old + summa
        sheet.append_row([sana, str(msg.from_user.id), user["ism"], "Kirim", summa, izoh, yangi_qoldiq])
        await msg.answer(
            f"✅ <b>Kirim saqlandi!</b>\n\n"
            f"💵 Summa: <b>+{summa:,.0f} so'm</b>\n"
            f"📝 Izoh: {izoh or '—'}\n"
            f"🕒 {sana}\n\n"
            f"{qoldiq_emoji(yangi_qoldiq)} Qoldig'ingiz: <b>{yangi_qoldiq:,.0f} so'm</b>",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


# ─── CHIQIM ───────────────────────────────────────────────────────────────────
@router.message(F.text == "➖ Chiqim")
async def chiqim_boshlash(msg: Message, state: FSMContext):
    user = get_user(msg.from_user.id)
    if not user:
        await msg.answer("⚠️ Avval /start orqali ro'yxatdan o'ting.")
        return
    await state.set_state(ChiqimStates.summa)
    await msg.answer("💸 Chiqim summasini kiriting (so'm):", reply_markup=BEKOR_KB)


@router.message(ChiqimStates.summa)
async def chiqim_summa(msg: Message, state: FSMContext):
    text = msg.text.strip().replace(" ", "").replace(",", ".")
    try:
        summa = float(text)
        if summa <= 0: raise ValueError
    except ValueError:
        await msg.answer("⚠️ To'g'ri summa kiriting (masalan: 50000)")
        return
    await state.update_data(summa=summa)
    await state.set_state(ChiqimStates.izoh)
    await msg.answer("📝 Izoh kiriting (ixtiyoriy — '-' yozing):")


@router.message(ChiqimStates.izoh)
async def chiqim_izoh(msg: Message, state: FSMContext):
    izoh = "" if msg.text.strip() == "-" else msg.text.strip()
    data = await state.get_data()
    await state.clear()
    user = get_user(msg.from_user.id)
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        summa = -abs(data["summa"])
        qoldiq_old = get_user_qoldiq(msg.from_user.id)
        yangi_qoldiq = qoldiq_old + summa
        sheet.append_row([sana, str(msg.from_user.id), user["ism"], "Chiqim", summa, izoh, yangi_qoldiq])
        await msg.answer(
            f"✅ <b>Chiqim saqlandi!</b>\n\n"
            f"💸 Summa: <b>{summa:,.0f} so'm</b>\n"
            f"📝 Izoh: {izoh or '—'}\n"
            f"🕒 {sana}\n\n"
            f"{qoldiq_emoji(yangi_qoldiq)} Qoldig'ingiz: <b>{yangi_qoldiq:,.0f} so'm</b>",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


# ─── HISOBOT ──────────────────────────────────────────────────────────────────
@router.message(F.text == "📊 Hisobot")
async def hisobot_menyu(msg: Message):
    user = get_user(msg.from_user.id)
    if not user:
        await msg.answer("⚠️ Avval /start orqali ro'yxatdan o'ting.")
        return
    await msg.answer("📊 Hisobot turini tanlang:", reply_markup=HISOBOT_KB)


@router.callback_query(F.data == "h_bugun")
async def h_bugun(call: CallbackQuery):
    await call.answer()
    user = get_user(call.from_user.id)
    if not user:
        return
    bugun = datetime.now().strftime("%Y-%m-%d")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = [r for r in sheet.get_all_values()[1:]
                if r and r[0].startswith(bugun) and str(r[1]) == str(call.from_user.id)]
        if not rows:
            await call.message.answer("📅 Bugun operatsiya yo'q.")
            return
        kirim = sum(float(r[4]) for r in rows if len(r) > 4 and r[4] and float(r[4]) > 0)
        chiqim = sum(float(r[4]) for r in rows if len(r) > 4 and r[4] and float(r[4]) < 0)
        qoldiq = get_user_qoldiq(call.from_user.id)
        lines = [f"📅 <b>Bugungi hisobot ({bugun}):</b>\n"]
        lines.append(f"➕ Kirim: <b>+{kirim:,.0f} so'm</b>")
        lines.append(f"➖ Chiqim: <b>{chiqim:,.0f} so'm</b>")
        lines.append(f"\n{qoldiq_emoji(qoldiq)} <b>Qoldig'ingiz: {qoldiq:,.0f} so'm</b>")
        lines.append(f"📝 Operatsiyalar: {len(rows)} ta")
        await call.message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik: {e}")


@router.callback_query(F.data == "h_oy")
async def h_oy(call: CallbackQuery):
    await call.answer()
    user = get_user(call.from_user.id)
    if not user:
        return
    oy = datetime.now().strftime("%Y-%m")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = [r for r in sheet.get_all_values()[1:]
                if r and r[0].startswith(oy) and str(r[1]) == str(call.from_user.id)]
        if not rows:
            await call.message.answer(f"📆 {oy} oyida operatsiya yo'q.")
            return
        kirim = sum(float(r[4]) for r in rows if len(r) > 4 and r[4] and float(r[4]) > 0)
        chiqim = sum(float(r[4]) for r in rows if len(r) > 4 and r[4] and float(r[4]) < 0)
        qoldiq = get_user_qoldiq(call.from_user.id)
        lines = [f"📆 <b>Oylik hisobot ({oy}):</b>\n"]
        lines.append(f"➕ Jami kirim: <b>+{kirim:,.0f} so'm</b>")
        lines.append(f"➖ Jami chiqim: <b>{chiqim:,.0f} so'm</b>")
        lines.append(f"📊 Farq: <b>{kirim+chiqim:,.0f} so'm</b>")
        lines.append(f"\n{qoldiq_emoji(qoldiq)} <b>Qoldig'ingiz: {qoldiq:,.0f} so'm</b>")
        lines.append(f"📝 Operatsiyalar: {len(rows)} ta")
        await call.message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik: {e}")


# ─── ADMIN ────────────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Sizga ruxsat yo'q.")
        return
    try:
        users = get_all_users_qoldiq()
        if not users:
            await msg.answer("📋 Hozircha foydalanuvchi yo'q.")
            return
        lines = ["👑 <b>Admin paneli — Barcha qoldiqlar:</b>\n"]
        jami = 0.0
        for u in users:
            q = u["qoldiq"]
            jami += q
            lines.append(f"{qoldiq_emoji(q)} <b>{u['ism']}</b>: {q:,.0f} so'm")
        lines.append(f"\n💰 <b>Umumiy: {jami:,.0f} so'm</b>")
        lines.append(f"👥 Foydalanuvchilar: {len(users)} ta")
        await msg.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Bot ishga tushmoqda...")
    try:
        init_spreadsheet()
        log.info("Google Sheets ulandi.")
    except Exception as e:
        log.warning("Google Sheets ulanmadi: %s", e)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
