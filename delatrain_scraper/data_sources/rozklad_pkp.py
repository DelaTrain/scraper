import requests
from datetime import date
from bs4 import BeautifulSoup, Tag
import re
from ..structures import TrainSummary, Train

_STATION_REQUEST_URL = "https://old.rozklad-pkp.pl/bin/trainsearch.exe/pn?ld=mobil&protocol=https:&="
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"}
_TRAIN_NUMBER_REGEX = re.compile(r"^(\D+)(\d+)([^,]*),?$")


def _extract_train_number(full_number: str) -> tuple[str, int, str | None]:
    match = _TRAIN_NUMBER_REGEX.fullmatch(full_number)
    cat, num, name = match.groups()  # type: ignore
    name = name.strip()
    return cat.strip(), int(num), name if name else None


def get_train_urls_from_station(station_name: str, date: date) -> list[TrainSummary]:
    payload = {
        "trainname": "",
        "stationname": station_name.replace(" ", "+"),
        "selectDate": "oneday",
        "date": date.strftime("%d.%m.%y"),
        "time": "",
        "start": "Szukaj",
    }
    response = requests.post(_STATION_REQUEST_URL, payload, headers=_HEADERS)
    html = BeautifulSoup(response.text, "lxml")
    trains: list[TrainSummary] = []
    for trs in html.find_all("tr", class_=["zebracol-1", "zebracol-2"]):
        tds = trs.find_all("td")
        full_number = next(tds[0].stripped_strings)
        category, number, _ = _extract_train_number(full_number)
        url = tds[0].a["href"]  # type: ignore
        days = tds[-1].string
        trains.append(TrainSummary(category, number, url, days))  # type: ignore
    return trains


def _parse_train(full_name: str, stations: list[Tag]) -> Train:
    raise NotImplementedError  # TODO


def get_full_train_info(url: str) -> list[Train]:
    response = requests.get(url, headers=_HEADERS)
    html = BeautifulSoup(response.text, "lxml")

    subtrains: list[tuple[str, list[Tag]]] = []
    stations_table: Tag = html.find("div", id="tq_trainroute_content_table_alteAnsicht").table  # type: ignore
    for row in stations_table.find_all("tr", class_=["zebracol-1", "zebracol-2"]):
        tds = row.find_all("td")
        full_name = tds[-2].string.strip()  # type: ignore
        if not full_name:
            subtrains[-1][1].append(row)
            continue
        if subtrains:
            subtrains[-1][1].append(row)
        subtrains.append((full_name, [row]))

    trains = [_parse_train(f, s) for f, s in subtrains]
    return trains
