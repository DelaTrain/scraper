import pandas as pd
import pickle
import signal
import traceback
import shutil
import os
import jsonpickle
from time import sleep
from datetime import datetime
from .algorithm import ScraperState


_interrupted = 0
STATE_FILE = "output/scraper_state.pkl"
STATE_FILE_BACKUP = "output/scraper_state_backup.pkl"
FIXUP_FILE = "output/saved_fixups.csv"
EXPORT_FILE = "output/delatrain"
_SLEEP_BETWEEN_SCRAPES = 10  # seconds
_SLEEP_BETWEEN_FIXUPS = 1  # seconds


def handle_interrupt(*_) -> None:
    global _interrupted
    _interrupted += 1
    if _interrupted == 1:
        print("Interrupt received, saving state...")
    elif _interrupted == 5:
        print("Force exiting now.")
        exit(1)
    else:
        print(f"Interrupt received {_interrupted} times. Press Ctrl+C 5 times to force exit.")


def main(args: list[str]) -> None:
    if len(args) == 2:
        day = datetime.strptime(args[0], "%d.%m.%Y").date()
        starting_station = args[1]
        scraper_state = ScraperState(day, starting_station)
        args.insert(0, "resume")
        print(f"Initialized scraper state for day {scraper_state.day} with starting station '{starting_station}'.")
    elif len(args) != 1:
        print(
            "Usage:\npython -m delatrain_scraper <args...>\n\nPossible argument combinations:\n\t<DD.MM.YYYY> <station> - start fresh\n\tresume - resume scraping from saved state\n\tfixup - fix missing station and track data\n\texport - export all data to JSON and msgpack\n\t(no args) - show this help message"
        )
        return
    elif args[0] not in ("resume", "export", "fixup"):
        print("Bad argument. Run without arguments to see usage.")
        return
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

    if args[0] == "export":
        data = scraper_state.get_export_data()
        with open(f"{EXPORT_FILE}.json", "w") as f:
            f.write(jsonpickle.encode(data, unpicklable=False, make_refs=False, indent=2))  # type: ignore
        print("Export completed.")
        return

    signal.signal(signal.SIGINT, handle_interrupt)
    try:
        if args[0] == "resume":
            while _interrupted == 0 and not scraper_state.is_scrape_finished():
                print("\n--- New iteration of scraping ---")
                scraper_state.scrape()
                sleep(_SLEEP_BETWEEN_SCRAPES)

        elif args[0] == "fixup":
            print("Starting fixup process...")
            if not os.path.exists(FIXUP_FILE):
                csv = pd.DataFrame(columns=[0, 1, 2])
            else:
                csv = pd.read_csv(FIXUP_FILE, header=None)
            while _interrupted == 0 and not scraper_state.is_fixup_finished():
                print("\n--- New iteration of fixup ---")
                scraper_state.fixup(csv)
                sleep(_SLEEP_BETWEEN_FIXUPS)
            csv.to_csv(FIXUP_FILE, index=False, header=False)

    except Exception as e:
        print("An error occurred. Saving state...")
        traceback.print_exception(e)

    if os.path.exists(STATE_FILE_BACKUP) and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE_BACKUP)
    if os.path.exists(STATE_FILE):
        shutil.move(STATE_FILE, STATE_FILE_BACKUP)
    print("Saving started...")
    with open(STATE_FILE, "wb") as f:
        pickle.dump(scraper_state, f)
    print("Scraper state saved. Exiting.")
