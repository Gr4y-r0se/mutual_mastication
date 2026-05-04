"""Unit tests for shared route utilities (mobile detection, security headers)."""

from __future__ import annotations

from routes import _is_mobile
from tests.conftest import text

# ── _is_mobile ─────────────────────────────────────────────────────────────────


class TestIsMobile:
    def test_iphone(self):
        assert _is_mobile(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        )

    def test_android(self):
        assert _is_mobile("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36")

    def test_ipad(self):
        assert _is_mobile(
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        )

    def test_blackberry(self):
        assert _is_mobile("BlackBerry9700/5.0.0.351 Profile/MIDP-2.1")

    def test_windows_phone(self):
        assert _is_mobile(
            "Mozilla/5.0 (compatible; MSIE 10.0; Windows Phone 8.0; Trident/6.0)"
        )

    def test_opera_mini(self):
        assert _is_mobile("Opera/9.80 (J2ME/MIDP; Opera Mini/9.80)")

    def test_desktop_mac(self):
        assert not _is_mobile(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

    def test_desktop_windows(self):
        assert not _is_mobile(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

    def test_empty_string(self):
        assert not _is_mobile("")

    def test_case_insensitive(self):
        assert _is_mobile("MOBILE/browser")


# ── Security headers ───────────────────────────────────────────────────────────


class TestSecurityHeaders:
    def test_x_frame_options(self, client):
        resp = client.get("/")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_x_content_type_options(self, client):
        resp = client.get("/")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_csp_frame_ancestors(self, client):
        resp = client.get("/")
        assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]

    def test_csp_default_src_self(self, client):
        resp = client.get("/")
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]

    def test_vary_user_agent(self, client):
        resp = client.get("/")
        assert resp.headers["Vary"] == "User-Agent"

    def test_referrer_policy(self, client):
        resp = client.get("/")
        assert resp.headers["Referrer-Policy"] == "same-origin"
