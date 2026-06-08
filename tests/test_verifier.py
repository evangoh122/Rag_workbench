import unittest
from api.services.verifier import verify_numeric

class TestVerifier(unittest.TestCase):
    def test_verify_numeric_exact(self):
        self.assertTrue(verify_numeric(100.0, 100.0))

    def test_verify_numeric_within_tolerance(self):
        # 0.4% difference
        self.assertTrue(verify_numeric(100.4, 100.0))
        self.assertTrue(verify_numeric(99.6, 100.0))

    def test_verify_numeric_outside_tolerance(self):
        # 0.6% difference
        self.assertFalse(verify_numeric(100.6, 100.0))
        self.assertFalse(verify_numeric(99.4, 100.0))

    def test_verify_numeric_zero(self):
        self.assertTrue(verify_numeric(0.0, 0.0))
        self.assertFalse(verify_numeric(0.1, 0.0))

if __name__ == "__main__":
    unittest.main()
