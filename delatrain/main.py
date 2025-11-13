import pandas as pd
import pickle
import signal
import traceback
import shutil
import os
import jsonpickle
from time import sleep, time
from typing import Callable
from datetime import datetime, timedelta
from argparse import ArgumentParser
from .algorithm import ScraperState


_interrupted = 0
_sleep = 1

STATE_FILE = "output/scraper_state.pkl"
STATE_FILE_BACKUP = "output/scraper_state_backup.pkl"
FIXUP_FILE = "output/saved_fixups.csv"
EXPORT_FILE = "output/delatrain"


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


def get_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="delatrain", description="Scrape train and rail data for the Delatrain service.")
    parser.add_argument("-s", "--sleep", type=int, help="Seconds to sleep between iterations.")
    sub = parser.add_subparsers(dest="command", required=True, help="Subcommand to run.")

    scraper = sub.add_parser("scraper", aliases=["s"], help="Scrape PKP data.")
    scraper_sub = scraper.add_subparsers(dest="scraper_command", required=True, help="Scraper subcommand to run.")
    scraper_sub.add_parser("continue", aliases=["c"], help="Resume scraping from saved state.")
    scraper_reset = scraper_sub.add_parser(
        "reset", aliases=["r"], help="Start scraping fresh from a given station and day."
    )
    scraper_reset.add_argument("station", type=str, help="Starting station name.")
    scraper_reset.add_argument(
        "-d", "--day", type=str, help="Day to scrape data for, in DD.MM.YYYY format (tomorrow if empty)."
    )

    paths = sub.add_parser("paths", aliases=["p"], help="Find rails and connections.")
    paths_sub = paths.add_subparsers(dest="paths_command", required=True, help="Paths subcommand to run.")
    paths_sub.add_parser("continue", aliases=["c"], help="Resume pathfinding from saved state.")
    paths_reset = paths_sub.add_parser("reset", aliases=["r"], help="Start fresh pathfinding from a given station.")
    paths_reset.add_argument(
        "-r",
        "--radius",
        type=int,
        default=15,
        help="Radius in kilometers to search for adjacent stations (default: 15).",
    )
    paths_reset.add_argument(
        "-i", "--interval", type=int, default=200, help="Resampling interval in meters for found rails (default: 200)."
    )

    sub.add_parser("export", aliases=["e"], help="Export all data to JSON.")
    sub.add_parser("fixup", aliases=["f"], help="Perform manual fix-up for missing station data.")

    return parser


def read_state() -> ScraperState | None:
    try:
        with open(STATE_FILE, "rb") as f:
            scraper_state = pickle.load(f)
        assert isinstance(scraper_state, ScraperState)
        print(
            f"Resumed scraper state for day {scraper_state.day} with {len(scraper_state.stations)} station(s), {len(scraper_state.trains)} train(s) and {len(scraper_state.rails)} rail(s)."
        )
        return scraper_state
    except (FileNotFoundError, AssertionError):
        print("Failed to load scraper state - fresh start required.")


def graceful_shutdown(function: Callable[[ScraperState], None], state: ScraperState) -> None:
    signal.signal(signal.SIGINT, handle_interrupt)
    try:
        function(state)
    except Exception as e:
        print("An error occurred. Saving state...")
        traceback.print_exception(e)

    if os.path.exists(STATE_FILE_BACKUP) and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE_BACKUP)
    if os.path.exists(STATE_FILE):
        shutil.move(STATE_FILE, STATE_FILE_BACKUP)
    print("Saving started...")
    with open(STATE_FILE, "wb") as f:
        pickle.dump(state, f)
    print("Scraper state saved. Exiting.")


def scraper_main(state: ScraperState) -> None:
    print("Starting scraping...")
    while _interrupted == 0 and not state.is_scrape_finished():
        time_start = time()
        print("\n--- New iteration of scraping ---")
        state.scrape()
        time_end = time()
        elapsed = time_end - time_start
        if elapsed < _sleep:
            sleep(_sleep - elapsed)


def fixup_main(state: ScraperState) -> None:
    print("Starting fixup process...")
    if not os.path.exists(FIXUP_FILE):
        csv = pd.DataFrame(columns=[0, 1, 2])
    else:
        csv = pd.read_csv(FIXUP_FILE, header=None)
    while _interrupted == 0 and not state.is_fixup_finished():
        print("\n--- New iteration of fixup ---")
        state.fixup(csv)
        sleep(_sleep)
    csv.to_csv(FIXUP_FILE, index=False, header=False)


def export_main(state: ScraperState) -> None:
    print("Starting export...")
    data = state.get_export_data()
    jsonpickle.set_encoder_options("json", ensure_ascii=False)
    with open(f"{EXPORT_FILE}.json", "w") as f:
        f.write(jsonpickle.encode(data, unpicklable=False, make_refs=False, indent=2))  # type: ignore
    print("Export completed.")


def paths_main(state: ScraperState) -> None:
    print("Starting pathfinding...")
    if state.is_pathfinding_finished():
        print("Pathfinding is already finished or was never started.")
        return
    while _interrupted == 0 and not state.is_pathfinding_finished():
        print("\n--- New iteration of pathfinding ---")
        state.pathfind()
        sleep(_sleep)


def main() -> None:
    global _sleep
    parser = get_parser()
    args = parser.parse_args()
    if args.sleep:
        _sleep = args.sleep
    else:
        _sleep = 10 if args.command in ("scraper", "s") else 1

    if args.command in ("scraper", "s") and args.scraper_command in ("reset", "r"):
        day = datetime.strptime(args.day, "%d.%m.%Y").date() if args.day else datetime.now().date() + timedelta(days=1)
        starting_station = args.station
        scraper_state = ScraperState(day, starting_station)
        print(f"Initialized scraper state for day {scraper_state.day} with starting station '{starting_station}'.")
    else:
        scraper_state = read_state()
        if not scraper_state:
            return

    if args.command in ("scraper", "s"):
        graceful_shutdown(scraper_main, scraper_state)
    elif args.command in ("fixup", "f"):
        graceful_shutdown(fixup_main, scraper_state)
    elif args.command in ("export", "e"):
        export_main(scraper_state)
    elif args.command in ("paths", "p"):
        if args.paths_command in ("reset", "r"):
            scraper_state.reset_pathfinding(args.radius, args.interval)
        graceful_shutdown(paths_main, scraper_state)
