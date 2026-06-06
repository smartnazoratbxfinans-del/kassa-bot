import asyncio
import logging
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
CREDENTIALS_FILE = "credentials.json"
ALLOWED_USERS: list[int] = []

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def get_sheets_client():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


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
    get_or_create_sheet(sp, "Operatsiyalar", ["Sana", "Tur", "Kategoriya", "Summa", "Izoh", "Qoldiq", "Foydalanuvchi"])
    get_or_create_sheet(sp, "Inventar", ["Mahsulot", "Miqdor", "Birlik", "Narx", "Izoh", "Oxirgi yangilanish"])
    return sp


def get_qoldiq():
    """Joriy qoldiqni hisoblash"""
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = sheet.get_all_values()[1:]
        qoldiq = 0.0
        for r in rows:
            if len(r) > 3 and r[3]:
                try:
                    qoldiq += float(r[3])
                except ValueError:
                    pass
        return qoldiq
    except Exception:
        return 0.0


class KirimStates(StatesGroup):
    kategoriya = State()
    summa      = State()
    izoh       = State()


class ChiqimStates(StatesGroup):
    kategoriya = State()
    summa      = State()
    izoh       = State()


class InventarStates(StatesGroup):
    amal     = State()
    mahsulot = State()
    miqdor   = State()
    birlik   = State()
    narx     = State()
    izoh     = State()


MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Kirim"),        KeyboardButton(text="➖ Chiqim")],
        [KeyboardButton(text="💰 Qoldiq"),       KeyboardButton(text="📊 Hisobot")],
        [KeyboardButton(text="📦 Inventar"),     KeyboardButton(text="ℹ️ Yordam")],
    ],
    resize_keyboard=True,
)

KIRIM_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💵 Ish haqi"),     KeyboardButton(text="🏪 Sotuv")],
        [KeyboardButton(text="🏦 Bank"),          KeyboardButton(text="👤 Investor")],
        [KeyboardButton(text="➕ Boshqa kirim"), KeyboardButton(text="❌ Bekor")],
    ],
    resize_keyboard=True,
)

CHIQIM_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👷 Ish haqi"),     KeyboardButton(text="🛒 Oziq-ovqat")],
        [KeyboardButton(text="🚗 Transport"),    KeyboardButton(text="💡 Kommunal")],
        [KeyboardButton(text="🔧 Ta'mirlash"),   KeyboardButton(text="📦 Ombor")],
        [KeyboardButton(text="➕ Boshqa chiqim"),KeyboardButton(text="❌ Bekor")],
    ],
    resize_keyboard=True,
)

INVENTAR_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Mahsulot qo'shish"), KeyboardButton(text="✏️ Yangilash")],
        [KeyboardButton(text="📋 Ro'yxat ko'rish"),   KeyboardButton(text="❌ Bekor")],
    ],
    resize_keyboard=True,
)

HISOBOT_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📅 Bugungi hisobot",  callback_data="hisobot_bugun")],
    [InlineKeyboardButton(text="📆 Oylik hisobot",    callback_data="hisobot_oy")],
    [InlineKeyboardButton(text="📦 Inventar holati",  callback_data="hisobot_inventar")],
])

router = Router()


def check_user(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS


def qoldiq_emoji(q):
    if q > 0:
        return "🟢"
    elif q < 0:
        return "🔴"
    return "⚪"


@router.message(Command("start"))
async def cmd_start(msg: Message):
    if not check_user(msg.from_user.id):
        await msg.answer("⛔ Sizga ruxsat yo'q.")
        return
    qoldiq = get_qoldiq()
    await msg.answer(
        f"👋 Salom, <b>{msg.from_user.full_name}</b>!\n\n"
        f"🏪 <b>Kassa boshqaruv tizimi</b>\n\n"
        f"{qoldiq_emoji(qoldiq)} Joriy qoldiq: <b>{qoldiq:,.0f} so'm</b>",
        reply_markup=MAIN_KB,
        parse_mode="HTML",
    )


@router.message(F.text == "ℹ️ Yordam")
async def cmd_yordam(msg: Message):
    await msg.answer(
        "📌 <b>Buyruqlar:</b>\n\n"
        "➕ <b>Kirim</b> — kassa ga pul tushishi (sotuv, ish haqi olish...)\n"
        "➖ <b>Chiqim</b> — kassadan pul chiqishi (xarajat, to'lov...)\n"
        "💰 <b>Qoldiq</b> — joriy kassa qoldig'i\n"
        "📊 <b>Hisobot</b> — kunlik/oylik hisobot\n"
        "📦 <b>Inventar</b> — mahsulotlar boshqaruvi",
        parse_mode="HTML",
    )


# ─── QOLDIQ ───────────────────────────────────────────────────────────────────
@router.message(F.text == "💰 Qoldiq")
async def qoldiq_korish(msg: Message):
    if not check_user(msg.from_user.id):
        return
    try:
        qoldiq = get_qoldiq()
        await msg.answer(
            f"{qoldiq_emoji(qoldiq)} <b>Joriy qoldiq: {qoldiq:,.0f} so'm</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}")


# ─── KIRIM ────────────────────────────────────────────────────────────────────
@router.message(F.text == "➕ Kirim")
async def kirim_boshlash(msg: Message, state: FSMContext):
    if not check_user(msg.from_user.id):
        return
    await state.set_state(KirimStates.kategoriya)
    await msg.answer("📂 Kirim kategoriyasini tanlang:", reply_markup=KIRIM_KB)


@router.message(KirimStates.kategoriya, F.text == "❌ Bekor")
@router.message(ChiqimStates.kategoriya, F.text == "❌ Bekor")
@router.message(InventarStates.amal, F.text == "❌ Bekor")
async def bekor_qilish(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Bekor qilindi.", reply_markup=MAIN_KB)


@router.message(KirimStates.kategoriya)
async def kirim_kategoriya(msg: Message, state: FSMContext):
    await state.update_data(kategoriya=msg.text.strip())
    await state.set_state(KirimStates.summa)
    await msg.answer(
        f"✅ Kategoriya: <b>{msg.text.strip()}</b>\n\n"
        f"💵 Kirim summasini kiriting (so'm):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )


@router.message(KirimStates.summa)
async def kirim_summa(msg: Message, state: FSMContext):
    text = msg.text.strip().replace(" ", "").replace(",", ".")
    try:
        summa = float(text)
        if summa <= 0:
            raise ValueError
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
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        # Kirim musbat (+)
        summa = abs(data["summa"])
        qoldiq_old = get_qoldiq()
        yangi_qoldiq = qoldiq_old + summa
        sheet.append_row([sana, "Kirim", data["kategoriya"], summa, izoh, yangi_qoldiq, msg.from_user.full_name])
        await msg.answer(
            f"✅ <b>Kirim saqlandi!</b>\n\n"
            f"📂 Kategoriya: {data['kategoriya']}\n"
            f"💵 Summa: <b>+{summa:,.0f} so'm</b>\n"
            f"📝 Izoh: {izoh or '—'}\n"
            f"🕒 Sana: {sana}\n\n"
            f"{qoldiq_emoji(yangi_qoldiq)} Qoldiq: <b>{yangi_qoldiq:,.0f} so'm</b>",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Sheets xatosi: %s", e)
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


# ─── CHIQIM ───────────────────────────────────────────────────────────────────
@router.message(F.text == "➖ Chiqim")
async def chiqim_boshlash(msg: Message, state: FSMContext):
    if not check_user(msg.from_user.id):
        return
    await state.set_state(ChiqimStates.kategoriya)
    await msg.answer("📂 Chiqim kategoriyasini tanlang:", reply_markup=CHIQIM_KB)


@router.message(ChiqimStates.kategoriya)
async def chiqim_kategoriya(msg: Message, state: FSMContext):
    await state.update_data(kategoriya=msg.text.strip())
    await state.set_state(ChiqimStates.summa)
    await msg.answer(
        f"✅ Kategoriya: <b>{msg.text.strip()}</b>\n\n"
        f"💸 Chiqim summasini kiriting (so'm):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )


@router.message(ChiqimStates.summa)
async def chiqim_summa(msg: Message, state: FSMContext):
    text = msg.text.strip().replace(" ", "").replace(",", ".")
    try:
        summa = float(text)
        if summa <= 0:
            raise ValueError
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
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        # Chiqim manfiy (-)
        summa = -abs(data["summa"])
        qoldiq_old = get_qoldiq()
        yangi_qoldiq = qoldiq_old + summa
        sheet.append_row([sana, "Chiqim", data["kategoriya"], summa, izoh, yangi_qoldiq, msg.from_user.full_name])
        await msg.answer(
            f"✅ <b>Chiqim saqlandi!</b>\n\n"
            f"📂 Kategoriya: {data['kategoriya']}\n"
            f"💸 Summa: <b>{summa:,.0f} so'm</b>\n"
            f"📝 Izoh: {izoh or '—'}\n"
            f"🕒 Sana: {sana}\n\n"
            f"{qoldiq_emoji(yangi_qoldiq)} Qoldiq: <b>{yangi_qoldiq:,.0f} so'm</b>",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        log.error("Sheets xatosi: %s", e)
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


# ─── INVENTAR ─────────────────────────────────────────────────────────────────
@router.message(F.text == "📦 Inventar")
async def inventar_menyu(msg: Message, state: FSMContext):
    if not check_user(msg.from_user.id):
        return
    await state.set_state(InventarStates.amal)
    await msg.answer("📦 Inventar bo'limi:", reply_markup=INVENTAR_KB)


@router.message(InventarStates.amal, F.text == "📋 Ro'yxat ko'rish")
async def inventar_royxat(msg: Message, state: FSMContext):
    await state.clear()
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Inventar")
        rows = sheet.get_all_values()[1:]
        if not rows:
            await msg.answer("📦 Inventar bo'sh.", reply_markup=MAIN_KB)
            return
        lines = ["📦 <b>Inventar ro'yxati:</b>\n"]
        for i, r in enumerate(rows, 1):
            m    = r[0] if len(r) > 0 else "—"
            miq  = r[1] if len(r) > 1 else "—"
            bir  = r[2] if len(r) > 2 else ""
            narx = r[3] if len(r) > 3 else ""
            try:
                q = float(miq) * float(narx) if narx else 0
                qs = f" = {q:,.0f} so'm" if narx else ""
            except ValueError:
                qs = ""
            lines.append(f"{i}. <b>{m}</b>: {miq} {bir}{qs}")
        await msg.answer("\n".join(lines), reply_markup=MAIN_KB, parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


@router.message(InventarStates.amal, F.text.in_(["➕ Mahsulot qo'shish", "✏️ Yangilash"]))
async def inventar_qoshish(msg: Message, state: FSMContext):
    amal = "qoshish" if "qo'shish" in msg.text else "yangilash"
    await state.update_data(amal=amal)
    await state.set_state(InventarStates.mahsulot)
    await msg.answer("📝 Mahsulot nomini kiriting:", reply_markup=ReplyKeyboardRemove())


@router.message(InventarStates.mahsulot)
async def inventar_mahsulot(msg: Message, state: FSMContext):
    await state.update_data(mahsulot=msg.text.strip())
    await state.set_state(InventarStates.miqdor)
    await msg.answer("🔢 Miqdorini kiriting:")


@router.message(InventarStates.miqdor)
async def inventar_miqdor(msg: Message, state: FSMContext):
    try:
        miqdor = float(msg.text.strip().replace(",", "."))
    except ValueError:
        await msg.answer("⚠️ To'g'ri miqdor kiriting:")
        return
    await state.update_data(miqdor=miqdor)
    await state.set_state(InventarStates.birlik)
    await msg.answer("📐 O'lchov birligini kiriting (dona, kg, litr ...):")


@router.message(InventarStates.birlik)
async def inventar_birlik(msg: Message, state: FSMContext):
    await state.update_data(birlik=msg.text.strip())
    await state.set_state(InventarStates.narx)
    await msg.answer("💰 Narxini kiriting (ixtiyoriy — '-' yozing):")


@router.message(InventarStates.narx)
async def inventar_narx(msg: Message, state: FSMContext):
    narx = "" if msg.text.strip() == "-" else msg.text.strip().replace(" ", "")
    await state.update_data(narx=narx)
    await state.set_state(InventarStates.izoh)
    await msg.answer("📝 Izoh (ixtiyoriy — '-' yozing):")


@router.message(InventarStates.izoh)
async def inventar_izoh(msg: Message, state: FSMContext):
    izoh = "" if msg.text.strip() == "-" else msg.text.strip()
    data = await state.get_data()
    await state.clear()
    sana = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Inventar")
        if data["amal"] == "yangilash":
            cell = sheet.find(data["mahsulot"])
            if cell:
                sheet.update(f"B{cell.row}:F{cell.row}",
                             [[data["miqdor"], data["birlik"], data["narx"], izoh, sana]])
                status = "yangilandi ✏️"
            else:
                sheet.append_row([data["mahsulot"], data["miqdor"], data["birlik"], data["narx"], izoh, sana])
                status = "qo'shildi ➕ (yangi)"
        else:
            sheet.append_row([data["mahsulot"], data["miqdor"], data["birlik"], data["narx"], izoh, sana])
            status = "qo'shildi ➕"
        await msg.answer(
            f"✅ <b>Inventar {status}</b>\n\n"
            f"📦 {data['mahsulot']}: {data['miqdor']} {data['birlik']}",
            reply_markup=MAIN_KB,
            parse_mode="HTML",
        )
    except Exception as e:
        await msg.answer(f"❌ Xatolik: {e}", reply_markup=MAIN_KB)


# ─── HISOBOT ──────────────────────────────────────────────────────────────────
@router.message(F.text == "📊 Hisobot")
async def hisobot_menyu(msg: Message):
    if not check_user(msg.from_user.id):
        return
    await msg.answer("📊 Hisobot turini tanlang:", reply_markup=HISOBOT_KB)


@router.callback_query(F.data == "hisobot_bugun")
async def hisobot_bugun(call: CallbackQuery):
    await call.answer()
    bugun = datetime.now().strftime("%Y-%m-%d")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = [r for r in sheet.get_all_values()[1:] if r and r[0].startswith(bugun)]
        if not rows:
            await call.message.answer("📅 Bugun operatsiya yo'q.")
            return
        kirim = sum(float(r[3]) for r in rows if len(r) > 3 and r[3] and float(r[3]) > 0)
        chiqim = sum(float(r[3]) for r in rows if len(r) > 3 and r[3] and float(r[3]) < 0)
        qoldiq = get_qoldiq()
        lines = [f"📅 <b>Bugungi hisobot ({bugun}):</b>\n"]
        lines.append(f"➕ Kirim: <b>+{kirim:,.0f} so'm</b>")
        lines.append(f"➖ Chiqim: <b>{chiqim:,.0f} so'm</b>")
        lines.append(f"\n{qoldiq_emoji(qoldiq)} <b>Joriy qoldiq: {qoldiq:,.0f} so'm</b>")
        lines.append(f"📝 Operatsiyalar: {len(rows)} ta")

        # Kategoriyalar bo'yicha
        kat_chiqim: dict = {}
        for r in rows:
            if len(r) > 3 and r[3] and float(r[3]) < 0:
                k = r[2] if len(r) > 2 else "Boshqa"
                kat_chiqim[k] = kat_chiqim.get(k, 0) + abs(float(r[3]))
        if kat_chiqim:
            lines.append("\n<b>Chiqimlar:</b>")
            for k, s in sorted(kat_chiqim.items(), key=lambda x: -x[1]):
                lines.append(f"  {k}: {s:,.0f} so'm")
        await call.message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik: {e}")


@router.callback_query(F.data == "hisobot_oy")
async def hisobot_oy(call: CallbackQuery):
    await call.answer()
    oy = datetime.now().strftime("%Y-%m")
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Operatsiyalar")
        rows = [r for r in sheet.get_all_values()[1:] if r and r[0].startswith(oy)]
        if not rows:
            await call.message.answer(f"📆 {oy} oyida operatsiya yo'q.")
            return
        kirim = sum(float(r[3]) for r in rows if len(r) > 3 and r[3] and float(r[3]) > 0)
        chiqim = sum(float(r[3]) for r in rows if len(r) > 3 and r[3] and float(r[3]) < 0)
        qoldiq = get_qoldiq()
        lines = [f"📆 <b>Oylik hisobot ({oy}):</b>\n"]
        lines.append(f"➕ Jami kirim: <b>+{kirim:,.0f} so'm</b>")
        lines.append(f"➖ Jami chiqim: <b>{chiqim:,.0f} so'm</b>")
        lines.append(f"📊 Farq: <b>{kirim+chiqim:,.0f} so'm</b>")
        lines.append(f"\n{qoldiq_emoji(qoldiq)} <b>Joriy qoldiq: {qoldiq:,.0f} so'm</b>")
        lines.append(f"📝 Operatsiyalar: {len(rows)} ta")

        kat_chiqim: dict = {}
        for r in rows:
            if len(r) > 3 and r[3] and float(r[3]) < 0:
                k = r[2] if len(r) > 2 else "Boshqa"
                kat_chiqim[k] = kat_chiqim.get(k, 0) + abs(float(r[3]))
        if kat_chiqim:
            lines.append("\n<b>Chiqimlar bo'yicha:</b>")
            for k, s in sorted(kat_chiqim.items(), key=lambda x: -x[1]):
                foiz = s / abs(chiqim) * 100 if chiqim else 0
                lines.append(f"  {k}: {s:,.0f} so'm ({foiz:.1f}%)")
        await call.message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik: {e}")


@router.callback_query(F.data == "hisobot_inventar")
async def hisobot_inventar(call: CallbackQuery):
    await call.answer()
    try:
        client = get_sheets_client()
        sp = client.open_by_key(SPREADSHEET_ID)
        sheet = sp.worksheet("Inventar")
        rows = sheet.get_all_values()[1:]
        if not rows:
            await call.message.answer("📦 Inventar bo'sh.")
            return
        jami = 0.0
        lines = ["📦 <b>Inventar holati:</b>\n"]
        for r in rows:
            m    = r[0] if r else "—"
            miq  = r[1] if len(r) > 1 else "0"
            bir  = r[2] if len(r) > 2 else ""
            narx = r[3] if len(r) > 3 else ""
            try:
                q = float(miq) * float(narx) if narx else 0
                jami += q
                qs = f" = {q:,.0f} so'm" if narx else ""
            except ValueError:
                qs = ""
            lines.append(f"• <b>{m}</b>: {miq} {bir}{qs}")
        if jami:
            lines.append(f"\n💰 <b>Jami qiymat: {jami:,.0f} so'm</b>")
        await call.message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"❌ Xatolik: {e}")


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
