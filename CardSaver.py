# file: group_card_interface_bot.py
import json
import re
from pathlib import Path
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)

TOKEN = "ur-api" #<==================================
STORE_PATH = Path("group_cards.json")

# ---------------- Storage ----------------
def load_store() -> Dict[str, Any]:
    if not STORE_PATH.exists():
        return {"groups": {}}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"groups": {}}

def save_store(store: Dict[str, Any]):
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------- Helpers ----------------
def slugify_owner(name: str) -> str:
    name = name.strip()
    if not name:
        return "owner_unknown"
    s = re.sub(r"\s+", "_", name)
    s = re.sub(r"[^\w\-]", "", s)
    return f"owner_{s}" if not s.startswith("owner_") else s

async def delete_wizard_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for msg_id in context.user_data.get("messages", []):
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except:
            pass
    context.user_data["messages"] = []

# ---------------- States ----------------
ASK_NAME, ASK_BANK, ASK_CARD, CONFIRM = range(4)

def get_group_key(update: Update):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        return str(chat.id)
    return None

# ---------------- Menu Helpers ----------------
def build_main_menu(store: Dict[str, Any], group_key: str):
    kb_buttons = [[InlineKeyboardButton("💳 افزودن کارت جدید (برای خودم)", callback_data="add_card")]]
    group_data = store.get("groups", {}).get(group_key, {})
    for uid, cards in list(group_data.items()):
        if cards:
            owner_name = cards[0].get("owner", f"کاربر {uid}")
            kb_buttons.append([InlineKeyboardButton(owner_name, callback_data=f"show_user_{uid}")])
    return InlineKeyboardMarkup(kb_buttons)

def build_user_menu(owner_name: str):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 افزودن کارت جدید (برای این کاربر)", callback_data="add_card_target")],
        [InlineKeyboardButton("🔙 منو اصلی", callback_data="main_menu")]
    ])
    return kb

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("سلام! از /card برای مدیریت کارت‌ها استفاده کنید.")
    context.user_data.setdefault("messages", []).append(msg.message_id)

async def card_start(update: Update, context: ContextTypes.DEFAULT_TYPE, from_query=False):
    store = load_store()
    group_key = get_group_key(update)
    kb = build_main_menu(store, group_key)

    if from_query:
        query = update.callback_query
        await query.answer()
        await query.message.edit_text("لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=kb)
    else:
        msg = await update.message.reply_text("لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=kb)
        context.user_data.setdefault("messages", []).append(msg.message_id)
    return ConversationHandler.END

# ---------------- Add Card ----------------
async def add_card_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    caller_id = str(query.from_user.id)
    context.user_data["target_user_id"] = caller_id
    msg = await query.message.reply_text("مرحله ۱: نام مالک کارت را وارد کنید:")
    context.user_data.setdefault("messages", []).append(msg.message_id)
    return ASK_NAME

async def add_card_target_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = context.user_data.get("target_user_id")
    store = load_store()
    group_key = get_group_key(update)
    group_data = store.get("groups", {}).get(group_key, {})
    user_cards = group_data.get(user_id, [])

    if user_cards:
        context.user_data["owner"] = user_cards[0]["owner"]
    else:
        context.user_data["owner"] = query.from_user.first_name or "مالک"

    msg = await query.message.reply_text(
        f"💳 کارت جدید برای {context.user_data['owner']} ثبت می‌شود.\nمرحله ۱: نام بانک را وارد کنید:"
    )
    context.user_data.setdefault("messages", []).append(msg.message_id)
    return ASK_BANK

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["owner"] = update.message.text.strip()
    context.user_data.setdefault("messages", []).append(update.message.message_id)
    msg = await update.message.reply_text("مرحله ۲: نام بانک را وارد کنید:")
    context.user_data["messages"].append(msg.message_id)
    return ASK_BANK

async def ask_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["bank"] = update.message.text.strip()
    context.user_data.setdefault("messages", []).append(update.message.message_id)
    msg = await update.message.reply_text("مرحله ۳: شماره کارت را وارد کنید:")
    context.user_data["messages"].append(msg.message_id)
    return ASK_CARD

async def ask_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["card"] = update.message.text.strip()
    context.user_data.setdefault("messages", []).append(update.message.message_id)
    owner = context.user_data.get("owner", "نامشخص")
    bank = context.user_data.get("bank", "نامشخص")
    card = context.user_data.get("card", "")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ذخیره کن", callback_data="confirm_save")],
        [InlineKeyboardButton("❌ لغو", callback_data="confirm_cancel")],
        [InlineKeyboardButton("🔙 منو اصلی", callback_data="main_menu")]
    ])
    msg = await update.message.reply_text(
        f"لطفاً بررسی کنید:\n\nاسم: {owner}\nبانک: {bank}\nشماره کارت: <code>{card}</code>\n\nآیا می‌خواهید ذخیره شود؟",
        parse_mode=ParseMode.HTML, reply_markup=kb
    )
    context.user_data["messages"].append(msg.message_id)
    return CONFIRM

# ---------------- Core: ذخیره کارت ----------------
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    store = load_store()
    group_key = get_group_key(update)

    owner = context.user_data.get("owner", "").strip()
    bank = context.user_data.get("bank", "").strip()
    card = context.user_data.get("card", "").strip()

    groups = store.setdefault("groups", {})
    group_data = groups.setdefault(group_key, {})

    target_uid = context.user_data.get("target_user_id")
    chosen_key = None

    if target_uid and target_uid in group_data:
        chosen_key = target_uid
    else:
        found = None
        for uid, cards in group_data.items():
            if cards and cards[0].get("owner", "").strip() == owner:
                found = uid
                break
        if found:
            chosen_key = found
        else:
            base = slugify_owner(owner or "owner")
            new_key = base
            i = 1
            while new_key in group_data:
                new_key = f"{base}_{i}"
                i += 1
            chosen_key = new_key
            group_data.setdefault(chosen_key, [])

    if query.data == "confirm_save":
        user_cards = group_data.setdefault(chosen_key, [])
        already = any(
            entry.get("bank", "").strip() == bank and entry.get("card", "").strip() == card
            for entry in user_cards
        )
        if already:
            await query.message.edit_text("⚠️ این کارت قبلاً ثبت شده است (تکراری کامل).")
        else:
            user_cards.append({"owner": owner or f"کاربر {chosen_key}", "bank": bank, "card": card})
            save_store(store)
            kb = build_main_menu(store, group_key)
            await query.message.edit_text(
                f"✅ کارت ذخیره شد:\nکاربر: {owner or chosen_key}\nبانک: {bank}\nشماره کارت: <code>{card}</code>\n\n"
                "بازگشت به منوی اصلی گروه:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )

    elif query.data == "confirm_cancel":
        await query.message.edit_text("❌ عملیات لغو شد.")
    elif query.data == "main_menu":
        await card_start(update, context, from_query=True)

    # حذف تمام پیام‌های ویزارد شامل پیام‌های کاربر
    await delete_wizard_messages(update, context)

    context.user_data.pop("owner", None)
    context.user_data.pop("bank", None)
    context.user_data.pop("card", None)
    context.user_data.pop("target_user_id", None)

    return ConversationHandler.END

# ---------------- Show User Cards ----------------
async def show_user_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    store = load_store()
    group_key = get_group_key(update)

    user_id = query.data.replace("show_user_", "")
    context.user_data["target_user_id"] = user_id

    group_data = store.get("groups", {}).get(group_key, {})
    user_cards = group_data.get(user_id, [])

    if user_cards:
        owner_name = user_cards[0].get("owner", f"کاربر {user_id}")
        text = "\n\n".join([f"بانک: {c.get('bank')}\nشماره کارت: <code>{c.get('card')}</code>" for c in user_cards])
    else:
        owner_name = f"کاربر {user_id}"
        text = "هیچ کارتی ثبت نشده است."

    kb = build_user_menu(owner_name)
    msg = await query.message.edit_text(f"📂 کارت‌های {owner_name}:\n\n{text}", parse_mode=ParseMode.HTML, reply_markup=kb)
    context.user_data.setdefault("messages", []).append(msg.message_id)

# ---------------- Main Menu & Cancel ----------------
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await card_start(update, context, from_query=True)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    import asyncio
    async def set_commands():
        await app.bot.set_my_commands([
            BotCommand("start", "شروع بات"),
            BotCommand("card", "مدیریت کارت‌ها")
        ])
    asyncio.get_event_loop().run_until_complete(set_commands())

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_card_cb, pattern="^add_card$"),
            CallbackQueryHandler(add_card_target_cb, pattern="^add_card_target$")
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bank)],
            ASK_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_card)],
            CONFIRM: [CallbackQueryHandler(handle_confirm, pattern="^(confirm_save|confirm_cancel|main_menu)$")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("card", card_start))
    app.add_handler(CallbackQueryHandler(show_user_cards, pattern="^show_user_"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(conv_handler)

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
