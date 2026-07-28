"""PGOps entrypoint: one Caspian handler, two channels (Telegram + Email)."""
import os

from dotenv import load_dotenv

load_dotenv()

from caspian_sdk import CommClient

from pgops.core.db import init_db
from pgops.router import route_message


def main() -> None:
    init_db()
    client = CommClient()

    email = client.connect_email(username=os.getenv("EMAIL_USERNAME", "pgops"))
    print("PGOps email:", email["address"], flush=True)
    tg = client.connect_telegram(bot_token=os.environ["TELEGRAM_BOT_TOKEN"])
    print("PGOps telegram:", tg["address"], flush=True)

    @client.on_message
    def handle(message):
        try:
            route_message(message)
        except Exception as e:  # never crash the listener
            print(f"[ERR] {e!r}", flush=True)
            message.reply("Sorry, something went wrong on my side. Please try again.")

    print("PGOps listening…", flush=True)
    client.listen()


if __name__ == "__main__":
    main()
