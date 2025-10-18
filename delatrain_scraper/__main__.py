from .data_sources.rozklad_pkp import get_train_urls_from_station
from datetime import date
from pprint import pprint

pprint(get_train_urls_from_station("Bielsko-Biała Główna", date.today()))
