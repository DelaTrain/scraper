import pickle
import signal
import traceback
import shutil
import os
from datetime import datetime
from .algorithm import ScraperState


_interrupted = False
STATE_FILE = "scraper_state.pkl"
STATE_FILE_BACKUP = "scraper_state_backup.pkl"


def handle_interrupt(*_) -> None:
    global _interrupted
    print("Interrupt received, saving state...")
    _interrupted = True


def main(args: list[str]) -> None:
    if len(args) == 2:
        day = datetime.strptime(args[0], "%d.%m.%Y").date()
        starting_station = args[1]
        scraper_state = ScraperState(day, starting_station)
        print(f"Initialized scraper state for day {scraper_state.day} with starting station '{starting_station}'.")
    elif len(args) == 1 and args[0] == "export":
        return  # TODO: implement export
    else:
        try:
            with open(STATE_FILE, "rb") as f:
                scraper_state = pickle.load(f)
            assert isinstance(scraper_state, ScraperState)
            print(
                f"Resumed scraper state for day {scraper_state.day} with {len(scraper_state.stations)} stations and {len(scraper_state.trains)} trains scraped."
            )
        except (FileNotFoundError, AssertionError):
            print(
                "Failed to load scraper state.\nRerun with args to start fresh:\npython -m delatrain_scraper <DD.MM.YYYY> <station>"
            )
            return

    signal.signal(signal.SIGINT, handle_interrupt)
    try:
        while not _interrupted and not scraper_state.finished():
            scraper_state.scrape()
    except Exception as e:
        print("An error occurred. Saving state...")
        traceback.print_exception(e)

    if os.path.exists(STATE_FILE_BACKUP) and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE_BACKUP)
    if os.path.exists(STATE_FILE):
        shutil.move(STATE_FILE, STATE_FILE_BACKUP)
    with open(STATE_FILE, "wb") as f:
        pickle.dump(scraper_state, f)
    print("Scraper state saved. Exiting.")
