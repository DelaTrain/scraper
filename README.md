# DelaTrain Scraper

A tool to scrape, process and export railway data from the Polish State Railways (PKP) system and OpenStreetMap (OSM).


## Suggested usage

1. **Set up a Python environment**:

    Use the following commands to create and activate a virtual environment, then install the package:
    ```bash
    $ python -m venv .venv
    $ source .venv/bin/activate
    $ pip install .
    ```

    Or, if you are crazy enough to be using NixOS - `shell.nix` is provided for your convenience.

2. **Initialize PKP scraper**:

    Example command to start scraping from "Kraków Główny" station:
    ```bash
    $ python -m delatrain scraper reset "Kraków Główny" --day 09.01.2026 --ban LA
    ```

    A date few days in the future is recommended to ensure the scraper has enough time to process everything
    (should take about 30 hours with default sleep time). Also, you may want to skip certain train categories
    (like `LA` - buses in the region of Łódź - they have really weird station data).

3. *Pause and resume scraping (optional)*:

    You can pause the scraper at any time with `CTRL+C` and resume later with:
    ```bash
    $ python -m delatrain scraper continue
    ```

4. **Station fix-ups**:

    After scraping is done, you will probably need to fix some station data manually. Run the interactive fix-up tool:
    ```bash
    $ python -m delatrain fixup stations
    ```

    It will ask you to paste OpenStreetMap links for stations that could not be matched automatically and save your answers
    as a CSV file for even more automatic fixing in the future. Fix-up can also be stopped and resumed later.

5. **Pathfinding**:

    Next, run the pathfinding tool to find rails, simplify them and generate connections between stations (in that order):
    ```bash
    $ python -m delatrain paths reset
    ```

    Again, as it will take a few hours, you can pause and resume this process with:
    ```bash
    $ python -m delatrain paths continue
    ```

6. **Routing fix-ups**:

    After pathfinding is done, you may need to fix some routing data for trains. Run the interactive fix-up tool:
    ```bash
    $ python -m delatrain fixup routing
    ```

    It will prompt you about every section of every train route which has had an issue during pathfinding and allow you to
    add a new rail, skip the train for now or forcefully generate a connection, regardless of its length.

    You may also want to add custom rails and connections between stations that are missing them
    (or delete them if they are incorrect or you make a mistake):
    ```bash
    $ python -m delatrain fixup add "Start Station" "End Station"
    $ python -m delatrain fixup delete "Start Station" "End Station"
    ```

7. *Re-run routing after fix-ups (optional)*:

    If you have added or deleted any rails/connections manually, you may want to re-run pathfinding
    to recalculate routing data for all trains:
    ```bash
    $ python -m delatrain paths reset --routing
    ```

    After that, you should check the routing fix-up tool again to see if there are any remaining issues.

8. **Export data**:

    Finally, export all the data to a zip file:
    ```bash
    $ python -m delatrain export --chunked
    ```

    If you omit the `--chunked` option, a single large JSON file will be created instead.
    You can run the export command at any time to get the current state of the data.


## All command line options

The `delatrain` command-line tool provides several subcommands to scrape, fix, pathfind and export data.

-   **`scraper`** (alias: `s`): Scrape PKP data.

    -   **`continue`** (alias: `c`): Resume scraping from saved state.
    -   **`reset`** (alias: `r`): Start scraping fresh from a given station and day.
        -   Arguments:
            -   `station` (string): Starting station name.
        -   Options:
            -   `-d`, `--day` (string): Day to scrape data for in `DD.MM.YYYY` format (defaults to tomorrow if omitted).
            -   `-b`, `--ban` (string): Comma-separated list of train categories to skip (e.g. `IC,TLK`).

-   **`paths`** (alias: `p`): Find rails and connections.

    -   **`continue`** (alias: `c`): Resume pathfinding from saved state.
    -   **`reset`** (alias: `r`): Start fresh pathfinding from a given station.
        -   Options:
            -   `-i`, `--interval` (int): Resampling interval in meters for found rails (default: `200`).
            -   `-m`, `--maxspeed` (int): Default max speed in km/h for broken edges (default: `160`).
            -   `-r`, `--routing`: Only reset routing data without recalculating rails. When this is used, the above options are ignored.

-   **`export`** (alias: `e`): Export all data to JSON.

    -   Options:
        -   `-c`, `--chunked`: Export data to a chunked zip (writes multiple `.json` files inside a `.zip`).

-   **`fixup`** (alias: `f`): Perform manual fix-up for various data.
    -   **`stations`** (alias: `s`): Interactively fix station data.
    -   **`routing`** (alias: `r`): Interactively fix routing data for trains.
    -   **`add`** (alias: `a`): Add a custom rail between two stations.
        -   Arguments:
            -   `start` (string): Start station name.
            -   `end` (string): End station name.
        -   Options:
            -   `-m`, `--maxspeed` (int): Max speed in km/h for the new rail (default: uses paths settings).
    -   **`delete`** (alias: `d`): Delete a rail between two stations (any rail, not necessarily a custom one).
        -   Arguments:
            -   `start` (string): Start station name.
            -   `end` (string): End station name.

-   `-s`, `--sleep`: Seconds to sleep between iterations (can be used with any subcommand).

---

Notes:

-   State, exports and fixup CSVs are written into the `output` directory by default.
-   Interactive fix-up commands will prompt for input during execution.
