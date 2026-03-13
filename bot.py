import os
import requests
from dotenv import load_dotenv

load_dotenv()

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# -------------------------------
# CONFIG
# -------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
SHIPHUB_API_KEY = os.environ["SHIPHUB_API_KEY"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
PRICE_STARS = 1
paid_users = set()
payment_logs = {}

SENDER, RECIPIENT = range(2)

# -------------------------------
# HELPERS
# -------------------------------
def get_cheapest_label():
    url = "https://shiphub-production.up.railway.app/api/user/services"
    headers = {"X-API-Key": SHIPHUB_API_KEY}
    r = requests.get(url, headers=headers)
    data = r.json()
    if not data.get("success"):
        return "1"
    cheapest = min(data["data"], key=lambda x: float(x["price"].replace("$", "")))
    return cheapest["id"]

def create_label(from_info, to_info, weight=16, length=10, width=8, height=4, reference="ORDER"):
    url = "https://shiphub-production.up.railway.app/api/user/create-order"
    label_id = get_cheapest_label()
    payload = {
        "label_id": label_id,
        "fromName": from_info.get("name"),
        "fromCompany": from_info.get("company", ""),
        "fromAddress": from_info.get("address"),
        "fromAddress2": from_info.get("address2", ""),
        "fromCity": from_info.get("city"),
        "fromState": from_info.get("state"),
        "fromZip": from_info.get("zip"),
        "fromCountry": from_info.get("country", "US"),
        "toName": to_info.get("name"),
        "toCompany": to_info.get("company", ""),
        "toAddress": to_info.get("address"),
        "toAddress2": to_info.get("address2", ""),
        "toCity": to_info.get("city"),
        "toState": to_info.get("state"),
        "toZip": to_info.get("zip"),
        "toCountry": to_info.get("country", "US"),
        "weight": weight,
        "length": length,
        "width": width,
        "height": height,
        "reference_1": reference,
        "description": "Telegram label purchase"
    }
    headers = {"X-API-Key": SHIPHUB_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# -------------------------------
# BOT HANDLERS
# -------------------------------
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📦 Buy Label", callback_data="buy")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📦 Shipping Label Panel\nChoose an option:\n\n"
        "💬 Customer support: DM @dfdfsfewrbot on Telegram",
        reply_markup=reply_markup
    )

async def button(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "buy":
        await buy_label(query, context)
    elif query.data == "stats":
        count = context.user_data.get("labels", 0)
        await query.message.reply_text(f"📊 Labels purchased: {count}")
    elif query.data == "help":
        await query.message.reply_text(
            "This bot sells shipping labels for ⭐ 300 Stars.\n"
            "Customer support: DM @dfdfsfewrbot on Telegram\n"
            "Weight limit per package: 69 lbs"
        )

async def buy_label(update, context):
    chat_id = update.message.chat.id if update.message else update.callback_query.message.chat.id
    prices = [LabeledPrice("Shipping Label", PRICE_STARS)]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="Shipping Label",
        description="Purchase a shipping label (up to 69 lbs)",
        payload="label_purchase",
        currency="XTR",
        prices=prices
    )

async def precheckout(update, context):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update, context):
    user_id = update.effective_user.id
    paid_users.add(user_id)
    payment_logs[user_id] = update.message.successful_payment.to_dict()
    await update.message.reply_text(
        "✅ Payment received!\n\nStep 1: Send sender info:\n"
        "Name, Address, City, State, ZIP\n"
        "Example:\nJohn Doe, 123 Main Street, Los Angeles, CA, 90001"
    )
    return SENDER

async def sender_info(update, context):
    user_id = update.effective_user.id
    if user_id not in paid_users:
        await update.message.reply_text("Please purchase a label first using Buy Label.")
        return ConversationHandler.END

    parts = [x.strip() for x in update.message.text.split(",")]
    if len(parts) < 5:
        await update.message.reply_text("Invalid format. Use: Name, Address, City, State, ZIP")
        return SENDER

    context.user_data["from_info"] = {
        "name": parts[0],
        "address": parts[1],
        "city": parts[2],
        "state": parts[3],
        "zip": parts[4],
        "country": "US"
    }

    await update.message.reply_text(
        "✅ Sender info saved!\n\nStep 2: Send recipient info:\n"
        "Name, Address, City, State, ZIP, Weight (max 69 lbs)\n"
        "Example:\nJane Smith, 456 Elm Street, New York, NY, 10001, 5"
    )
    return RECIPIENT

async def recipient_info(update, context):
    user_id = update.effective_user.id
    if user_id not in paid_users:
        await update.message.reply_text("Please purchase a label first using Buy Label.")
        return ConversationHandler.END

    parts = [x.strip() for x in update.message.text.split(",")]
    if len(parts) < 6:
        await update.message.reply_text("Invalid format. Use: Name, Address, City, State, ZIP, Weight")
        return RECIPIENT

    try:
        weight = float(parts[5])
        if weight > 69:
            await update.message.reply_text("❌ Weight exceeds 69 lbs limit.")
            return RECIPIENT

        to_info = {
            "name": parts[0],
            "address": parts[1],
            "city": parts[2],
            "state": parts[3],
            "zip": parts[4],
            "country": "US"
        }

        resp = create_label(context.user_data["from_info"], to_info, weight=weight)

        if resp.get("success"):
            label_data = resp["data"]
            await update.message.reply_text(
                f"✅ Label Created!\n"
                f"Tracking: {label_data['tracking_id']}\n"
                f"PDF: {label_data['pdf']}\n\n"
                "Customer support: DM @dfdfsfewrbot on Telegram"
            )
            context.user_data["labels"] = context.user_data.get("labels", 0) + 1
            paid_users.remove(user_id)
        else:
            error_msg = resp.get("error", "Unknown error")
            await update.message.reply_text(
                f"❌ Label creation failed.\nError: {error_msg}\n\n"
                "Please contact support for a refund: @dfdfsfewrbot"
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Unexpected error: {e}\n\nPlease contact support: @dfdfsfewrbot")

    return ConversationHandler.END

async def view_logs(update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to view logs.")
        return

    if not payment_logs:
        await update.message.reply_text("No payments logged yet.")
        return

    msg = ""
    for uid, log in payment_logs.items():
        msg += f"User ID: {uid}\nPayment Info: {log}\n\n"

    await update.message.reply_text(msg)

# -------------------------------
# MAIN
# -------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment)],
        states={
            SENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, sender_info)],
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recipient_info)]
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(CommandHandler("viewlogs", view_logs))
    app.add_handler(conv_handler)

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
