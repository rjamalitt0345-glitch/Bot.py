import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

BOT_TOKEN = "8648341248:AAEmDjz8NwDLpBnhzrjveRDY87i_1tSOicw"
CHANNEL_USERNAME = "@earnmoneyfors"

API_BASE = "https://mixy-ox-enjoy.vercel.app/?url="

# ✅ Join check function
async def is_joined(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

# 🚀 Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_joined(user_id, context):
        buttons = [
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/earnmoneyfors")],
            [InlineKeyboardButton("✅ Verify", callback_data="verify")]
        ]
        await update.message.reply_text(
            "❌ Pehle channel join karo fir verify karo",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    await update.message.reply_text("✅ Welcome! Link bhej 😎")

# 🔘 Verify button
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_joined(user_id, context):
        await query.edit_message_text("✅ Verified!\n\nAb link bhej 😎")
    else:
        await query.answer("❌ Join nahi kiya abhi", show_alert=True)

# 📩 Message handler
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await is_joined(user_id, context):
        await update.message.reply_text("❌ Pehle channel join karo")
        return

    url = update.message.text.strip()

    if "instagram.com" not in url:
        await update.message.reply_text("❌ Sirf Instagram link bhej")
        return

    msg = await update.message.reply_text("⏳ Fetch ho raha hai...")

    try:
        res = requests.get(API_BASE + url)
        data = res.json()

        video = data.get("video_url") or data.get("video")
        image = data.get("thumbnail") or data.get("image") or data.get("url")

        media_url = video if video else image

        if not media_url:
            await msg.edit_text("❌ Media nahi mila")
            return

        if video:
            await update.message.reply_video(video=media_url)
        else:
            await update.message.reply_photo(photo=media_url)

        await msg.delete()

    except:
        await msg.edit_text("❌ Error aagaya")

# 🔧 App setup
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(verify))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("🤖 Bot Running...")
app.run_polling()