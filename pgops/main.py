"""PGOps entrypoint: one Caspian handler, two channels (Telegram + Email)."""
import os

from dotenv import load_dotenv

load_dotenv()

from caspian_sdk import CommClient

from pgops.core.db import init_db
from pgops.core.logging import configure_logging, get_logger
from pgops.router import route_message

log = get_logger("main")


def main() -> None:
    configure_logging()
    init_db()
    client = CommClient()

    email = client.connect_email(username=os.getenv("EMAIL_USERNAME", "pgops"))
    log.info("channel_connected", channel="email", address=email["address"])
    tg = client.connect_telegram(bot_token=os.environ["TELEGRAM_BOT_TOKEN"])
    log.info("channel_connected", channel="telegram", address=tg["address"])

    @client.on_message
    def handle(message):
        try:
            route_message(message)
        except Exception:  # never crash the listener
            log.exception("handler_error", conv=getattr(message, "conversation_id", None))
            message.reply("Sorry, something went wrong on my side. Please try again.")

    log.info("listening")
    client.listen()


if __name__ == "__main__":
    main()
