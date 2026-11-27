import functools
import logging
import time
from typing import Any, Callable

log = logging.getLogger("timing")


def timeit(func: Callable) -> Callable:
    """Декоратор для замера времени выполнения функции (пишет на уровне DEBUG)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            log.debug("⏱️ %s выполнен за %.4f сек.", func.__name__, time.perf_counter() - start)
    return wrapper
