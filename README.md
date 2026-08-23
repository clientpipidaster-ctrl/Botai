# Автоответчик через Telegram Business + Gemini (без api_id/api_hash)

Никакого my.telegram.org, никаких блокировок сайта — только токен от
@BotFather, который выдаётся прямо в чате внутри Telegram.

## 1. Термукс

Если ещё не установлен — с F-Droid: https://f-droid.org/packages/com.termux/
(не из Play Store, там старая версия).

```bash
pkg update && pkg upgrade -y
pkg install python -y
pip install python-telegram-bot google-genai python-dotenv httpx[socks]
```

Если при установке `cryptography` вылезет ошибка сборки — сначала:
```bash
pkg install python-cryptography -y
```
и повтори `pip install` выше.

## 2. Создать бота

1. В Telegram открой **@BotFather**
2. `/newbot` -> придумай имя и username (должен заканчиваться на `bot`)
3. Получишь токен вида `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` —
   это и есть `BOT_TOKEN`

## 3. Включить Business Mode боту

1. В @BotFather: `/mybots` -> выбери своего бота
2. **Bot Settings -> Business Mode -> Turn on**

Без этого шага Telegram не даст подключить бота к бизнес-аккаунту.

## 4. Подключить бота к своему аккаунту

1. В Telegram: **Настройки -> Telegram Business -> Chatbots**
   (если пункта "Telegram Business" нет — обнови приложение Telegram
   до последней версии)
2. Впиши username своего бота, нажми добавить
3. Разреши боту **отвечать на сообщения** (permission "Reply to messages")
4. Выбери, к каким чатам бот имеет доступ — можно ко всем 1-на-1 чатам,
   можно исключить контакты из списка, если нужно отвечать только
   незнакомым людям

## 5. Ключ Gemini

https://aistudio.google.com/apikey — создай ключ, это бесплатно.
Если сайт не открывается напрямую — впиши прокси в `PROXY_URL` в `.env`
(тот же прокси, что использовался бы и раньше).

## 6. Настройка и запуск

```bash
cp .env.example .env
nano .env   # впиши BOT_TOKEN, GEMINI_API_KEY, при нужде PROXY_URL
python bot.py
```

В логе должно появиться `[connected] owner_user_id=... connection_id=...`
после того, как ты подключил бота в настройках Telegram (шаг 4) — это
подтверждение, что связка сработала.

## 7. Чтобы бот не умирал при выключенном экране

```bash
termux-wake-lock
```

И в настройках Android: `Батарея -> Termux -> без ограничений`.

## 8. Чтобы бот пережил закрытие Termux

```bash
pkg install tmux -y
tmux new -s tgbot
python bot.py
# Ctrl+B, затем D — свернуть, не убивая процесс
# tmux attach -t tgbot — вернуться
```

## Команды бота

Пиши себе в любой чат, где ты автор сообщения — ответ бот пришлёт тебе
отдельным сообщением, собеседник его не увидит.

| Команда | Что делает |
|---|---|
| `.help` | список команд |
| `.status` | текущие настройки |
| `.pause` / `.resume` | вкл/выкл автоответы |
| `.setdelay 10 60` | задержка перед ответом, сек |
| `.setthreshold 15` | порог твоего простоя, мин |
| `.setprompt <текст>` | новый системный промпт |
| `.setpersona <имя>` | сменить имя персонажа |
| `.ping` | проверка, что бот жив |

## Почему это лучше прошлого варианта (Telethon-userbot)

- Не нужен `api_id`/`api_hash` -> не нужен `my.telegram.org` -> нет
  проблемы с блокировками сайта в России вообще
- Это официальная, поддерживаемая функция Telegram (Business Chatbots),
  а не автоматизация личного аккаунта в обход правил — рисков бана
  аккаунта за сам факт использования нет
- Настройка проще: токен от BotFather получается прямо в приложении

## Ограничение

Telegram Business — функция личных (не групповых) чатов. Групповые чаты
и каналы через эту схему не автоответишь — там по-прежнему нужен был бы
обычный бот через `/start` или userbot-подход.
