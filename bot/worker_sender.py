import os, asyncio, json, time
from aiokafka import AIOKafkaConsumer
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
BOT_TOKEN = os.getenv("BOT_TOKEN")

def kb_from_payload_buttons(buttons):
    # buttons: [["Title","callback_data"], ...] в одну/несколько строк?
    rows, row = [], []
    for i, (t, c) in enumerate(buttons):
        row.append(InlineKeyboardButton(text=t, callback_data=c))
        if len(row) == 2:
            rows.append(row); row=[]
    if row: rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def main():
    bot = Bot(BOT_TOKEN)
    consumer = AIOKafkaConsumer("reminder.fire", bootstrap_servers=KAFKA_BOOTSTRAP, group_id="reminders-sender")
    await consumer.start()
    per_chat_last = {}  # chat_id -> ts
    try:
        async for msg in consumer:
            payload = json.loads(msg.value.decode())
            chat_id = payload["chat_id"]
            text = payload["text"]
            buttons = payload.get("buttons") or []
            silent = payload.get("silent", True)

            # simple throttle per chat
            now = time.time()
            last = per_chat_last.get(chat_id, 0)
            dt = now - last
            if dt < 1.0:
                await asyncio.sleep(1.0 - dt)
            try:
                await bot.send_message(chat_id, text, reply_markup=kb_from_payload_buttons(buttons), disable_notification=silent)
                per_chat_last[chat_id] = time.time()
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                continue
            except TelegramForbiddenError:
                # пользователь заблокировал бота — можно пометить в БД, но для простоты — пропускаем
                continue
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(main())
