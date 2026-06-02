import pytest

from utils.security import generate_token, constant_time_compare


class TestGenerateToken:
    def test_default_length(self):
        token = generate_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_custom_length(self):
        token = generate_token(length=16)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_url_safe(self):
        token = generate_token()
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_unique_tokens(self):
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_different_lengths(self):
        t1 = generate_token(length=8)
        t2 = generate_token(length=64)
        assert len(t1) > 0
        assert len(t2) > 0


class TestConstantTimeCompare:
    def test_equal_strings(self):
        assert constant_time_compare("abc", "abc") is True

    def test_different_strings(self):
        assert constant_time_compare("abc", "xyz") is False

    def test_different_lengths(self):
        assert constant_time_compare("abc", "abcd") is False

    def test_empty_strings(self):
        assert constant_time_compare("", "") is True

    def test_empty_vs_nonempty(self):
        assert constant_time_compare("", "a") is False

    def test_unicode_not_supported(self):
        with pytest.raises(TypeError):
            constant_time_compare("hello wörld", "hello wörld")
