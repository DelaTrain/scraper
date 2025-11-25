import pandas as pd
import pickle
import signal
import traceback
import shutil
import os
import jsonpickle
import zipfile
from time import sleep, time
from typing import Callable
from datetime import datetime, timedelta
from argparse import ArgumentParser
from functools import partial
from .algorithm import ScraperState
from .utils import log


_interrupted: int = 0
_sleep: float = 0.0

STATE_FILE = "output/scraper_state.pkl"
STATE_FILE_BACKUP = "output/scraper_state_backup.pkl"
FIXUP_FILE = "output/station_fixups.csv"
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
    parser.add_argument("-s", "--sleep", type=float, help="Seconds to sleep between iterations.")
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
        "-i", "--interval", type=int, default=200, help="Resampling interval in meters for found rails (default: 200)."
    )

    export = sub.add_parser("export", aliases=["e"], help="Export all data to JSON.")
    export.add_argument("-c", "--chunked", action="store_true", help="Export data to a chunked zip.")
    
    fixup = sub.add_parser("fixup", aliases=["f"], help="Perform manual fix-up for various data.")
    fixup_sub = fixup.add_subparsers(dest="fixup_command", required=True, help="Fix-up subcommand to run.")
    fixup_sub.add_parser("stations", aliases=["s"], help="Interactively fix station data.")
    fixup_sub.add_parser("load", aliases=["l"], help="Load rail fix-ups based on previous additions.")
    fixup_add = fixup_sub.add_parser("add", aliases=["a"], help="Add a new rail manually.")
    fixup_add.add_argument("from_station", type=str, help="Starting station name.")
    fixup_add.add_argument("to_station", type=str, help="Ending station name.")
    fixup_add.add_argument("-s", "--speed", type=int, default=120, help="Max speed on the rail in km/h (default: 120).")
    fixup_add.add_argument(
        "-f",
        "--follow",
        type=str,
        help="Train category and number to follow. Makes multiple connections instead of a direct line.",
    )

    return parser


def read_state() -> ScraperState | None:
    try:
        with open(STATE_FILE, "rb") as f:
            scraper_state = pickle.load(f)
        assert isinstance(scraper_state, ScraperState)
        log(
            f"Resumed scraper state for day {scraper_state.day} with {len(scraper_state.stations)} station(s), {len(scraper_state.trains)} train(s) and {len(scraper_state.rails)} rail(s)."
        )
        return scraper_state
    except (FileNotFoundError, AssertionError):
        log("Failed to load scraper state - fresh start required.")


def graceful_shutdown(function: Callable[[ScraperState], None], state: ScraperState) -> None:
    signal.signal(signal.SIGINT, handle_interrupt)
    try:
        function(state)
    except Exception as e:
        log("An error occurred. Saving state...")
        traceback.print_exception(e)

    if os.path.exists(STATE_FILE_BACKUP) and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE_BACKUP)
    if os.path.exists(STATE_FILE):
        shutil.move(STATE_FILE, STATE_FILE_BACKUP)
    log("Saving started...")
    with open(STATE_FILE, "wb") as f:
        pickle.dump(state, f)
    log("Scraper state saved. Exiting.")


def scraper_main(state: ScraperState) -> None:
    log("Starting scraping...")
    while _interrupted == 0 and not state.is_scrape_finished():
        time_start = time()
        print("\n----------  New iteration of scraping  ----------")
        state.scrape()
        time_end = time()
        elapsed = time_end - time_start
        if elapsed < _sleep:
            sleep(_sleep - elapsed)


def fixup_stations_main(state: ScraperState) -> None:
    log("Starting station fix-up process...")
    log(f"{len(state.broken_stations)} stations need to be fixed.")
    if not os.path.exists(FIXUP_FILE):
        csv = pd.DataFrame(columns=[0, 1, 2])
    else:
        csv = pd.read_csv(FIXUP_FILE, header=None)
    while _interrupted == 0 and not state.is_fixup_finished():
        print("\n----------  New iteration of fix-up  ----------")
        state.fixup(csv)
        sleep(_sleep)
    csv.to_csv(FIXUP_FILE, index=False, header=False)


def export_main(state: ScraperState, chunked: bool) -> None:
    log("Starting export...")
    jsonpickle.set_encoder_options("json", ensure_ascii=False)
    encoder = partial(jsonpickle.encode, unpicklable=False, make_refs=False, indent=2)
    data = state.get_export_data()
    if not chunked:
        with open(f"{EXPORT_FILE}.json", "w") as f:
            f.write(encoder(data))  # type: ignore
        log(f"Exported as {EXPORT_FILE}.json")
        return
    with zipfile.ZipFile(f"{EXPORT_FILE}.zip", "w", zipfile.ZIP_DEFLATED) as f:  # TODO: actually chunk it
        f.writestr("all.json", encoder(data))  # type: ignore
        f.writestr("index.json", encoder({"chunks": ["all"]}))  # type: ignore
    log(f"Exported as {EXPORT_FILE}.zip")


def paths_main(state: ScraperState) -> None:
    log("Starting pathfinding...")
    if state.is_pathfinding_finished():
        log("Pathfinding is already finished or was never started.")
        return
    log(f"{len(state.rails_to_find)} stations queued.")
    state.prepare_pathfinding()
    while _interrupted == 0 and not state.is_pathfinding_finished():
        print("\n----------  New iteration of pathfinding  ----------")
        state.pathfind()
        sleep(_sleep)


def main() -> None:
    global _sleep
    parser = get_parser()
    args = parser.parse_args()
    if args.sleep and args.sleep >= 0:
        _sleep = args.sleep
    else:
        _sleep = 10.0 if args.command in ("scraper", "s") else 0.5

    if args.command in ("scraper", "s") and args.scraper_command in ("reset", "r"):
        day = datetime.strptime(args.day, "%d.%m.%Y").date() if args.day else datetime.now().date() + timedelta(days=1)
        starting_station = args.station
        scraper_state = ScraperState(day, starting_station)
        log(f"Initialized scraper state for day {scraper_state.day} with starting station '{starting_station}'.")
    else:
        scraper_state = read_state()
        if not scraper_state:
            return

    match args.command:
        case "scraper" | "s":
            graceful_shutdown(scraper_main, scraper_state)
        case "fixup" | "f":
            match args.fixup_command:
                case "stations" | "s":
                    graceful_shutdown(fixup_stations_main, scraper_state)
                case _:
                    log(str(args))
        case "export" | "e":
            export_main(scraper_state, args.chunked)
        case "paths" | "p":
            if args.paths_command in ("reset", "r"):
                scraper_state.reset_pathfinding(args.interval)
            graceful_shutdown(paths_main, scraper_state)
