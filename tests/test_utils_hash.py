import pytest

from utils.hash import generate_hash, verify_hash


class TestGenerateHash:
    def test_default_sha256(self):
        result = generate_hash("hello")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_sha256_known_value(self):
        import hashlib
        expected = hashlib.sha256(b"hello").hexdigest()
        assert generate_hash("hello") == expected

    def test_md5(self):
        import hashlib
        expected = hashlib.md5(b"hello").hexdigest()
        assert generate_hash("hello", "md5") == expected

    def test_sha1(self):
        import hashlib
        expected = hashlib.sha1(b"hello").hexdigest()
        assert generate_hash("hello", "sha1") == expected

    def test_empty_string(self):
        result = generate_hash("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_unicode_string(self):
        result = generate_hash("hello wörld")
        assert isinstance(result, str)

    def test_deterministic(self):
        assert generate_hash("test") == generate_hash("test")

    def test_different_inputs_different_hashes(self):
        assert generate_hash("a") != generate_hash("b")


class TestVerifyHash:
    def test_correct_hash(self):
        h = generate_hash("secret")
        assert verify_hash("secret", h) is True

    def test_incorrect_hash(self):
        assert verify_hash("secret", "wrong_hash") is False

    def test_different_algorithm(self):
        import hashlib
        h = hashlib.md5(b"hello").hexdigest()
        assert verify_hash("hello", h, "md5") is True

    def test_case_sensitive(self):
        h = generate_hash("Hello")
        assert verify_hash("hello", h) is False

    def test_empty_string(self):
        h = generate_hash("")
        assert verify_hash("", h) is True
