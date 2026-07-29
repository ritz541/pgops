import logging


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
