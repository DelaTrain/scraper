import requests
from datetime import date
from bs4 import BeautifulSoup
from ..structures import TrainSummary

STATION_REQUEST_URL = "https://old.rozklad-pkp.pl/bin/trainsearch.exe/pn?ld=mobil&protocol=https:&="
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"


def extract_train_number(full_number: str) -> tuple[str, int]:
    category = "".join(filter(str.isupper, full_number))
    number = int("".join(filter(str.isdigit, full_number)))
    return category, number


def get_train_urls_from_station(station_name: str, date: date) -> list[TrainSummary]:
    payload = {
        "trainname": "",
        "stationname": station_name.replace(" ", "+"),
        "selectDate": "oneday",
        "date": date.strftime("%d.%m.%y"),
        "time": "",
        "start": "Szukaj",
    }
    headers = {
        "User-Agent": USER_AGENT,
    }
    response = requests.post(STATION_REQUEST_URL, payload, headers=headers)
    html = BeautifulSoup(response.text, "lxml")
    trains = []
    for trs in html.find_all("tr", class_=["zebracol-1", "zebracol-2"]):
        tds = trs.find_all("td")
        full_number = next(tds[0].stripped_strings)
        category, number = extract_train_number(full_number)
        url = tds[0].a["href"]  # type: ignore
        days = tds[-1].string
        trains.append(TrainSummary(category, number, url, days))  # type: ignore
    return trains
