from time import strftime


def log(message: str) -> None:
    timestamp = strftime("%H:%M:%S")
    print(f"[{timestamp}]  {message}")
