import time
import functools
from typing import Callable, Any

def timeit(func: Callable) -> Callable:
    """Декоратор для замера времени выполнения функции."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            end_time = time.perf_counter()
            duration = end_time - start_time
            # Выводим в консоль, чтобы видеть в реальном времени
            print(f"⏱️ [Время] {func.__name__} выполнен за {duration:.4f} сек.")
    return wrapper
