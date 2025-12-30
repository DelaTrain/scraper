from time import strftime
from functools import wraps
from typing import Callable, TYPE_CHECKING


def log(message: str) -> None:
    timestamp = strftime("%H:%M:%S")
    print(f"[{timestamp}]  {message}")


def oneshot_cache[R, **P](func: Callable[P, R]) -> Callable[P, R]:
    if TYPE_CHECKING:  # silence all warnings
        raise NotImplementedError

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.result = func(*args, **kwargs)
            wrapper.has_run = True
        return wrapper.result

    wrapper.has_run = False
    wrapper.result = None
    return wrapper
