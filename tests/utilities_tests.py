import unittest

import pendulum

from chai_data_sources.utilities import optional, round_date, convert_timestamp_ms, Minutes, InvalidTimestampError


class UtilitiesTests(unittest.TestCase):

    def testOptional(self):
        data_dict = {"a": 1, "b": 2, "c": 3}

        self.assertIsNone(optional(None, "d"))
        self.assertEqual(5, optional(None, "d", 5))

        self.assertEqual(1, optional(data_dict, "a"))
        self.assertEqual(1, optional(data_dict, "a", 4))

        self.assertIsNone(optional(data_dict, "d"))
        self.assertEqual(4, optional(data_dict, "d", 4))

        self.assertEqual(2, optional(data_dict, "a", 4, lambda x: x * 2))
        self.assertEqual(8, optional(data_dict, "d", 4, lambda x: x * 2))
        self.assertIsNone(optional(data_dict, "d", mapping=lambda x: x * 2))

    def testRoundDate(self):
        date = pendulum.datetime(2022, 5, 28, 10, 7, 2)

        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 5, 0),
                         round_date(date, minutes=Minutes.MIN_5, round_down=True))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 0, 0),
                         round_date(date, minutes=Minutes.MIN_10, round_down=True))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 10, 0),
                         round_date(date, minutes=Minutes.MIN_5, round_down=False))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 9, 0),
                         round_date(date, minutes=Minutes.MIN_3, round_down=False))

        date = pendulum.datetime(2022, 5, 28, 10, 10, 0)  # special case, already rounded for some divisors
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 10, 0),
                         round_date(date, minutes=Minutes.MIN_5, round_down=False))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 9, 0),
                         round_date(date, minutes=Minutes.MIN_3, round_down=True))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 12, 0),
                         round_date(date, minutes=Minutes.MIN_3, round_down=False))

        end = pendulum.datetime(2022, 5, 28, 10, 52, 37)  # special case, hour moves as well for some divisors
        self.assertEqual(pendulum.datetime(2022, 5, 28, 10, 55, 0),
                         round_date(end, minutes=Minutes.MIN_5, round_down=False))
        self.assertEqual(pendulum.datetime(2022, 5, 28, 11, 0, 0),
                         round_date(end, minutes=Minutes.MIN_10, round_down=False))

    def testConvertTimestamp(self):
        test_date = pendulum.datetime(2022, 5, 28, 10, 7, 2, tz="Europe/London")
        self.assertEqual(test_date, convert_timestamp_ms(str(test_date.int_timestamp * 1_000)))

        with self.assertRaises(InvalidTimestampError):
            convert_timestamp_ms("timestamp")  # not a number

        with self.assertRaises(InvalidTimestampError):
            convert_timestamp_ms(str(test_date.int_timestamp * 1_000_000))  # too big


if __name__ == '__main__':
    unittest.main()
