"""Unit tests for email_service.py — all SES calls are mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import email_service


# ── _email_html ────────────────────────────────────────────────────────────────

class TestEmailHtml:
    def test_contains_brand_name(self):
        html = email_service._email_html("Title", "<p>body</p>")
        assert "The Meat Ensemble" in html

    def test_contains_tagline(self):
        html = email_service._email_html("Title", "<p>body</p>")
        assert "monthly steak club" in html.lower()

    def test_contains_title(self):
        html = email_service._email_html("My Subject", "<p>body</p>")
        assert "My Subject" in html

    def test_contains_body_html(self):
        html = email_service._email_html("T", "<p>hello world</p>")
        assert "<p>hello world</p>" in html

    def test_cta_button_present_when_provided(self):
        html = email_service._email_html(
            "T", "<p>b</p>", cta_text="Vote now", cta_url="https://example.com/poll/1"
        )
        assert "Vote now" in html
        assert "https://example.com/poll/1" in html

    def test_cta_absent_when_not_provided(self):
        html = email_service._email_html("T", "<p>b</p>")
        assert "Vote now" not in html

    def test_is_valid_html_structure(self):
        html = email_service._email_html("T", "<p>b</p>")
        assert html.startswith("<!doctype html>")
        assert "</html>" in html

    def test_footer_disclaimer_present(self):
        html = email_service._email_html("T", "<p>b</p>")
        assert "member" in html.lower()


# ── _send ──────────────────────────────────────────────────────────────────────

class TestSend:
    def test_returns_false_when_no_sender(self, monkeypatch):
        monkeypatch.delenv("SES_FROM_ADDRESS", raising=False)
        with patch("email_service.boto3"):
            result = email_service._send(["a@b.com"], "subj", "body")
        assert result is False

    def test_no_ses_call_when_no_sender(self, monkeypatch):
        monkeypatch.delenv("SES_FROM_ADDRESS", raising=False)
        with patch("email_service.boto3") as mock_boto:
            email_service._send(["a@b.com"], "subj", "body")
        mock_boto.client.assert_not_called()

    def test_returns_false_when_no_recipients(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        with patch("email_service._client"):
            result = email_service._send([], "subj", "body")
        assert result is False

    def test_sends_plain_text(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service._send(["to@example.com"], "subj", "plain text")
        body = mock_ses.send_email.call_args[1]["Message"]["Body"]
        assert body["Text"]["Data"] == "plain text"

    def test_includes_html_when_provided(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service._send(["to@example.com"], "subj", "plain", html="<p>html</p>")
        body = mock_ses.send_email.call_args[1]["Message"]["Body"]
        assert "Html" in body
        assert body["Html"]["Data"] == "<p>html</p>"

    def test_omits_html_key_when_not_provided(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service._send(["to@example.com"], "subj", "plain")
        body = mock_ses.send_email.call_args[1]["Message"]["Body"]
        assert "Html" not in body

    def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            result = email_service._send(["to@example.com"], "subj", "body")
        assert result is True

    def test_returns_false_on_ses_error(self, monkeypatch):
        from botocore.exceptions import ClientError
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "bad"}}, "SendEmail"
        )
        with patch("email_service._client", return_value=mock_ses):
            result = email_service._send(["to@example.com"], "subj", "body")
        assert result is False


# ── send_poll_created ──────────────────────────────────────────────────────────

def _mock_db(emails=("a@b.com",)):
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [{"email": e} for e in emails]
    return db


class TestSendPollCreated:
    def _call(self, monkeypatch, poll=None):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        poll = poll or {"id": 1, "title": "November dinner",
                        "description": "", "end_date": "2025-11-30 18:00"}
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_poll_created(poll, _mock_db())
        return mock_ses.send_email.call_args[1]["Message"]

    def test_subject_contains_title(self, monkeypatch):
        msg = self._call(monkeypatch)
        assert "November dinner" in msg["Subject"]["Data"]

    def test_html_contains_poll_title(self, monkeypatch):
        msg = self._call(monkeypatch)
        assert "November dinner" in msg["Body"]["Html"]["Data"]

    def test_html_contains_description(self, monkeypatch):
        msg = self._call(monkeypatch, poll={
            "id": 1, "title": "T", "description": "Bring appetite", "end_date": None
        })
        assert "Bring appetite" in msg["Body"]["Html"]["Data"]

    def test_plain_text_contains_url(self, monkeypatch, monkeypatch_setenv=None):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        monkeypatch.setenv("APP_URL", "https://steakclub.example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_poll_created(
                {"id": 7, "title": "T", "description": "", "end_date": None}, _mock_db()
            )
        plain = mock_ses.send_email.call_args[1]["Message"]["Body"]["Text"]["Data"]
        assert "/poll/7" in plain


# ── send_polls_closing_soon ────────────────────────────────────────────────────

class TestSendPollsClosingSoon:
    def _call(self, monkeypatch, polls):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_polls_closing_soon(polls, _mock_db())
        return mock_ses.send_email.call_args[1]["Message"]

    def test_single_poll_subject_contains_title(self, monkeypatch):
        msg = self._call(monkeypatch, [
            {"id": 1, "title": "November dinner", "end_date": "2025-11-30 18:00"}
        ])
        assert "November dinner" in msg["Subject"]["Data"]

    def test_multiple_polls_subject_generic(self, monkeypatch):
        msg = self._call(monkeypatch, [
            {"id": 1, "title": "Poll A", "end_date": "2025-11-30 18:00"},
            {"id": 2, "title": "Poll B", "end_date": "2025-11-30 19:00"},
        ])
        subj = msg["Subject"]["Data"].lower()
        assert "polls" in subj or "tomorrow" in subj

    def test_html_lists_all_polls(self, monkeypatch):
        msg = self._call(monkeypatch, [
            {"id": 1, "title": "Poll Alpha", "end_date": "2025-11-30 18:00"},
            {"id": 2, "title": "Poll Beta",  "end_date": "2025-11-30 19:00"},
        ])
        html = msg["Body"]["Html"]["Data"]
        assert "Poll Alpha" in html
        assert "Poll Beta" in html


# ── send_polls_closed ──────────────────────────────────────────────────────────

class TestSendPollsClosed:
    def _call(self, monkeypatch, polls):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_polls_closed(polls, _mock_db())
        return mock_ses.send_email.call_args[1]["Message"]

    def test_single_poll_subject(self, monkeypatch):
        msg = self._call(monkeypatch, [{"id": 1, "title": "November dinner"}])
        assert "November dinner" in msg["Subject"]["Data"]

    def test_multiple_polls_subject_mentions_results(self, monkeypatch):
        msg = self._call(monkeypatch, [
            {"id": 1, "title": "A"}, {"id": 2, "title": "B"}
        ])
        assert "results" in msg["Subject"]["Data"].lower()

    def test_html_links_all_polls(self, monkeypatch):
        msg = self._call(monkeypatch, [
            {"id": 3, "title": "Gamma"}, {"id": 4, "title": "Delta"}
        ])
        html = msg["Body"]["Html"]["Data"]
        assert "Gamma" in html
        assert "Delta" in html


# ── send_password_reset ────────────────────────────────────────────────────────

class TestSendPasswordReset:
    def _call(self, monkeypatch, reset_url="https://example.com/reset/abc123"):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_password_reset("user@example.com", reset_url)
        return mock_ses.send_email.call_args[1]["Message"]

    def test_subject_mentions_password(self, monkeypatch):
        msg = self._call(monkeypatch)
        assert "password" in msg["Subject"]["Data"].lower()

    def test_sent_to_correct_address(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_ADDRESS", "from@example.com")
        mock_ses = MagicMock()
        with patch("email_service._client", return_value=mock_ses):
            email_service.send_password_reset("target@example.com", "https://x.com/r")
        dest = mock_ses.send_email.call_args[1]["Destination"]["ToAddresses"]
        assert dest == ["target@example.com"]

    def test_reset_url_in_plain_text(self, monkeypatch):
        msg = self._call(monkeypatch)
        assert "https://example.com/reset/abc123" in msg["Body"]["Text"]["Data"]

    def test_reset_url_in_html(self, monkeypatch):
        msg = self._call(monkeypatch)
        assert "https://example.com/reset/abc123" in msg["Body"]["Html"]["Data"]

    def test_html_cta_button_present(self, monkeypatch):
        msg = self._call(monkeypatch)
        html = msg["Body"]["Html"]["Data"]
        assert "reset" in html.lower()
