from .data_sources.rozklad_pkp import get_train_urls_from_station, get_full_train_info
from datetime import date
from pprint import pprint

t = get_train_urls_from_station("Bielsko-Biała Główna", date.today())
print(f"Found {len(t)} trains")
pprint(get_full_train_info(t[0].url))
