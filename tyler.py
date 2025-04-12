import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from telegram import Bot
from dotenv import load_dotenv
import os
import json

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
TONVIEWER_LINK = f"https://tonviewer.com/{WALLET_ADDRESS}"
TONAPI_URL = f"https://tonapi.io/v2/blockchain/accounts/{WALLET_ADDRESS}/transactions"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_ID")
MIN_AMOUNT = 5  # Минимальная сумма в TON

# Файл для хранения истории
PROCESSED_TXS_FILE = "processed_txs.json"


def load_processed_txs():
    try:
        if os.path.exists(PROCESSED_TXS_FILE):
            with open(PROCESSED_TXS_FILE, "r") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()


def save_processed_txs(txs):
    with open(PROCESSED_TXS_FILE, "w") as f:
        json.dump(list(txs), f)


def format_address(addr):
    return f"{addr[:4]}...{addr[-4:]}" if len(addr) > 8 else addr


async def get_transactions():
    async with aiohttp.ClientSession() as session:
        async with session.get(TONAPI_URL) as resp:
            if resp.status == 200:
                return await resp.json()
            print(f"Ошибка API: {resp.status}")
            return None


async def process_tx(transaction, bot, processed_txs):
    tx_hash = transaction.get("hash")
    if not tx_hash or tx_hash in processed_txs:
        return False

    # Основные данные
    timestamp = datetime.fromtimestamp(transaction["utime"], timezone.utc) + timedelta(hours=3)
    date_str = timestamp.strftime("%d.%m.%Y %H:%M:%S")

    # Определяем тип и сумму
    in_msg = transaction.get("in_msg", {})
    out_msgs = transaction.get("out_msgs", [])

    if in_msg and not out_msgs:
        tx_type = "📥 Входящая"
        amount = int(in_msg.get("value", 0)) / 1e9
        from_addr = in_msg.get("source", {}).get("address", "Unknown")
        to_addr = WALLET_ADDRESS
    else:
        tx_type = "📤 Исходящая"
        amount = int(out_msgs[0].get("value", 0)) / 1e9 if out_msgs else 0
        from_addr = WALLET_ADDRESS
        to_addr = out_msgs[0].get("destination", {}).get("address", "Unknown") if out_msgs else "Unknown"

    if amount < MIN_AMOUNT:
        return False

    # Формируем сообщение
    message = (
        f"{tx_type} транзакция\n"
        f"💎 Сумма: <b>{amount:.2f} TON</b>\n"
        f"🕒 Дата: <i>{date_str}</i>\n"
        f"🔍 <a href='{TONVIEWER_LINK}'>Просмотреть в TonViewer</a>"
    )

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        processed_txs.add(tx_hash)
        print(f"Отправлено: {amount:.2f} TON ({tx_type})")
        return True
    except Exception as e:
        print(f"Ошибка Telegram: {e}")
        return False


async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    processed_txs = load_processed_txs()

    while True:
        print("Проверяем новые транзакции...")
        try:
            data = await get_transactions()
            if data and "transactions" in data:
                for tx in data["transactions"][:4]:  # Последние 10 транзакций
                    await process_tx(tx, bot, processed_txs)
        except Exception as e:
            print(f"Ошибка: {e}")

        save_processed_txs(processed_txs)
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Работа завершена")