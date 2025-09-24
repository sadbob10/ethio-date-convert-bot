import logging
import os
import re
import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from age_calculation import calculate_age, parse_birth_date, validate_birth_date
from date_conversion import (
    format_gregorian_date,
    format_ethiopian_date,
    format_hijri_date,
    validate_date,
    EthiopianDateConverter,
)
from text_utils import escape_markdown, sanitize_message
from hijridate import Hijri, Gregorian
from flask import Flask, jsonify

# ---------------- FLASK APP FOR HEALTH CHECK ----------------
app = Flask(__name__)

@app.route("/")
def health_check():
    return "Bot is running", 200

@app.route("/health")
def health():
    return jsonify(status="ok", bot="running")

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
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
            [KeyboardButton("Cancel")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

GLOBAL_KEYBOARD = get_global_keyboard()

# ---------------- Calendar Names ----------------
calendar_names = {
    "greg": "Gregorian",
    "eth": "Ethiopian",
    "hijri": "Hijri",
}

# ---------------- Pending Messages ----------------
pending_messages = {}  # user_id -> (full_name, username)

# ---------------- Start Handler ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data.clear()
        today = datetime.date.today()
        greg_str = format_gregorian_date(today)

        eth_result = EthiopianDateConverter.to_ethiopian(today.year, today.month, today.day)
        if hasattr(eth_result, "year"):
            eth_year, eth_month, eth_day = eth_result.year, eth_result.month, eth_result.day
        else:
            eth_year, eth_month, eth_day = eth_result
        eth_str = format_ethiopian_date(eth_year, eth_month, eth_day)

        hijri_date = Gregorian(today.year, today.month, today.day).to_hijri()
        hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
        hijri_str = format_hijri_date(hy, hm, hd)

        await update.message.reply_text(
            f"🌍 *Ethiopian Date Converter Bot*\n\n"
            f"📅 *Today's Date in All Calendars:*\n\n"
            f"• {today.year}-{today.month:02d}-{today.day:02d} (Gregorian)\n→ {greg_str}\n\n"
            f"• {eth_year}-{eth_month:02d}-{eth_day:02d} (Ethiopian)\n→ {eth_str}\n\n"
            f"• {hy}-{hm:02d}-{hd:02d} (Hijri)\n→ {hijri_str}\n\n"
            f"✨ You can convert dates, calculate age, and send messages to admin!",
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            "Quick actions always available below 👇", reply_markup=GLOBAL_KEYBOARD
        )
    except Exception:
        logger.exception(f"Error in /start handler for user {update.effective_user.id}")
        await update.message.reply_text(
            "⚠️ Failed to generate today's dates.", reply_markup=GLOBAL_KEYBOARD
        )

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

*For Messaging Admin:*
- Click *Write a message* and type your message
- Admin can reply directly using the reply button inline

*To cancel any operation:*
- Type /cancel or click Cancel
"""
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Cancel ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_date"):
        context.user_data["awaiting_date"] = None
        context.user_data["input_mode"] = None
        context.user_data["reply_to_user"] = None
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=GLOBAL_KEYBOARD)
    else:
        await update.message.reply_text("No operation to cancel.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Process Date ----------------
async def process_date(update: Update, context: ContextTypes.DEFAULT_TYPE, override_text: str = None):
    text = override_text or update.message.text.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        await update.message.reply_text("⚠️ Please use YYYY-MM-DD format (e.g., 2023-12-25).")
        return

    mode = context.user_data.get("input_mode")
    awaiting = context.user_data.get("awaiting_date")
    if not mode or awaiting not in ["convert", "age"]:
        return

    try:
        y, m, d = map(int, text.split("-"))

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
                reply_markup=GLOBAL_KEYBOARD,
            )
            context.user_data["awaiting_date"] = None
            context.user_data["input_mode"] = None
            return

        if awaiting == "convert":
            if mode == "greg":
                eth_result = EthiopianDateConverter.to_ethiopian(y, m, d)
                ey, em, ed = (eth_result.year, eth_result.month, eth_result.day) if hasattr(eth_result, "year") else eth_result
                eth_str = format_ethiopian_date(ey, em, ed)

                hijri_date = Gregorian(y, m, d).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)

                result = f"📅 {y}-{m:02d}-{d:02d} (Gregorian)\n\n→ {ey}-{em:02d}-{ed:02d} (Ethiopian)\n   {eth_str}\n\n→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"

            elif mode == "eth":
                g_date = EthiopianDateConverter.to_gregorian(y, m, d)
                gy, gm, gd = (g_date.year, g_date.month, g_date.day) if hasattr(g_date, "year") else g_date
                greg_str = format_gregorian_date(datetime.date(gy, gm, gd))
                hijri_date = Gregorian(gy, gm, gd).to_hijri()
                hy, hm, hd = hijri_date.year, hijri_date.month, hijri_date.day
                hijri_str = format_hijri_date(hy, hm, hd)

                result = f"📅 {y}-{m:02d}-{d:02d} (Ethiopian)\n\n→ {gy}-{gm:02d}-{gd:02d} (Gregorian)\n   {greg_str}\n\n→ {hy}-{hm:02d}-{hd:02d} (Hijri)\n   {hijri_str}"

            elif mode == "hijri":
                g_date = Hijri(y, m, d).to_gregorian()
                gy, gm, gd = g_date.year, g_date.month, g_date.day
                greg_str = format_gregorian_date(datetime.date(gy, gm, gd))

                eth_result = EthiopianDateConverter.to_ethiopian(gy, gm, gd)
                ey, em, ed = (eth_result.year, eth_result.month, eth_result.day) if hasattr(eth_result, "year") else eth_result
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
    text = update.message.text.strip()

    # Cancel
    if text.lower() in ["cancel", "/cancel"]:
        await cancel(update, context)
        return

    # --- Direct date input detection ---
    if not context.user_data.get("awaiting_date"):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            context.user_data["awaiting_date"] = "direct_convert"
            context.user_data["pending_date"] = text
            keyboard = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("Gregorian", callback_data="direct-greg"),
                    InlineKeyboardButton("Ethiopian", callback_data="direct-eth"),
                    InlineKeyboardButton("Hijri", callback_data="direct-hijri"),
                ]]
            )
            await update.message.reply_text(
                "📅 You sent a date!\nSelect which calendar this date belongs to:",
                reply_markup=keyboard
            )
            return

        # Common wrong formats
        wrong_formats = [
            (r"^(\d{2})-(\d{2})-(\d{4})$", "{2}-{1}-{0}"),   # DD-MM-YYYY → YYYY-MM-DD
            (r"^(\d{4})/(\d{2})/(\d{2})$", "{0}-{1}-{2}"),   # YYYY/MM/DD → YYYY-MM-DD
            (r"^(\d{2})/(\d{2})/(\d{4})$", "{2}-{1}-{0}"),   # DD/MM/YYYY → YYYY-MM-DD
            (r"^(\d{2})-(\d{4})-(\d{2})$", "{1}-{0}-{2}"),   # MM-YYYY-DD
        ]

        for pattern, fmt in wrong_formats:
            m = re.match(pattern, text)
            if m:
                suggestion = fmt.format(*m.groups())
                await update.message.reply_text(
                    f"⚠️ Date format should be YYYY-MM-DD.\n👉 Did you mean *{suggestion}*?",
                    parse_mode="Markdown"
                )
                return

    # Convert Date
    if text.lower() in ["convert date", "convert"]:
        context.user_data["awaiting_date"] = "convert"
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Gregorian", callback_data="input-greg"),
                InlineKeyboardButton("Ethiopian", callback_data="input-eth"),
                InlineKeyboardButton("Hijri", callback_data="input-hijri"),
            ]]
        )
        await update.message.reply_text("Select input calendar type:", reply_markup=keyboard)
        return

    # Calculate Age
    if text.lower() in ["calculate age", "age"]:
        context.user_data["awaiting_date"] = "age"
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Gregorian", callback_data="input-greg"),
                InlineKeyboardButton("Ethiopian", callback_data="input-eth"),
                InlineKeyboardButton("Hijri", callback_data="input-hijri"),
            ]]
        )
        await update.message.reply_text("Select your birthdate calendar type:", reply_markup=keyboard)
        return

    # Write a message to admin
    if text.lower() in ["write a message", "message"]:
        if not ADMIN_CHAT_ID:
            await update.message.reply_text("⚠️ Admin chat is not configured. Cannot send messages.")
            return
        context.user_data["awaiting_date"] = "message"
        await update.message.reply_text("✏️ Please type your message and it will be sent to the admin.\nType /cancel to cancel.")
        return

    # User is sending message to admin
    if context.user_data.get("awaiting_date") == "message":
        try:
            sanitized_msg = sanitize_message(text)
            user_id = update.effective_user.id
            full_name = update.effective_user.full_name
            username = update.effective_user.username or "N/A"
            pending_messages[user_id] = (full_name, username)

            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Reply to User", callback_data=f"reply-{user_id}")]]
            )
            reply_text = f"📨 Message from {full_name} (@{username}):\n\n{sanitized_msg}"
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=reply_text, reply_markup=reply_markup)
            await update.message.reply_text("✅ Your message has been sent to the admin. They can reply directly using the button.")
        except Exception as e:
            logger.exception(f"Error forwarding message from user {update.effective_user.id}")
            await update.message.reply_text(f"⚠️ Failed to send your message: {str(e)}")
        finally:
            context.user_data["awaiting_date"] = None
        return

    # Admin replying to user
    if context.user_data.get("awaiting_date") == "admin_reply":
        try:
            target_user_id = context.user_data.get("reply_to_user")
            if not target_user_id:
                await update.message.reply_text("⚠️ No user selected for reply.")
                return
            reply_msg = sanitize_message(text)
            await context.bot.send_message(chat_id=target_user_id, text=f"📩 Reply from Admin:\n\n{reply_msg}")
            await update.message.reply_text("✅ Reply sent to the user.")
        except Exception as e:
            logger.exception("Error sending admin reply")
            await update.message.reply_text(f"⚠️ Failed to send reply: {str(e)}")
        finally:
            context.user_data["awaiting_date"] = None
            context.user_data["reply_to_user"] = None
        return

    # Date processing (convert/age)
    if context.user_data.get("awaiting_date") in ["convert", "age"]:
        await process_date(update, context)
        return

    # Menu
    if text.lower() in ["menu", "/menu"]:
        await menu(update, context)
        return

    # Help
    if text.lower() in ["help", "/help"]:
        await help_command(update, context)
        return

    # Fallback
    await update.message.reply_text("⚠️ Command not recognized. Use /help.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Callback Handler ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("input-"):
        context.user_data["input_mode"] = data.split("-")[1]
        full_name = calendar_names.get(context.user_data["input_mode"], context.user_data["input_mode"])
        await query.edit_message_text(
            f"✅ Input mode set to *{full_name}*.\nSend a date in YYYY-MM-DD format.\nType /cancel to cancel.",
            parse_mode="Markdown",
        )

    elif data.startswith("direct-"):
        mode = data.split("-")[1]
        context.user_data["input_mode"] = mode
        date_str = context.user_data.get("pending_date")

        if not date_str:
            await query.edit_message_text("⚠️ No date found to process.")
            return

        # ✅ Corrected: no fake_update, just override text
        context.user_data["awaiting_date"] = "convert"
        await process_date(update, context, override_text=date_str)

        # Cleanup
        context.user_data["awaiting_date"] = None
        context.user_data["input_mode"] = None
        context.user_data["pending_date"] = None

    elif data.startswith("reply-"):
        user_id = int(data.split("-")[1])
        context.user_data["awaiting_date"] = "admin_reply"
        context.user_data["reply_to_user"] = user_id
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✏️ Please type your reply to the user now (User ID: {user_id})."
        )

# ---------------- Error Handler ----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ An unexpected error occurred. Please try again later.", reply_markup=GLOBAL_KEYBOARD)

# ---------------- Main ----------------
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)

    # Render Webhook
    if os.getenv("RENDER"):
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/"
        logger.info("Starting bot in webhook mode (Production)")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 10000)),
            webhook_url=webhook_url
        )
    else:
        logger.info("Starting bot in polling mode (Local)")
        application.run_polling()

if __name__ == "__main__":
    main()
