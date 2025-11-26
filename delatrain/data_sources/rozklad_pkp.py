import requests
from datetime import date, time
from bs4 import BeautifulSoup, Tag
import re
from ..structures.stations import StationTrack
from ..structures.trains import TrainSummary, TrainStop, Train

_STATION_REQUEST_URL = "https://old.rozklad-pkp.pl/bin/trainsearch.exe/pn?ld=mobil&protocol=https:&="
_REQUEST_ARGS = {
    "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0"},
    "cookies": {"HAFAS-PROD-OLD-CL-SSL": "HAFAS-PROD-OLD-03"},
}
_TRAIN_NUMBER_REGEX = re.compile(r"^(\D+)(\d+)([^,]*),?$")


def _extract_train_number(full_number: str) -> tuple[str, int, str | None]:
    match = _TRAIN_NUMBER_REGEX.fullmatch(full_number)
    cat, num, name = match.groups()  # type: ignore
    name = name.strip()
    return cat.strip(), int(num), name if name else None


def _generate_payload(station: str, day: date, disambiguated: bool = False) -> dict[str, str]:
    payload = {
        "trainname": "",
        "stationname": station if disambiguated else station.replace(" ", "+"),
        "selectDate": "oneday",
        "date": day.strftime("%d.%m.%y"),
        "time": "",
        "start": ["yes", "Szukaj"] if disambiguated else "Szukaj",
    }
    return payload


def _ensure_disambiguated(html_raw: str, station: str, day: date) -> BeautifulSoup:
    html = BeautifulSoup(html_raw, "lxml")
    check = html.find("td", class_="errormessage")
    if not check:
        return html
    check = check.string.strip()  # type: ignore
    if "jednoznaczne" not in check:
        return html
    select = html.find("select", class_="error")
    option = next(filter(lambda o: o.string.strip() == station, select.find_all("option")))  # type: ignore
    value = str(option["value"])
    url = str(html.find("form", attrs={"name": "ts_trainsearch"})["action"])  # type: ignore
    payload = _generate_payload(value, day, True)
    response = requests.post(url, payload, **_REQUEST_ARGS)  # type: ignore
    return BeautifulSoup(response.text, "lxml")


def get_train_urls_from_station(station_name: str, date: date) -> list[TrainSummary]:
    response = requests.post(_STATION_REQUEST_URL, _generate_payload(station_name, date), **_REQUEST_ARGS)  # type: ignore
    html = _ensure_disambiguated(response.text, station_name, date)
    trains: list[TrainSummary] = []
    for trs in html.find_all("tr", class_=["zebracol-1", "zebracol-2"]):
        tds = trs.find_all("td")
        full_number = next(tds[0].stripped_strings)
        category, number, _ = _extract_train_number(full_number)
        url = tds[0].a["href"]  # type: ignore
        days = tds[-1].string.strip()  # type: ignore
        trains.append(TrainSummary(category, number, url, days))  # type: ignore
    return trains


def _parse_train(full_name: str, stations: list[Tag]) -> Train:
    category, number, name = _extract_train_number(full_name)
    stops = []
    for row in stations:
        tds = row.find_all("td")
        station_name = tds[1].a.string.strip()  # type: ignore
        arrival = tds[2].string.strip()  # type: ignore
        arrival_time = time.fromisoformat(arrival) if arrival else None
        departure = tds[4 if len(tds) > 6 else 3].string.strip()  # type: ignore
        departure_time = time.fromisoformat(departure) if departure else None
        track = tds[-1].string.strip() if len(tds) > 5 else None  # type: ignore
        track_parsed = StationTrack.from_pkp_string(track)
        stops.append(TrainStop(station_name, arrival_time, departure_time, track_parsed))
    return Train(category, number, name, stops)


def get_full_train_info(url: str, *additional_params: str) -> list[Train]:
    response = requests.get(url, **_REQUEST_ARGS)  # type: ignore
    html = BeautifulSoup(response.text, "lxml")

    subtrains: list[tuple[str, list[Tag]]] = []
    main_content = html.find("div", id="tq_trainroute_content_table_alteAnsicht")
    if not main_content:
        return []
    stations_table: Tag = main_content.table  # type: ignore
    for row in stations_table.find_all("tr", class_=["zebracol-1", "zebracol-2"]):
        tds = row.find_all("td")
        full_name = tds[-2 if len(tds) > 5 else -1].string.strip()  # type: ignore
        if not full_name:
            subtrains[-1][1].append(row)
            continue
        if subtrains:
            subtrains[-1][1].append(row)
        subtrains.append((full_name, [row]))

    trains = [_parse_train(f, s) for f, s in subtrains]
    any_info = main_content.find("span", class_="bold")
    if not any_info:
        for train in trains:
            train.params = set(additional_params)
        return trains
    info: Tag = any_info.parent  # type: ignore
    info_list = set(list(info.stripped_strings)[1:])
    info_list.update(additional_params)
    for train in trains:
        train.params = info_list
    return trains
