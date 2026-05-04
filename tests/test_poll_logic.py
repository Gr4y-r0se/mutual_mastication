"""Unit tests for _build_calendar_data — the pure calendar-construction helper."""

from __future__ import annotations

import calendar

from routes.poll_routes import _build_calendar_data


def _opt(id_, label, vote_count=0):
    return {"id": id_, "label": label, "vote_count": vote_count}


# ── Invalid input ──────────────────────────────────────────────────────────────


class TestInvalidInput:
    def test_returns_none_for_non_date_label(self):
        assert _build_calendar_data([_opt(1, "Hawksmoor")], set(), {}) is None

    def test_returns_none_for_partially_valid(self):
        opts = [_opt(1, "2025-11-15"), _opt(2, "not-a-date")]
        assert _build_calendar_data(opts, set(), {}) is None

    def test_empty_options_returns_empty_list(self):
        assert _build_calendar_data([], set(), {}) == []


# ── Month structure ────────────────────────────────────────────────────────────


class TestMonthStructure:
    def test_single_month(self):
        opts = [_opt(1, "2025-11-15"), _opt(2, "2025-11-22")]
        result = _build_calendar_data(opts, set(), {})
        assert len(result) == 1

    def test_month_metadata(self):
        result = _build_calendar_data([_opt(1, "2025-11-15")], set(), {})
        m = result[0]
        assert m["year"] == 2025
        assert m["month"] == 11
        assert m["month_name"] == "November"

    def test_multiple_months_in_chronological_order(self):
        opts = [_opt(1, "2025-12-01"), _opt(2, "2025-11-15"), _opt(3, "2026-01-10")]
        result = _build_calendar_data(opts, set(), {})
        assert len(result) == 3
        assert [m["month"] for m in result] == [11, 12, 1]
        assert [m["year"] for m in result] == [2025, 2025, 2026]

    def test_weeks_are_monday_first(self):
        # 2025-11-01 is a Saturday (index 5 in Mon-first week)
        result = _build_calendar_data([_opt(1, "2025-11-01")], set(), {})
        week0 = result[0]["weeks"][0]
        saturday_cell = next(c for c in week0 if c is not None and c["day"] == 1)
        sat_idx = week0.index(saturday_cell)
        assert sat_idx == 5  # Mon=0 … Sat=5

    def test_padding_cells_are_none(self):
        result = _build_calendar_data([_opt(1, "2025-11-15")], set(), {})
        first_week = result[0]["weeks"][0]
        # November 2025 starts on a Saturday, so Mon–Fri are None
        nones = [c for c in first_week if c is None]
        assert len(nones) == 5


# ── Option placement ───────────────────────────────────────────────────────────


class TestOptionPlacement:
    def _find_day(self, result, day):
        for week in result[0]["weeks"]:
            for cell in week:
                if cell is not None and cell["day"] == day:
                    return cell
        return None

    def test_option_day_has_option_data(self):
        result = _build_calendar_data([_opt(1, "2025-11-15")], set(), {})
        cell = self._find_day(result, 15)
        assert cell is not None
        assert cell["option"] is not None
        assert cell["option"]["id"] == 1

    def test_non_option_day_has_none_option(self):
        result = _build_calendar_data([_opt(1, "2025-11-15")], set(), {})
        cell = self._find_day(result, 1)
        assert cell is not None
        assert cell["option"] is None

    def test_vote_count_propagated(self):
        result = _build_calendar_data([_opt(1, "2025-11-15", vote_count=4)], set(), {})
        cell = self._find_day(result, 15)
        assert cell["option"]["vote_count"] == 4


# ── Voted state ────────────────────────────────────────────────────────────────


class TestVotedState:
    def _find_opt_cell(self, result, opt_id):
        for week in result[0]["weeks"]:
            for cell in week:
                if cell and cell.get("option") and cell["option"]["id"] == opt_id:
                    return cell
        return None

    def test_voted_flag_true_for_my_vote(self):
        opts = [_opt(1, "2025-11-15"), _opt(2, "2025-11-22")]
        result = _build_calendar_data(opts, {1}, {})
        assert self._find_opt_cell(result, 1)["option"]["voted"] is True

    def test_voted_flag_false_for_other(self):
        opts = [_opt(1, "2025-11-15"), _opt(2, "2025-11-22")]
        result = _build_calendar_data(opts, {1}, {})
        assert self._find_opt_cell(result, 2)["option"]["voted"] is False

    def test_voters_list_propagated(self):
        opts = [_opt(1, "2025-11-15")]
        voters = {1: ["alice", "bob"]}
        result = _build_calendar_data(opts, set(), voters)
        cell = self._find_opt_cell(result, 1)
        assert cell["option"]["voters"] == ["alice", "bob"]

    def test_empty_voters_when_not_provided(self):
        result = _build_calendar_data([_opt(1, "2025-11-15")], set(), {})
        cell = self._find_opt_cell(result, 1)
        assert cell["option"]["voters"] == []
