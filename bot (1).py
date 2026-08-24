"""
Автоответчик через Telegram Business Chatbot + Gemini.

Никакого my.telegram.org, никакого api_id/api_hash — только токен бота
от @BotFather и подключение через Telegram Business в настройках аккаунта.

Как это работает на уровне Telegram:
- Ты создаёшь обычного бота через @BotFather, включаешь ему Business Mode.
- В своих настройках Telegram (Settings -> Telegram Business -> Chatbots)
  подключаешь этого бота к своему личному аккаунту.
- После этого ВСЕ сообщения в твоих личных чатах (и входящие от собеседника,
  и твои собственные, если ты ответил вручную) начинают дублироваться
  этому боту как "business_message" апдейты.
- Бот может отвечать в эти чаты от твоего имени через send_message(...,
  business_connection_id=...).

КОМАНДЫ (пиши их себе в любой чат, где ты сам автор сообщения — они не
попадают собеседнику, бот отвечает только тебе отдельным сообщением):

    .help                  — список команд
    .status                — текущие настройки
    .pause                 — выключить автоответы полностью
    .resume                — включить обратно
    .setdelay 10 60         — диапазон задержки перед ответом, секунды
    .setthreshold 15        — через сколько минут твоего молчания включаться
    .setprompt <текст>      — заменить системный промпт
    .setpersona <имя>       — сменить имя персонажа
    .ping                   — проверка, что бот жив

Установка (в Termux):
    pkg install python
    pip install python-telegram-bot google-genai python-dotenv httpx[socks]

Получить токен бота: @BotFather в Telegram -> /newbot
Включить Business Mode: @BotFather -> /mybots -> выбрать бота ->
    Bot Settings -> Business Mode -> Turn on
Подключить к своему аккаунту: Настройки Telegram -> Telegram Business ->
    Chatbots -> вписать username бота -> разрешить отвечать на сообщения
Получить бесплатный ключ Gemini: https://aistudio.google.com/apikey
"""

import asyncio
import os
import random
import time
from collections import defaultdict, deque

from telegram import Update
from telegram.ext import Application, ContextTypes, TypeHandler
from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

load_dotenv()

# ---------- Конфиг ----------

BOT_TOKEN = os.environ["BOT_TOKEN"]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Прокси для доступа к Gemini API (если он у тебя недоступен напрямую).
PROXY_URL = os.environ.get("PROXY_URL") or None

MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "8192"))
HISTORY_LIMIT = 12

# ---------- Изменяемые "на лету" настройки (через .команды) ----------

settings = {
    "enabled": True,
    "delay_min": int(os.environ.get("REPLY_DELAY_MIN", "8")),
    "delay_max": int(os.environ.get("REPLY_DELAY_MAX", "45")),
    "threshold_min": int(os.environ.get("INACTIVITY_THRESHOLD_MIN", "15")),
    "persona_name": os.environ.get("PERSONA_NAME", "Лерекай"),
}
settings["system_prompt"] = (
    "Ты — {persona}, отвечаешь в Telegram от своего лица, пока временно "
    "недоступен(а). Пиши как обычно пишут в мессенджере — живо, без "
    "канцелярита, в своей обычной манере. Ты не ассистент и не ИИ — "
    "никогда не упоминай Gemini, модели, нейросети или что ты программа; "
    "если спросят прямо, отвечай в характере {persona}, не подтверждая и "
    "не опровергая это напрямую. Если вопрос требует решения, которое "
    "стоит принять лично {persona} (деньги, договорённости, личные "
    "обещания), мягко скажи, что ответишь сам(а), как освободишься. "
    "Отвечай настолько подробно, насколько того требует вопрос — не "
    "обрезай мысль искусственно."
).format(persona=settings["persona_name"])

# ---------- Состояние ----------

# Жёстко заданный ID владельца/админа — только он может отдавать команды,
# и только его сообщения считаются "твоими" (не автоответ клиенту).
ADMIN_ID = int(os.environ["ADMIN_ID"])

last_owner_activity: dict[int, float] = defaultdict(lambda: 0.0)
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
paused_chats: set[int] = set()

# ---------- Gemini клиент ----------

genai_http_options = None
if PROXY_URL:
    genai_http_options = genai_types.HttpOptions(
        client_args={"proxy": PROXY_URL},
        async_client_args={"proxy": PROXY_URL},
    )

genai_client = genai.Client(api_key=GEMINI_API_KEY, http_options=genai_http_options)


def is_owner_active(chat_id: int) -> bool:
    elapsed_min = (time.time() - last_owner_activity[chat_id]) / 60
    return elapsed_min < settings["threshold_min"]


async def generate_reply(chat_id: int) -> str:
    lines = []
    for who, text in history[chat_id]:
        prefix = "Я" if who == "me" else "Собеседник"
        lines.append(f"{prefix}: {text}")
    conversation = "\n".join(lines)

    prompt = f"{settings['system_prompt']}\n\nПереписка:\n{conversation}\n\nЯ:"

    response = await asyncio.to_thread(
        genai_client.models.generate_content,
        model=MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    return (response.text or "").strip()


# ---------- Команды на "." ----------

async def handle_command(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not text.startswith("."):
        return False

    parts = text[1:].split(maxsplit=1)
    if not parts:
        return False
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "help":
        reply = (
            ".help — это сообщение\n"
            ".status — текущие настройки\n"
            ".pause — выключить автоответы\n"
            ".resume — включить автоответы\n"
            ".setdelay <мин> <макс> — задержка перед ответом, сек\n"
            ".setthreshold <минуты> — порог твоего простоя\n"
            ".setprompt <текст> — новый системный промпт\n"
            ".setpersona <имя> — сменить имя персонажа\n"
            ".ping — проверить, что бот жив"
        )
    elif cmd == "status":
        reply = (
            f"Автоответы: {'включены' if settings['enabled'] else 'выключены'}\n"
            f"Задержка: {settings['delay_min']}-{settings['delay_max']} сек\n"
            f"Порог простоя: {settings['threshold_min']} мин\n"
            f"Персонаж: {settings['persona_name']}\n"
            f"Модель: {MODEL}\n"
            f"Макс. токенов ответа: {MAX_OUTPUT_TOKENS}\n"
            f"Прокси Gemini: {'да' if PROXY_URL else 'нет'}\n"
            f"Пауз по чатам: {len(paused_chats)}"
        )
    elif cmd == "pause":
        settings["enabled"] = False
        reply = "Автоответы выключены глобально."
    elif cmd == "resume":
        settings["enabled"] = True
        reply = "Автоответы включены."
    elif cmd == "setdelay":
        try:
            lo, hi = map(int, arg.split())
            settings["delay_min"], settings["delay_max"] = lo, hi
            reply = f"Задержка теперь {lo}-{hi} сек."
        except Exception:
            reply = "Формат: .setdelay 10 60"
    elif cmd == "setthreshold":
        try:
            settings["threshold_min"] = int(arg.strip())
            reply = f"Порог простоя теперь {settings['threshold_min']} мин."
        except Exception:
            reply = "Формат: .setthreshold 15"
    elif cmd == "setprompt":
        if arg.strip():
            settings["system_prompt"] = arg.strip()
            reply = "Системный промпт обновлён."
        else:
            reply = "Формат: .setprompt <текст промпта>"
    elif cmd == "setpersona":
        if arg.strip():
            settings["persona_name"] = arg.strip()
            reply = f"Имя персонажа теперь: {arg.strip()}"
        else:
            reply = "Формат: .setpersona <имя>"
    elif cmd == "ping":
        reply = "pong 🏓"
    else:
        return False

    await context.bot.send_message(
        chat_id=chat_id,
        text=reply,
        business_connection_id=business_connection_id,
    )
    return True


# ---------- Обработчик всех апдейтов ----------

async def on_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Событие подключения/переподключения бота к бизнес-аккаунту — просто
    # логируем для диагностики, для логики бота больше не требуется.
    if update.business_connection:
        conn = update.business_connection
        print(f"[connected] connection_id={conn.id} account_user_id={conn.user.id}")
        return

    msg = update.business_message or update.edited_business_message
    if msg is None:
        return

    chat_id = msg.chat.id
    text = msg.text or msg.caption or ""

    is_me = bool(msg.from_user) and msg.from_user.id == ADMIN_ID

    if is_me:
        if await handle_command(text, chat_id, context):
            return
        last_owner_activity[chat_id] = time.time()
        history[chat_id].append(("me", text))
        return

    # Сообщение от собеседника
    history[chat_id].append(("them", text))

    if not settings["enabled"] or chat_id in paused_chats or is_owner_active(chat_id):
        return

    await asyncio.sleep(random.uniform(settings["delay_min"], settings["delay_max"]))

    try:
        reply_text = await generate_reply(chat_id)
    except Exception as e:
        print(f"[LLM error] {e}")
        return

    if not reply_text:
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=reply_text,
        business_connection_id=msg.business_connection_id,
    )
    history[chat_id].append(("me", reply_text))


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(TypeHandler(Update, on_update))
    print("Бот запущен. Подключи его в Settings -> Telegram Business -> Chatbots.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
