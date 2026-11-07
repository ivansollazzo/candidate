"""Maintenance commands, run inside the backend container:

    docker compose exec backend python -m app.cli https-off

https-off: turns HTTPS off (Settings › HTTPS), e.g. when the app can no longer be opened from any of the
addresses listed. The web server is back on plain HTTP within a few seconds.
"""

import sys

from sqlmodel import Session

from app.db import engine
from app.services import app_settings


def https_off() -> None:
    with Session(engine) as session:
        settings = app_settings.load(session)
        settings.https_mode = "off"
        session.add(settings)
        session.commit()
    print("HTTPS turned off: the app answers over plain HTTP within a few seconds.")


def main(args: list[str]) -> int:
    if args[:1] == ["https-off"]:
        https_off()
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
