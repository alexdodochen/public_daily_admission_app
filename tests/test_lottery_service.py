"""Pure-logic tests for lottery_service (draw + round_robin)."""
from __future__ import annotations

from app.services import lottery_service as ls


def _pts(pairs):
    return [{"doctor": d, "name": n, "chart_no": f"C{n}"} for d, n in pairs]


def test_draw_respects_ticket_count():
    patients = _pts([
        ("A", "a1"), ("A", "a2"), ("A", "a3"),
        ("B", "b1"), ("B", "b2"),
    ])
    tickets = {"A": 2, "B": 1}
    drawn = ls.draw(patients, tickets, seed=42)
    assert len(drawn["A"]) == 2
    assert len(drawn["B"]) == 1


def test_draw_deterministic_with_seed():
    patients = _pts([("A", "a1"), ("A", "a2"), ("A", "a3")])
    d1 = ls.draw(patients, {"A": 2}, seed=42)
    d2 = ls.draw(patients, {"A": 2}, seed=42)
    assert [p["name"] for p in d1["A"]] == [p["name"] for p in d2["A"]]


def test_draw_non_schedule_doctors_go_last():
    patients = _pts([("A", "a1"), ("Z", "z1"), ("Z", "z2")])
    drawn = ls.draw(patients, {"A": 1}, seed=1)
    # Z is non-schedule; should still be present but after A in iteration order
    keys = list(drawn.keys())
    assert keys.index("A") < keys.index("Z")
    assert len(drawn["Z"]) == 2  # all non-schedule kept


def test_round_robin_order():
    """A1 -> B1 -> C1 -> A2 -> B2 -> A3 (C exhausted early)."""
    drawn = {
        "A": _pts([("A", "a1"), ("A", "a2"), ("A", "a3")]),
        "B": _pts([("B", "b1"), ("B", "b2")]),
        "C": _pts([("C", "c1")]),
    }
    tickets = {"A": 3, "B": 2, "C": 1}
    out = ls.round_robin(drawn, tickets)
    names = [p["name"] for p in out]
    assert names == ["a1", "b1", "c1", "a2", "b2", "a3"]


def test_round_robin_non_schedule_last():
    drawn = {
        "A": _pts([("A", "a1"), ("A", "a2")]),
        "Z": _pts([("Z", "z1")]),
    }
    tickets = {"A": 2}  # Z not in tickets
    out = ls.round_robin(drawn, tickets)
    names = [p["name"] for p in out]
    # A block fires first, then Z gets appended once per round
    # True round-robin after order is [A, Z]: a1, z1, a2
    assert names[0] == "a1"
    assert "z1" in names
