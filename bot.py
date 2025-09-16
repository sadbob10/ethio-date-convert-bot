# bot.py
import logging
import os
import re
import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from age_calculation import calculate_age, parse_birth_date, validate_birth_date
from date_conversion import format_gregorian_date, format_ethiopian_date, format_hijri_date, validate_date, EthiopianDateConverter
from text_utils import escape_markdown, sanitize_message
from hijridate import Hijri, Gregorian

# ---------------- LOGGING ----------------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set.")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if ADMIN_CHAT_ID:
    try:
        ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
    except ValueError:
        logger.warning("ADMIN_CHAT_ID is not a valid integer. Messages won't be forwarded.")
        ADMIN_CHAT_ID = None

# ---------------- KEYBOARD ----------------
def get_global_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Convert Date"), KeyboardButton("Calculate Age")],
            [KeyboardButton("Menu"), KeyboardButton("Write a message")],
            [KeyboardButton("Cancel")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

GLOBAL_KEYBOARD = get_global_keyboard()

# ---------------- Calendar Names ----------------
calendar_names = {
    "greg": "Gregorian",
    "eth": "Ethiopian",
    "hijri": "Hijri"
}


# ---------------- Start Handler ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data.clear()
        today = datetime.date.today()
        greg_str = format_gregorian_date(today)
        eth_year, eth_month, eth_day = EthiopianDateConverter.to_ethiopian(today.year, today.month, today.day)
        eth_str = format_ethiopian_date(eth_year, eth_month, eth_day)
        hijri_date = Gregorian(today.year, today.month, today.day).to_hijri()
        hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
        hijri_str = format_hijri_date(hy, hm, hd)
        await update.message.reply_text(
            f"📅 *Today's Date in All Calendars:*\n\n"
            f"• {today.year}-{today.month:02d}-{today.day:02d} (Greg)\n→ {greg_str}\n\n"
            f"• {eth_year}-{eth_month:02d}-{eth_day:02d} (Eth)\n→ {eth_str}\n\n"
            f"• {hy}-{hm:02d}-{hd:02d} (Hijri)\n→ {hijri_str}",
            parse_mode="Markdown"
        )
        await update.message.reply_text("Quick actions always available below 👇", reply_markup=GLOBAL_KEYBOARD)
    except Exception:
        logger.exception(f"Error in /start handler for user {update.effective_user.id}")
        await update.message.reply_text("⚠️ Failed to generate today's dates.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Menu & Help ----------------
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu_text = """
🤖 *Date Converter Bot Menu*

*Available Commands:*
/start - Start the bot
/menu - Show this menu
/help - Get help information
/cancel - Cancel current operation

*Quick Actions:*
• Convert Date - Convert between calendars
• Calculate Age - Calculate age from birthdate
• Write a message - Contact the admin

*Supported Calendars:*
• Gregorian 📅
• Ethiopian 🇪🇹
• Hijri 🌙
"""
    await update.message.reply_text(menu_text, parse_mode="Markdown", reply_markup=GLOBAL_KEYBOARD)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 *How to use this bot:*

1. Click *Convert Date* or send /start
2. Choose the calendar type of your input date
3. Send the date in *YYYY-MM-DD* format
4. Select the conversion type

*For Age Calculation:*
1. Click *Calculate Age*
2. Choose the calendar your birth date belongs to
3. Send your birth date in YYYY-MM-DD
4. Bot will show your age

*To cancel any operation:*
- Type /cancel or click Cancel
"""
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Cancel ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_date"):
        context.user_data["awaiting_date"] = None
        context.user_data["input_mode"] = None
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=GLOBAL_KEYBOARD)
    else:
        await update.message.reply_text("No operation to cancel.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Process Date ----------------

async def process_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await update.message.reply_text("⚠️ Please use YYYY-MM-DD format (e.g., 2023-12-25).")
        return

    mode = context.user_data.get("input_mode")
    awaiting = context.user_data.get("awaiting_date")
    if not mode or awaiting not in ["convert", "age"]:
        return

    try:
        y, m, d = map(int, text.split("-"))

        # ---------------- Age Validation ----------------
        if awaiting == "age":
            valid, error_msg = validate_birth_date(mode, y, m, d)
            if not valid:
                await update.message.reply_text(f"⚠️ {error_msg}")
                return

            birth_date = parse_birth_date(mode, y, m, d)
            age = calculate_age(birth_date)
            await update.message.reply_text(
                f"🎂 You are *{age}* years old.",
                parse_mode="Markdown",
                reply_markup=GLOBAL_KEYBOARD
            )
            context.user_data["awaiting_date"] = None
            context.user_data["input_mode"] = None
            return

        # ---------------- Date Conversion ----------------
        if awaiting == "convert":
            if mode == "greg":
                ey, em, ed = EthiopianDateConverter.to_ethiopian(y, m, d)
                eth_str = format_ethiopian_date(ey, em, ed)
                hijri_date = Gregorian(y, m, d).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)
                result = (
                    f"📅 {y}-{m:02d}-{d:02d} (Gregorian)\n\n"
                    f"→ {ey}-{em:02d}-{ed:02d} (Ethiopian)\n   {eth_str}\n\n"
                    f"→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"
                )

            elif mode == "eth":
                g_date = EthiopianDateConverter.to_gregorian(y, m, d)
                gy, gm, gd = g_date.year, g_date.month, g_date.day
                greg_str = format_gregorian_date(g_date)
                hijri_date = Gregorian(gy, gm, gd).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)
                result = (
                    f"📅 {y}-{m:02d}-{d:02d} (Ethiopian)\n\n"
                    f"→ {gy}-{gm:02d}-{gd:02d} (Gregorian)\n   {greg_str}\n\n"
                    f"→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"
                )

            elif mode == "hijri":
                g_date = Hijri(y, m, d).to_gregorian()
                gy, gm, gd = g_date.year, g_date.month, g_date.day
                greg_str = format_gregorian_date(g_date)
                ey, em, ed = EthiopianDateConverter.to_ethiopian(gy, gm, gd)
                eth_str = format_ethiopian_date(ey, em, ed)
                result = (
                    f"📅 {y}-{m:02d}-{d:02d} (Hijri)\n\n"
                    f"→ {gy}-{gm:02d}-{gd:02d} (Gregorian)\n   {greg_str}\n\n"
                    f"→ {ey}-{em:02d}-{ed:02d} (Ethiopian)\n   {eth_str}"
                )

            await update.message.reply_text(result)
            context.user_data["awaiting_date"] = None
            context.user_data["input_mode"] = None

    except Exception as e:
        logger.exception(f"Error processing date for user {update.effective_user.id}")
        await update.message.reply_text(f"⚠️ Error processing date: {str(e)}")

    text = update.message.text.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await update.message.reply_text("⚠️ Please use YYYY-MM-DD format (e.g., 2023-12-25).")
        return

    mode = context.user_data.get("input_mode")
    awaiting = context.user_data.get("awaiting_date")
    if not mode or awaiting not in ["convert", "age"]:
        return

    try:
        y, m, d = map(int, text.split("-"))
        is_valid, error_msg = validate_date(mode, y, m, d)
        if not is_valid:
            await update.message.reply_text(f"⚠️ {error_msg or 'Invalid date for selected calendar'}. Please try again.")
            return

        if awaiting == "age":
            birth_date = parse_birth_date(mode, y, m, d)
            age = calculate_age(birth_date)
            await update.message.reply_text(f"🎂 You are *{age}* years old.", parse_mode="Markdown", reply_markup=GLOBAL_KEYBOARD)
            context.user_data["awaiting_date"] = None
            context.user_data["input_mode"] = None
            return

        # Date conversion logic
        if awaiting == "convert":
            if mode == "greg":
                ey, em, ed = EthiopianDateConverter.to_ethiopian(y, m, d)
                eth_str = format_ethiopian_date(ey, em, ed)
                hijri_date = Gregorian(y, m, d).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)
                result = f"📅 {y}-{m:02d}-{d:02d} (Gregorian)\n\n→ {ey}-{em:02d}-{ed:02d} (Ethiopian)\n   {eth_str}\n\n→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"
            elif mode == "eth":
                g_date = EthiopianDateConverter.to_gregorian(y, m, d)
                gy, gm, gd = g_date.year, g_date.month, g_date.day
                greg_str = format_gregorian_date(g_date)
                hijri_date = Gregorian(gy, gm, gd).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)
                result = f"📅 {y}-{m:02d}-{d:02d} (Ethiopian)\n\n→ {gy}-{gm:02d}-{gd:02d} (Gregorian)\n   {greg_str}\n\n→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"
            elif mode == "hijri":
                g_date = Hijri(y, m, d).to_gregorian()
                gy, gm, gd = g_date.year, g_date.month, g_date.day
                greg_str = format_gregorian_date(g_date)
                ey, em, ed = EthiopianDateConverter.to_ethiopian(gy, gm, gd)
                eth_str = format_ethiopian_date(ey, em, ed)
                result = f"📅 {y}-{m:02d}-{d:02d} (Hijri)\n\n→ {gy}-{gm:02d}-{gd:02d} (Gregorian)\n   {greg_str}\n\n→ {ey}-{em:02d}-{ed:02d} (Ethiopian)\n   {eth_str}"
            await update.message.reply_text(result)
            context.user_data["awaiting_date"] = None
            context.user_data["input_mode"] = None

    except Exception as e:
        logger.exception(f"Error processing date for user {update.effective_user.id}")
        await update.message.reply_text(f"⚠️ Error processing date: {str(e)}")

# ---------------- Text Handler ----------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text in ["cancel", "/cancel"]:
        await cancel(update, context)
        return

    if text in ["convert date", "convert"]:
        context.user_data["awaiting_date"] = "convert"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Gregorian", callback_data="input-greg"),
              InlineKeyboardButton("Ethiopian", callback_data="input-eth"),
              InlineKeyboardButton("Hijri", callback_data="input-hijri")]]
        )
        await update.message.reply_text("Select input calendar type:", reply_markup=keyboard)
        return

    if text in ["calculate age", "age"]:
        context.user_data["awaiting_date"] = "age"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Gregorian", callback_data="input-greg"),
              InlineKeyboardButton("Ethiopian", callback_data="input-eth"),
              InlineKeyboardButton("Hijri", callback_data="input-hijri")]]
        )
        await update.message.reply_text("Select your birthdate calendar type:", reply_markup=keyboard)
        return

    if text in ["write a message", "message"]:
        if not ADMIN_CHAT_ID:
            await update.message.reply_text("⚠️ Admin chat is not configured. Cannot send messages.")
            return
        context.user_data["awaiting_date"] = "message"
        await update.message.reply_text("✏️ Please type your message and it will be sent to the admin.\nType /cancel to cancel.")
        return

    if context.user_data.get("awaiting_date") == "message":
        try:
            sanitized_msg = sanitize_message(update.message.text)
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID,
                                           text=f"📨 Message from {update.effective_user.full_name} (@{update.effective_user.username or 'N/A'}):\n\n{sanitized_msg}")
            await update.message.reply_text("✅ Your message has been sent to the admin. Thank you!")
        except Exception as e:
            logger.exception(f"Error forwarding message from user {update.effective_user.id}")
            await update.message.reply_text(f"⚠️ Failed to send your message: {str(e)}")
        finally:
            context.user_data["awaiting_date"] = None
        return

    if context.user_data.get("awaiting_date"):
        await process_date(update, context)
        return

    if text in ["menu", "/menu"]:
        await menu(update, context)
        return

    if text in ["help", "/help"]:
        await help_command(update, context)
        return

    await update.message.reply_text("⚠️ Command not recognized. Use /help.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Callback Handler ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data["input_mode"] = data.split("-")[1]
    
    full_name = calendar_names.get(context.user_data["input_mode"], context.user_data["input_mode"])
    
    await query.edit_message_text(
        f"✅ Input mode set to *{full_name}*.\nSend a date in YYYY-MM-DD format.\nType /cancel to cancel.",
        parse_mode="Markdown"
    )

# ---------------- Error Handler ----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ An unexpected error occurred. Please try again later.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Main ----------------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)
    logger.info("Bot started successfully.")
    app.run_polling()

if __name__ == "__main__":
    main()
