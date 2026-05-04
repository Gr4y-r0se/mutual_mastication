"""Unit tests for config.py — regex constants and secret-key loading."""
from __future__ import annotations

import config


# ── USERNAME_RE ────────────────────────────────────────────────────────────────

class TestUsernameRe:
    def test_valid_lowercase(self):
        assert config.USERNAME_RE.match("alice")

    def test_valid_with_digits(self):
        assert config.USERNAME_RE.match("alice123")

    def test_valid_with_underscore(self):
        assert config.USERNAME_RE.match("alice_smith")

    def test_valid_uppercase(self):
        assert config.USERNAME_RE.match("ALICE")

    def test_valid_minimum_length(self):
        assert config.USERNAME_RE.match("abc")

    def test_valid_maximum_length(self):
        assert config.USERNAME_RE.match("a" * 32)

    def test_invalid_too_short(self):
        assert not config.USERNAME_RE.match("ab")

    def test_invalid_too_long(self):
        assert not config.USERNAME_RE.match("a" * 33)

    def test_invalid_special_char(self):
        assert not config.USERNAME_RE.match("al!ce")

    def test_invalid_space(self):
        assert not config.USERNAME_RE.match("al ice")

    def test_invalid_empty(self):
        assert not config.USERNAME_RE.match("")

    def test_invalid_hyphen(self):
        assert not config.USERNAME_RE.match("al-ice")


# ── EMAIL_RE ───────────────────────────────────────────────────────────────────

class TestEmailRe:
    def test_valid_standard(self):
        assert config.EMAIL_RE.match("user@example.com")

    def test_valid_subdomain(self):
        assert config.EMAIL_RE.match("user@mail.example.co.uk")

    def test_valid_plus_address(self):
        assert config.EMAIL_RE.match("user+tag@example.com")

    def test_invalid_no_at(self):
        assert not config.EMAIL_RE.match("notanemail")

    def test_invalid_no_local_part(self):
        assert not config.EMAIL_RE.match("@example.com")

    def test_invalid_no_tld(self):
        assert not config.EMAIL_RE.match("user@nodot")

    def test_invalid_empty(self):
        assert not config.EMAIL_RE.match("")


# ── _load_secret_key ───────────────────────────────────────────────────────────

class TestLoadSecretKey:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "env-secret-value")
        assert config._load_secret_key() == "env-secret-value"

    def test_reads_from_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setattr(config, "BASE_DIR", tmp_path)
        (tmp_path / ".secret_key").write_text("file-secret-value")
        assert config._load_secret_key() == "file-secret-value"

    def test_generates_and_saves_key_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setattr(config, "BASE_DIR", tmp_path)
        key = config._load_secret_key()
        assert len(key) == 64  # 32 random bytes → 64 hex chars
        saved = (tmp_path / ".secret_key").read_text().strip()
        assert saved == key

    def test_env_takes_priority_over_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "env-wins")
        monkeypatch.setattr(config, "BASE_DIR", tmp_path)
        (tmp_path / ".secret_key").write_text("file-loses")
        assert config._load_secret_key() == "env-wins"

    def test_generated_key_is_consistent_on_second_call(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setattr(config, "BASE_DIR", tmp_path)
        key1 = config._load_secret_key()
        key2 = config._load_secret_key()
        assert key1 == key2  # second call reads the file written by the first
