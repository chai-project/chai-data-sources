# pylint: disable=line-too-long, missing-module-docstring

from enum import Enum
from functools import lru_cache, wraps
from typing import Dict, Optional, TypeVar, Callable, Union

import pendulum

V = TypeVar("V")
K = TypeVar("K")
T = TypeVar("T")


class Minutes(Enum):  # minutes as divisors of 30 (and 60)
    """ Enumeration of all valid minute intervals that are divisors of 30 to allow hour aligning. """
    MIN_1 = 1
    MIN_2 = 2
    MIN_3 = 3
    MIN_5 = 5
    MIN_6 = 6
    MIN_10 = 10
    MIN_15 = 15
    MIN_30 = 30


# pylint: disable=missing-class-docstring
class InvalidTimestampError(Exception):  # the value is not a valid timestamp due to its range or its type
    pass


def optional(source: Optional[Dict[K, V]], key: K, default: V = None,
             mapping: Optional[Callable[[V], T]] = None) -> Optional[Union[V, T]]:
    """
    Safely access a resource assuming the resource either exists or is None.
    :param source: A dictionary of values, which is possibly empty or None.
    :param key: The desired key to access in the dictionary.
    :param default: The default value to return when the value associated with `key` cannot be found.
    :param mapping: An optional mapping to apply to the value or default before returning it.
    :return: The value in the dictionary if the key exists, otherwise the default value if one is provided.
             If a mapping is provided the value in the dictionary or the default if it is exists is mapped.
             Returns None in all other cases.
    """
    if source is None:
        return default if mapping is None or default is None else mapping(default)
    try:
        element = source[key]
        return element if mapping is None else mapping(element)
    except (KeyError, IndexError):
        return default if mapping is None or default is None else mapping(default)


def round_date(date: pendulum.DateTime, *, minutes: Minutes, round_down: bool) -> pendulum.DateTime:
    """
    Round a data up or down to the nearest minute using the hours as boundaries (e.g. round to 00:00).
    :param date: The date to round.
    :param minutes: The minutes to round to; must be a divisor of 60.
    :param round_down: Whether to round down to the nearest multiple of `minutes`, or up.
    :return: The date rounded down or up to the nearest multiple of ``minutes.
    """
    minutes = minutes.value
    assert 60 % minutes == 0  # ensure that `minutes` is a divisor of 60 to guarantee consistent behaviour across hours.
    remainder = 0 if round_down else (date.minute % minutes) + date.second / 60
    return date.set(minute=(date.minute // minutes) * minutes, second=0).add(minutes=0 if remainder == 0 else minutes)


def convert_timestamp_ms(value: str) -> pendulum.DateTime:
    """
    Convert a Unix millisecond timestamp string into a DateTime instance.
    :param value: the Unix millisecond timestamp given as a string.
    :return: a DateTime instance set to the given timestamp value and assigned the Europe/London timezone.
    :raises:
        InvalidTimestampError: The timestamp is not a valid integer, or exceeds the range of a valid timestamp.
    """
    if not value.isdigit(): raise InvalidTimestampError  # noqa, pylint: disable=multiple-statements
    timestamp = int(value) / 1_000
    try:
        return pendulum.from_timestamp(timestamp, tz="Europe/London")
    except ValueError as exc:
        raise InvalidTimestampError from exc


def timed_lru_cache(seconds: int, maxsize: int = 128):
    """
    A timed variant of the default LRU cache implemented in Python that invalidates the cache after a given timeout.
    **Note**: this decorator clears the entire cache associated with the function.
              The lifetime applies to the cache as a whole, not to individual articles.
    :param seconds: The lifetime of the cache.
    :param maxsize: The maximum number of elements to store in the cache before older entries are removed.
    """

    def wrapper_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = seconds
        func.expiration = pendulum.now().add(seconds=func.lifetime)

        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if pendulum.now() >= func.expiration:
                func.cache_clear()
                func.expiration = pendulum.now().add(seconds=func.lifetime)

            return func(*args, **kwargs)

        return wrapped_func

    return wrapper_cache
