"""
Telegram Bot for AnonXStreamAPI
Allows users and bot owners to generate, view, and manage API keys directly via Telegram.
"""

import os
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import database as db

logger = logging.getLogger("AnonXStreamAPI.Bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://your-app.up.railway.app").strip().rstrip("/")

router = Router()


def get_start_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔑 Generate New API Key", callback_data="btn_genkey"),
                InlineKeyboardButton(text="📋 My Keys", callback_data="btn_mykeys"),
            ],
            [
                InlineKeyboardButton(text="📊 Server Stats", callback_data="btn_stats"),
                InlineKeyboardButton(text="📖 How to Connect", callback_data="btn_help"),
            ],
        ]
    )


def get_back_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="btn_start")]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    first_name = message.from_user.first_name if message.from_user else "User"
    text = (
        f"👋 **Hello, {first_name}!**\n\n"
        "Welcome to **AnonXStreamAPI Bot** 🎵\n\n"
        "This bot provides high-speed, 403-free streaming API keys for your **Telegram Music Bots** (like AnonXMusic).\n\n"
        "👇 **Choose an option below:**"
    )
    await message.reply(text, reply_markup=get_start_markup(), parse_mode="Markdown")


@router.message(Command("genkey", "newkey", "key"))
async def cmd_genkey(message: Message):
    user = message.from_user
    user_id = user.id if user else 0
    user_name = user.username or user.first_name or "Unknown"

    try:
        new_key = await db.generate_api_key(
            user_id=user_id,
            user_name=user_name,
            note=f"Created via Telegram by {user_name}",
        )

        reply_text = (
            "🎉 **Your API Key has been generated successfully!**\n\n"
            "🔑 **Your API Key:**\n"
            f"`{new_key}`\n\n"
            "*(Tap the key above to copy)*\n\n"
            "⚙️ **How to connect in AnonXMusic (.env):**\n"
            "```env\n"
            f"STREAM_API_URL={PUBLIC_URL}\n"
            f"STREAM_API_KEY={new_key}\n"
            "```\n\n"
            "Send `/restart` to your music bot to apply!"
        )
        await message.reply(reply_text, parse_mode="Markdown")
    except Exception as exc:
        logger.error("Failed to generate key: %s", exc)
        await message.reply("❌ Error generating API key. Please try again later.")


@router.message(Command("mykeys", "keys"))
async def cmd_mykeys(message: Message):
    user_id = message.from_user.id if message.from_user else 0
    keys = await db.get_user_keys(user_id)

    if not keys:
        return await message.reply(
            "ℹ️ You don't have any active API keys.\n\nUse `/genkey` to generate your first key!",
            parse_mode="Markdown",
        )

    lines = ["📋 **Your Active API Keys:**\n"]
    for idx, item in enumerate(keys, 1):
        lines.append(f"**{idx}.** `{item['key']}`")
        lines.append(f"   • Requests served: `{item.get('requests_count', 0)}`")
        lines.append(f"   • Status: {'Active ✅' if item.get('active') else 'Revoked ❌'}\n")

    lines.append("To revoke a key, use `/revoke <key>`")
    await message.reply("\n".join(lines), parse_mode="Markdown")


@router.message(Command("revoke", "delkey"))
async def cmd_revoke(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("⚠️ **Usage:** `/revoke <your_api_key>`", parse_mode="Markdown")

    key_to_revoke = args[1].strip()
    user_id = message.from_user.id if message.from_user else 0

    # If owner, can revoke any key; otherwise only own keys
    target_user_id = None if (OWNER_ID and user_id == OWNER_ID) else user_id
    success = await db.revoke_api_key(key_to_revoke, user_id=target_user_id)

    if success:
        await message.reply(f"✅ API Key `{key_to_revoke}` has been revoked.", parse_mode="Markdown")
    else:
        await message.reply("❌ Key not found or you do not have permission to revoke it.", parse_mode="Markdown")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = await db.get_stats()
    text = (
        "📊 **AnonXStreamAPI Server Statistics:**\n\n"
        f"• **Database Connected:** {'Yes ✅' if stats.get('connected') else 'No ❌'}\n"
        f"• **Total Keys Generated:** `{stats.get('total_keys', 0)}`\n"
        f"• **Active Keys:** `{stats.get('active_keys', 0)}`\n"
        f"• **Total Stream Requests:** `{stats.get('total_requests', 0)}`\n"
    )
    await message.reply(text, parse_mode="Markdown")


@router.callback_query(F.data == "btn_start")
async def cb_start(query: CallbackQuery):
    first_name = query.from_user.first_name if query.from_user else "User"
    text = (
        f"👋 **Hello, {first_name}!**\n\n"
        "Welcome to **AnonXStreamAPI Bot** 🎵\n\n"
        "This bot provides high-speed, 403-free streaming API keys for your **Telegram Music Bots** (like AnonXMusic).\n\n"
        "👇 **Choose an option below:**"
    )
    await query.message.edit_text(text, reply_markup=get_start_markup(), parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data == "btn_genkey")
async def cb_genkey(query: CallbackQuery):
    user = query.from_user
    user_id = user.id if user else 0
    user_name = user.username or user.first_name or "Unknown"

    try:
        new_key = await db.generate_api_key(
            user_id=user_id,
            user_name=user_name,
            note=f"Created via Telegram button by {user_name}",
        )

        reply_text = (
            "🎉 **Your API Key has been generated successfully!**\n\n"
            "🔑 **Your API Key:**\n"
            f"`{new_key}`\n\n"
            "*(Tap the key above to copy)*\n\n"
            "⚙️ **How to connect in AnonXMusic (.env):**\n"
            "```env\n"
            f"STREAM_API_URL={PUBLIC_URL}\n"
            f"STREAM_API_KEY={new_key}\n"
            "```\n\n"
            "Send `/restart` to your music bot to apply!"
        )
        await query.message.edit_text(reply_text, reply_markup=get_back_markup(), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Error generating key in callback: %s", exc)
        await query.answer("❌ Error generating API key. Please check MongoDB connection.", show_alert=True)
    await query.answer()


@router.callback_query(F.data == "btn_mykeys")
async def cb_mykeys(query: CallbackQuery):
    user_id = query.from_user.id if query.from_user else 0
    keys = await db.get_user_keys(user_id)

    if not keys:
        await query.message.edit_text(
            "ℹ️ You don't have any active API keys yet.\n\nClick **Generate New API Key** below!",
            reply_markup=get_start_markup(),
            parse_mode="Markdown",
        )
        return await query.answer()

    lines = ["📋 **Your Active API Keys:**\n"]
    for idx, item in enumerate(keys, 1):
        lines.append(f"**{idx}.** `{item['key']}`")
        lines.append(f"   • Requests served: `{item.get('requests_count', 0)}`")
        lines.append(f"   • Status: {'Active ✅' if item.get('active') else 'Revoked ❌'}\n")

    lines.append("To revoke a key, send `/revoke <key>` in chat.")
    await query.message.edit_text("\n".join(lines), reply_markup=get_back_markup(), parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data == "btn_stats")
async def cb_stats(query: CallbackQuery):
    stats = await db.get_stats()
    text = (
        "📊 **AnonXStreamAPI Server Statistics:**\n\n"
        f"• **Database Connected:** {'Yes ✅' if stats.get('connected') else 'No ❌'}\n"
        f"• **Total Keys Generated:** `{stats.get('total_keys', 0)}`\n"
        f"• **Active Keys:** `{stats.get('active_keys', 0)}`\n"
        f"• **Total Stream Requests:** `{stats.get('total_requests', 0)}`\n"
    )
    await query.message.edit_text(text, reply_markup=get_back_markup(), parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data == "btn_help")
async def cb_help(query: CallbackQuery):
    text = (
        "📖 **How to Connect with your Telegram Music Bot:**\n\n"
        "1. Click **Generate New API Key** to get your random key.\n"
        "2. Copy the key.\n"
        "3. Open your bot's `.env` file on your VPS and set:\n"
        "```env\n"
        f"STREAM_API_URL={PUBLIC_URL}\n"
        "STREAM_API_KEY=your_generated_key\n"
        "```\n"
        "4. Restart your bot (`/restart` in Telegram).\n\n"
        "Now your bot streams all audio through this safe Railway microservice!"
    )
    await query.message.edit_text(text, reply_markup=get_back_markup(), parse_mode="Markdown")
    await query.answer()


bot_instance: Optional[Bot] = None
dp_instance: Optional[Dispatcher] = None
bot_task: Optional[asyncio.Task] = None


async def start_telegram_bot():
    global bot_instance, dp_instance, bot_task
    if not BOT_TOKEN:
        logger.info("No BOT_TOKEN found in environment. Telegram Bot is disabled.")
        return

    try:
        bot_instance = Bot(token=BOT_TOKEN)
        dp_instance = Dispatcher()
        dp_instance.include_router(router)

        # Delete any pending updates
        await bot_instance.delete_webhook(drop_pending_updates=True)
        bot_info = await bot_instance.get_me()
        logger.info("Telegram Bot started as @%s", bot_info.username)

        # Start polling as a background task
        bot_task = asyncio.create_task(dp_instance.start_polling(bot_instance))
    except Exception as exc:
        logger.error("Failed to start Telegram Bot: %s", exc)


async def stop_telegram_bot():
    global bot_instance, dp_instance, bot_task
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    if bot_instance:
        await bot_instance.session.close()
        logger.info("Telegram Bot stopped.")
