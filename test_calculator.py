import unittest
from calculator import add, subtract, multiply, divide

class TestCalculator(unittest.TestCase):
    """Unit tests for the calculator module."""

    def test_add_positive_numbers(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_negative_numbers(self):
        self.assertEqual(add(-1, -1), -2)

    def test_add_mixed_numbers(self):
        self.assertEqual(add(-1, 1), 0)

    def test_subtract_positive_numbers(self):
        self.assertEqual(subtract(5, 3), 2)

    def test_subtract_negative_result(self):
        self.assertEqual(subtract(3, 5), -2)

    def test_multiply_positive_numbers(self):
        self.assertEqual(multiply(3, 4), 12)

    def test_multiply_by_zero(self):
        self.assertEqual(multiply(5, 0), 0)

    def test_divide_positive_numbers(self):
        self.assertEqual(divide(10, 2), 5.0)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            divide(10, 0)

    def test_divide_float_result(self):
        self.assertEqual(divide(7, 2), 3.5)

if __name__ == '__main__':
    unittest.main()
