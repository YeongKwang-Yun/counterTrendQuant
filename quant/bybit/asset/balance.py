from pybit.unified_trading import HTTP
import os
import logging

from telegram.common.utils import send_to_telegram
from common.env_loader import load_project_env
logger = logging.getLogger(__name__)

ENV_PATH = load_project_env()

TELEGRAM_TEST_CHANNEL_ID = os.getenv("TELEGRAM_TEST_CHANNEL_ID")

def get_bybit_balance(api_key, api_secret, label):
    result = {
        "status": "error",
        "wallet_balance": None,
        "equity": None,
        "message": ""
    }

    try:
        session = HTTP(
            testnet=False,
            api_key=api_key,
            api_secret=api_secret
        )
        response = session.get_wallet_balance(accountType="UNIFIED")

        if response["retCode"] == 0:
            usdt_balance = next(
                (coin for coin in response["result"]["list"][0]["coin"] if coin["coin"] == "USDT"),
                None
            )

            if usdt_balance:
                result["status"] = "success"
                result["wallet_balance"] = usdt_balance.get("walletBalance")
                result["equity"] = usdt_balance.get("equity")
                result["message"] = "Balance fetched successfully"

                balance_message = (
                    f"Bybit {label} Quant Account Balance\n\n"
                    f"Wallet Balance: {result['wallet_balance']} USDT\n"
                    f"Equity: {result['equity']} USDT\n"
                )
            else:
                result["message"] = "USDT balance not found!"
                balance_message = result["message"]
        else:
            result["message"] = f"Error fetching balance: {response['retMsg']}"
            balance_message = result["message"]

        if TELEGRAM_TEST_CHANNEL_ID:
            send_to_telegram(TELEGRAM_TEST_CHANNEL_ID, balance_message, "None")
        else:
            logger.warning("TELEGRAM_TEST_CHANNEL_ID is not set; skipping telegram send")

        return result

    except Exception as e:
        logger.exception("Error fetching Bybit balance")
        result["message"] = str(e)
        return result