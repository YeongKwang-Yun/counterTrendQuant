import os
import logging
from telebot import TeleBot
from quant.bybit.asset.balance import get_bybit_balance
from common.env_loader import load_project_env

ENV_PATH = load_project_env()
logger = logging.getLogger(__name__)
logger.info(f"ENV loaded from: {ENV_PATH}")

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = TeleBot(TELEGRAM_BOT_TOKEN)

@bot.message_handler(commands=['CT_Balance'])
def handle_main_balance(message):
    logger.info(f"Received /CT_Balance command from chat ID: {message.chat.id}")
    api_key = BYBIT_API_KEY
    api_secret = BYBIT_API_SECRET
    get_bybit_balance(api_key, api_secret, "CT_Balance")

if __name__ == "__main__":
    logger.info("Starting Telegram Bot polling loop...")
    bot.infinity_polling(skip_pending=True)