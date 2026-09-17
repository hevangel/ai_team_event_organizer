"""End-to-end smoke test for the backend: REST API + MCP tools.

Run from backend/:  uv run python scripts/smoke_test.py
Uses a throwaway SQLite database; does not touch real data.
"""

import asyncio
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Config is read at import time -> set env before importing the app.
_tmp_db = Path(tempfile.gettempdir()) / "event_organizer_smoke.db"
if _tmp_db.exists():
    _tmp_db.unlink()
os.environ["DB_PATH"] = str(_tmp_db)
os.environ["TESTING_MODE"] = "true"
# Display override for the login-page MCP hints (would normally be CLI flags).
os.environ["MCP_PUBLIC_HOSTNAME"] = "smoke.example.com"
os.environ["MCP_PUBLIC_SUBPATH"] = "team"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from app.errors import ApiError  # noqa: E402
from app.main import app  # noqa: E402
from app.mcp_server import mcp  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED += 1
        print(f" FAIL {name} {detail}")


def tool_text(res) -> str:
    if res.content:
        return str(res.content[0].text)
    return ""


def main() -> None:
    with TestClient(app) as client:
        # ---- health & unauthenticated state
        r = client.get("/api/health")
        check("health", r.status_code == 200)

        r = client.get("/api/state")
        check("state without login -> unauthenticated payload", r.status_code == 200 and r.json()["authenticated"] is False)
        check(
            "mcp display URL override in config",
            r.json()["config"]["mcp_url_override"] == "http://smoke.example.com/team",
        )

        # ---- first login becomes admin (no --admin designated)
        alice = TestClient(app)
        r = alice.post("/api/login", json={"userid": "alice"})
        check("alice logs in", r.status_code == 200)
        check("alice is admin (first login)", r.json()["user"]["is_admin"] is True)

        # ---- second login is not admin
        bob = TestClient(app)
        r = bob.post("/api/login", json={"userid": "bob"})
        check("bob logs in", r.status_code == 200)
        check("bob is not admin", r.json()["user"]["is_admin"] is False)

        # ---- admin configures the event
        closes = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        r = alice.put(
            "/api/admin/settings",
            json={
                "patch": {
                    "event_title": "Team Offsite 2026",
                    "budget_amount": 50,
                    "budget_type": "per_head",
                    "headcount_limit": 10,
                    "preference_mode": "strong_weak",
                    "allow_venue_suggestions": True,
                    "anonymous_voting": False,
                    "hide_live_counts": False,
                    "voting_closes_at": closes,
                }
            },
        )
        check(
            "admin sets settings",
            r.status_code == 200 and r.json()["event_title"] == "Team Offsite 2026",
        )

        r = alice.put("/api/admin/settings", json={"patch": {"preference_mode": "bogus"}})
        check("bad setting rejected", r.status_code == 422)

        # ---- admin sets slots
        slots = [
            {"date": "2026-09-21", "start_time": "11:00", "end_time": "14:00"},  # Monday
            {"date": "2026-09-21", "start_time": "17:00", "end_time": "20:00"},
            {"date": "2026-09-23", "start_time": "11:00", "end_time": "14:00"},  # Wednesday
            {"date": "2026-09-25", "start_time": "17:00", "end_time": "21:00"},  # Friday
        ]
        r = alice.put("/api/admin/slots", json={"slots": slots})
        check("admin sets 4 slots", r.status_code == 200 and r.json()["slot_count"] == 4)

        # ---- admin adds venues
        r = alice.post(
            "/api/admin/venues",
            json={
                "name": "Sushi Zanmai",
                "type": "food",
                "description": "Casual sushi",
                "estimated_cost": 25,
                "address": "1 Market St",
                "slot_ids": [1, 3],
            },
        )
        check("admin adds food venue", r.status_code == 200 and r.json()["venue_id"] == 1)
        r = alice.post(
            "/api/admin/venues",
            json={"name": "Bowling Alley", "type": "activity", "estimated_cost": 15},
        )
        check("admin adds activity venue", r.status_code == 200 and r.json()["venue_id"] == 2)

        r = alice.post("/api/admin/venues", json={"name": "No Type"})
        check("venue without type rejected", r.status_code == 422)

        # ---- bob votes via REST
        state_bob = bob.get("/api/state").json()
        check("bob sees 4 slots", len(state_bob["slots"]) == 4)
        check("bob sees results (live counts on)", state_bob["results"]["visible"] is True)

        r = bob.put(
            "/api/vote",
            json={
                "availability": [
                    {"slot_id": 1, "level": "strong"},
                    {"slot_id": 2, "level": "weak"},
                    {"slot_id": 99, "level": "yes"},
                ],
                "food_venue_ids": [1],
                "activity_venue_ids": [2],
            },
        )
        check("vote with unknown slot rejected", r.status_code == 422)

        r = bob.put(
            "/api/vote",
            json={
                "availability": [
                    {"slot_id": 1, "level": "strong"},
                    {"slot_id": 2, "level": "weak"},
                ],
                "food_venue_ids": [1],
                "activity_venue_ids": [2],
            },
        )
        check("bob saves vote", r.status_code == 200)

        # ---- bob suggests a venue live
        r = bob.post(
            "/api/venues",
            json={
                "name": "Rock Climbing Gym",
                "type": "activity",
                "estimated_cost": 30,
                "description": "Beginner friendly",
            },
        )
        check("bob suggests venue", r.status_code == 200 and r.json()["venue_id"] == 3)

        state_alice = alice.get("/api/state").json()
        check("alice sees suggested venue live", any(v["id"] == 3 for v in state_alice["venues"]))
        suggested = next(v for v in state_alice["venues"] if v["id"] == 3)
        check("suggestion tagged with suggester", suggested["suggested_by"] == "bob")
        check("live results show bob's picks", state_alice["results"]["food"]["1"]["count"] == 1)
        check("live results include names", state_alice["results"]["food"]["1"]["voters"] == ["bob"])
        check("availability counts strong", state_alice["results"]["availability"]["1"]["strong"] == 1)

        # ---- non-admin blocked from admin endpoints
        r = bob.put("/api/admin/settings", json={"patch": {}})
        check("bob blocked from admin API", r.status_code == 403)

        # ---- hide_live_counts hides results from voters
        alice.put("/api/admin/settings", json={"patch": {"hide_live_counts": True}})
        state_bob = bob.get("/api/state").json()
        check("live counts hidden from bob", state_bob["results"]["visible"] is False)
        state_alice = alice.get("/api/state").json()
        check("admin still sees live results", state_alice["results"]["visible"] is True)
        alice.put("/api/admin/settings", json={"patch": {"hide_live_counts": False}})

        # ---- anonymity hides names from everyone
        alice.put("/api/admin/settings", json={"patch": {"anonymous_voting": True}})
        state_alice = alice.get("/api/state").json()
        check("anonymous hides names", state_alice["results"]["food"]["1"].get("voters") is None)
        votes = alice.get("/api/admin/votes").json()
        check(
            "admin votes view anonymous",
            all(p["display_name"] == "(anonymous)" for p in votes["people"]),
        )
        alice.put("/api/admin/settings", json={"patch": {"anonymous_voting": False}})

        # ---- admin detail view
        votes = alice.get("/api/admin/votes").json()
        bob_row = next(p for p in votes["people"] if p.get("user_id") == "bob")
        check("admin sees bob's availability", bob_row["availability"] == {"1": "strong", "2": "weak"})

        # ---- closed voting blocks edits
        alice.put("/api/admin/settings", json={"patch": {"voting_closed": True}})
        r = bob.put(
            "/api/vote",
            json={
                "availability": [{"slot_id": 3, "level": "strong"}],
                "food_venue_ids": [],
                "activity_venue_ids": [],
            },
        )
        check("closed voting blocks edits", r.status_code == 403)
        r = bob.post("/api/venues", json={"name": "Too Late Cafe", "type": "food"})
        check("closed voting blocks suggestions", r.status_code == 403)
        state_bob = bob.get("/api/state").json()
        check("results visible after close", state_bob["results"]["visible"] is True)
        alice.put("/api/admin/settings", json={"patch": {"voting_closed": False}})

        # ---- venue removal strips it from saved votes
        r = alice.delete("/api/admin/venues/2")
        check("admin removes venue", r.status_code == 200)
        votes = alice.get("/api/admin/votes").json()
        bob_row = next(p for p in votes["people"] if p.get("user_id") == "bob")
        check("removed venue stripped from votes", bob_row["activity_venue_ids"] == [])

        # ---- AI attribution footer + voter-visibility setting
        state_pub = client.get("/api/state").json()
        check(
            "unauthenticated state includes footer",
            state_pub["footer"]["repo_url"].startswith("https://github.com/"),
        )
        check(
            "show_footer_to_voters defaults on",
            state_pub["settings"]["show_footer_to_voters"] is True,
        )
        r = alice.put(
            "/api/admin/settings", json={"patch": {"show_footer_to_voters": False}}
        )
        check("footer visibility toggle saved", r.json()["show_footer_to_voters"] is False)
        alice.put("/api/admin/settings", json={"patch": {"show_footer_to_voters": True}})
        entries = state_pub["footer"]["entries"]
        check(
            "footer logs agent with tokens/cost",
            bool(entries)
            and all(
                {"agent", "model", "tokens_in", "tokens_out", "cost_usd"} <= set(e)
                for e in entries
            ),
        )

        # ---- admin management: promote / demote other users
        r = alice.put("/api/admin/users/bob/admin", json={"is_admin": True})
        check("alice promotes bob", r.status_code == 200 and r.json()["is_admin"] is True)
        users = alice.get("/api/admin/users").json()
        check(
            "user list shows both admins",
            {u["user_id"] for u in users if u["is_admin"]} == {"alice", "bob"},
        )
        state_bob = bob.get("/api/state").json()
        check("bob's session sees admin immediately", state_bob["me"]["is_admin"] is True)

        r = alice.put("/api/admin/users/alice/admin", json={"is_admin": False})
        check("self-demote rejected", r.status_code == 422)

        r = bob.put("/api/admin/users/alice/admin", json={"is_admin": False})
        check("bob demotes alice", r.status_code == 200)
        r = alice.put("/api/admin/settings", json={"patch": {}})
        check("demoted alice blocked from admin API", r.status_code == 403)

        r = bob.put("/api/admin/users/carol/admin", json={"is_admin": True})
        check("grant admin to unknown user creates them", r.status_code == 200)
        users = bob.get("/api/admin/users").json()
        carol = next(u for u in users if u["user_id"] == "carol")
        check("carol is admin before ever logging in", carol["is_admin"] is True)
        r = bob.put("/api/admin/users/nobody/admin", json={"is_admin": False})
        check("demote unknown user rejected", r.status_code == 404)

        # Restore a stable admin set for the MCP section: alice + bob are
        # admins, carol is a plain voter again.
        r = bob.put("/api/admin/users/carol/admin", json={"is_admin": False})
        check("bob demotes carol", r.status_code == 200 and r.json()["is_admin"] is False)

        # ---- MCP tools
        asyncio.run(mcp_checks())

        # ---- regressions for the audit findings in github issue #1
        audit_checks(bob)
        okta_checks()
        mcp_sso_identity_checks()

    print(f"\n{PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)


def audit_checks(admin: TestClient) -> None:
    """Regression checks for github issue #1 (correctness / data-integrity).

    Runs after the MCP section, so it sets up its own schedule, venues and
    voters instead of relying on earlier state. `admin` is an admin client.
    """
    admin.put(
        "/api/admin/settings",
        json={
            "patch": {
                "voting_closed": False,
                "voting_closes_at": None,
                "headcount_limit": None,
                "anonymous_voting": False,
                "preference_mode": "strong_weak",
            }
        },
    )

    # --- #9 duplicate schedule entries collapse into one slot
    schedule = [
        {"date": "2026-10-05", "start_time": "11:00", "end_time": "14:00"},
        {"date": "2026-10-06", "start_time": "11:00", "end_time": "14:00"},
        {"date": "2026-10-06", "start_time": "11:00", "end_time": "14:00"},  # duplicate
    ]
    r = admin.put("/api/admin/slots", json={"slots": schedule})
    check("duplicate schedule entries collapsed", r.status_code == 200 and r.json()["slot_count"] == 2)
    slots = admin.get("/api/state").json()["slots"]
    slot_a, slot_b = slots[0]["id"], slots[1]["id"]

    r = admin.post(
        "/api/admin/venues", json={"name": "Audit Diner", "type": "food", "slot_ids": [slot_a]}
    )
    food_id = r.json()["venue_id"]
    r = admin.post("/api/admin/venues", json={"name": "Audit Arcade", "type": "activity"})
    activity_id = r.json()["venue_id"]

    dave = TestClient(app)
    dave.post("/api/login", json={"userid": "dave"})

    # --- #7 duplicate ids are stored once and counted once
    r = dave.put(
        "/api/vote",
        json={
            "availability": [
                {"slot_id": slot_a, "level": "strong"},
                {"slot_id": slot_a, "level": "weak"},
            ],
            "food_venue_ids": [food_id, food_id],
            "activity_venue_ids": [activity_id, activity_id, activity_id],
        },
    )
    check("duplicate ids accepted", r.status_code == 200 and r.json()["slots"] == 1)
    st = dave.get("/api/state").json()
    check(
        "duplicate venue ids de-duplicated in storage",
        st["my_vote"]["food_venue_ids"] == [food_id]
        and st["my_vote"]["activity_venue_ids"] == [activity_id],
    )
    check(
        "duplicate venue ids counted once",
        st["results"]["food"][str(food_id)]["count"] == 1,
        f"got {st['results']['food'].get(str(food_id))}",
    )

    # --- #9 re-saving the same schedule keeps ids and availability
    r = admin.put(
        "/api/admin/slots",
        json={
            "slots": [
                {"date": s["date"], "start_time": s["start_time"], "end_time": s["end_time"]}
                for s in slots
            ]
        },
    )
    check("re-saving an unchanged schedule keeps the count", r.json()["slot_count"] == 2)
    st = dave.get("/api/state").json()
    check("slot ids preserved across a schedule save", [s["id"] for s in st["slots"]] == [slot_a, slot_b])
    check(
        "availability survives an unchanged schedule save",
        st["my_availability"] == {str(slot_a): "strong"},
        f"got {st['my_availability']}",
    )

    # --- #9/#10 a venue that loses its whole compatibility list is disabled
    r = admin.put(
        "/api/admin/slots",
        json={"slots": [{"date": "2026-10-06", "start_time": "11:00", "end_time": "14:00"}]},
    )
    check("schedule shrinks to 1 slot", r.status_code == 200 and r.json()["slot_count"] == 1)
    st = dave.get("/api/state").json()
    check(
        "venue left without a compatible slot deactivated",
        all(v["id"] != food_id for v in st["venues"]),
    )
    check("that venue stripped from saved votes", st["my_vote"]["food_venue_ids"] == [])
    check("availability for a removed slot dropped", st["my_availability"] == {})

    # --- #10 changing a venue's category strips stale selections
    r = admin.put(f"/api/admin/venues/{activity_id}", json={"type": "food"})
    check("venue re-categorized", r.status_code == 200)
    st = dave.get("/api/state").json()
    check("re-categorized venue stripped from votes", st["my_vote"]["activity_venue_ids"] == [])

    # --- #10 deactivating a venue strips it too
    r = dave.put("/api/vote", json={"food_venue_ids": [activity_id], "activity_venue_ids": []})
    check("dave votes for the re-categorized venue", r.status_code == 200)
    r = admin.put(f"/api/admin/venues/{activity_id}", json={"active": False})
    check("venue deactivated", r.status_code == 200)
    st = dave.get("/api/state").json()
    check("deactivated venue stripped from votes", st["my_vote"]["food_venue_ids"] == [])

    # --- #8 an empty ballot cannot slip past a full headcount
    taken = admin.get("/api/state").json()["results"]["headcount_taken"]
    admin.put("/api/admin/settings", json={"patch": {"headcount_limit": taken}})
    erin = TestClient(app)
    erin.post("/api/login", json={"userid": "erin"})
    r = erin.put("/api/vote", json={"availability": [], "food_venue_ids": [], "activity_venue_ids": []})
    check("empty ballot cannot bypass a full headcount", r.status_code == 403, f"got {r.status_code}")
    r = dave.put("/api/vote", json={"availability": [], "food_venue_ids": [], "activity_venue_ids": []})
    check("existing voter can still update when full", r.status_code == 200)
    admin.put("/api/admin/settings", json={"patch": {"headcount_limit": None}})

    # --- #8 simultaneous first-time saves must not overbook the last places
    seats = 2
    taken = admin.get("/api/state").json()["results"]["headcount_taken"]
    admin.put("/api/admin/settings", json={"patch": {"headcount_limit": taken + seats}})
    racers = []
    for i in range(6):
        racer = TestClient(app)
        racer.post("/api/login", json={"userid": f"racer{i}"})
        racers.append(racer)
    gate = threading.Barrier(len(racers))
    statuses: list[int] = []
    lock = threading.Lock()

    def race(racer: TestClient) -> None:
        empty = {"availability": [], "food_venue_ids": [], "activity_venue_ids": []}
        gate.wait()
        status = racer.put("/api/vote", json=empty).status_code
        with lock:
            statuses.append(status)

    threads = [threading.Thread(target=race, args=(racer,)) for racer in racers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check(
        "concurrent saves fill exactly the free places",
        statuses.count(200) == seats,
        f"got {sorted(statuses)}",
    )
    check(
        "headcount never exceeds the limit under concurrency",
        admin.get("/api/state").json()["results"]["headcount_taken"] == taken + seats,
    )
    admin.put("/api/admin/settings", json={"patch": {"headcount_limit": None}})

    # --- #6 invalid values are 422s, not 500s or corrupt rows
    for label, body in (
        ("a negative cost", {"name": "Bad", "type": "food", "estimated_cost": -5}),
        ("an out-of-range latitude", {"name": "Bad", "type": "food", "lat": 120, "lng": 0}),
        ("an unknown compatible slot", {"name": "Bad", "type": "food", "slot_ids": [9999]}),
    ):
        r = admin.post("/api/admin/venues", json=body)
        check(f"venue with {label} rejected", r.status_code == 422, f"got {r.status_code}")

    for label, patch in (
        ("a negative headcount", {"headcount_limit": -5}),
        ("a non-numeric budget", {"budget_amount": "lots"}),
        ("a non-boolean anonymity flag", {"anonymous_voting": "maybe"}),
        ("an unparseable close time", {"voting_closes_at": "next tuesday"}),
        ("an out-of-range office latitude", {"office_lat": 200}),
    ):
        r = admin.put("/api/admin/settings", json={"patch": patch})
        check(f"setting with {label} rejected", r.status_code == 422, f"got {r.status_code}")

    r = dave.put("/api/vote", json={"availability": [{"slot_id": "abc", "level": "yes"}]})
    check("malformed slot id rejected", r.status_code == 422, f"got {r.status_code}")

    # --- #12 an offset-aware deadline is comparable, not a TypeError
    r = admin.put(
        "/api/admin/settings", json={"patch": {"voting_closes_at": "2020-01-01T00:00:00+00:00"}}
    )
    check("offset-aware deadline accepted", r.status_code == 200, f"got {r.status_code}")
    st = admin.get("/api/state").json()
    check(
        "offset-aware deadline closes voting",
        st["status"]["closed"] is True and st["status"]["reason"] == "time",
    )
    admin.put("/api/admin/settings", json={"patch": {"voting_closes_at": None}})

    # --- #11 anonymous admin results are aggregate-only
    admin.put("/api/admin/settings", json={"patch": {"anonymous_voting": True}})
    votes = admin.get("/api/admin/votes").json()
    check("anonymous admin view returns no ballot rows", votes["people"] == [])
    check("anonymous admin view keeps the aggregate", votes["results"]["visible"] is True)
    admin.put("/api/admin/settings", json={"patch": {"anonymous_voting": False}})


def okta_checks() -> None:
    """#3/#4: the callback must set the session cookie, and the id_token nonce
    must be bound to the login request. Okta itself is faked — no tenant needed.
    """
    from app import auth
    from app.config import CONFIG

    class _FakeTokenResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"id_token": "fake.id.token"}

    class _FakeHttpxClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> bool:
            return False

        def post(self, *a, **k):
            return _FakeTokenResponse()

    class _FakeSigningKey:
        key = "fake-key"

    class _FakeJWKClient:
        def __init__(self, *a, **k) -> None:
            pass

        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            return _FakeSigningKey()

    claims: dict = {}

    class _FakeJwt:
        PyJWTError = Exception
        PyJWKClient = _FakeJWKClient

        @staticmethod
        def decode(*a, **k):
            return dict(claims)

    originals = (
        auth.httpx,
        auth.jwt,
        CONFIG.okta_domain,
        CONFIG.okta_client_id,
        CONFIG.okta_client_secret,
    )
    auth.httpx = type("httpx", (), {"Client": _FakeHttpxClient})
    auth.jwt = _FakeJwt
    CONFIG.okta_domain = "https://okta.example.com/oauth2/default"
    CONFIG.okta_client_id = "client-id"
    CONFIG.okta_client_secret = "client-secret"
    try:
        url, state = auth.okta_login_url()
        check("okta authorize request binds nonce to state", f"nonce={state}" in url)

        claims.clear()
        claims.update({"nonce": "some-other-login", "email": "attacker@example.com"})
        try:
            auth.okta_exchange_code("code", state, state)
            check("okta id_token with a foreign nonce rejected", False)
        except ApiError as exc:
            check(
                "okta id_token with a foreign nonce rejected",
                exc.status == 400 and "nonce" in exc.message,
                exc.message,
            )

        claims.clear()
        claims.update({"nonce": state, "email": "okta.user@example.com", "name": "Okta User"})
        verified = auth.okta_exchange_code("code", state, state)
        check("okta id_token with the matching nonce accepted", verified["email"] == "okta.user@example.com")

        # The redirect that reaches the browser must carry the session cookie.
        browser = TestClient(app)
        browser.cookies.set(auth.STATE_COOKIE, state)
        r = browser.get(
            f"/api/auth/okta/callback?code=code&state={state}", follow_redirects=False
        )
        cookies = r.headers.get_list("set-cookie")
        check("okta callback redirects to the app", r.status_code == 302)
        check(
            "okta callback sets the session cookie on the redirect",
            any(c.startswith(f"{auth.SESSION_COOKIE}=") and "Max-Age=0" not in c for c in cookies),
            f"got {cookies}",
        )
        check(
            "okta callback clears the single-use state cookie",
            any(c.startswith(f"{auth.STATE_COOKIE}=") and "Max-Age=0" in c for c in cookies),
            f"got {cookies}",
        )
        check(
            "okta session works for the app",
            browser.get("/api/state").json()["me"]["user_id"] == "okta.user@example.com",
        )
    finally:
        (
            auth.httpx,
            auth.jwt,
            CONFIG.okta_domain,
            CONFIG.okta_client_id,
            CONFIG.okta_client_secret,
        ) = originals


def mcp_sso_identity_checks() -> None:
    """#5: with SSO on, an MCP caller must prove the userid with a session."""
    from app import service as svc
    from app.config import CONFIG
    from app.db import db

    CONFIG.testing_mode = False
    try:
        try:
            svc.mcp_identity("dave", None)
            check("mcp userid without a session rejected in SSO mode", False)
        except ApiError as exc:
            check("mcp userid without a session rejected in SSO mode", exc.status == 401, exc.message)

        try:
            svc.mcp_identity("dave", "not-a-real-token")
            check("mcp unknown session rejected", False)
        except ApiError as exc:
            check("mcp unknown session rejected", exc.status == 401, exc.message)

        with db() as conn:
            token = svc.create_session(conn, "dave")
        try:
            svc.mcp_identity("erin", token)
            check("mcp session/userid mismatch rejected", False)
        except ApiError as exc:
            check("mcp session/userid mismatch rejected", exc.status == 403, exc.message)

        check("mcp matching session accepted", svc.mcp_identity("dave", token) == "dave")

        # An unknown userid must not be auto-created in SSO mode.
        try:
            svc.mcp_identity("ghost", token)
            check("mcp cannot invent a user in SSO mode", False)
        except ApiError as exc:
            check("mcp cannot invent a user in SSO mode", exc.status == 403, exc.message)
    finally:
        CONFIG.testing_mode = True


async def mcp_checks() -> None:
    from fastmcp import Client

    async with Client(mcp) as c:
        tools = await c.list_tools()
        check("mcp: 12 tools registered", len(tools) == 12, f"got {sorted(t.name for t in tools)}")

        res = await c.call_tool("get_state", {"user_id": "bob"})
        st = res.data
        check("mcp: get_state returns venues", st is not None and len(st["venues"]) >= 2)

        res = await c.call_tool(
            "save_vote",
            {
                "user_id": "bob",
                "availability": [{"slot_id": 3, "level": "strong"}],
                "food_venue_ids": [1],
                "activity_venue_ids": [3],
            },
        )
        check("mcp: save_vote ok", res.data["saved"] is True)

        res = await c.call_tool(
            "suggest_venue",
            {"user_id": "bob", "name": "MCP Ramen", "type": "food", "estimated_cost": 12},
        )
        check("mcp: suggest_venue ok", res.data["venue_id"] >= 4)

        with_error = None
        try:
            await c.call_tool("admin_set_settings", {"user_id": "carol", "patch": {}})
        except ToolError as exc:
            with_error = str(exc)
        check("mcp: admin guard for non-admin", with_error is not None and "Admin access required" in with_error)

        # alice was demoted in the REST section above; re-grant via MCP first.
        res = await c.call_tool("admin_set_admin", {"user_id": "bob", "target_user_id": "alice", "is_admin": True})
        check("mcp: admin_set_admin grants", res.data["is_admin"] is True)

        res = await c.call_tool(
            "admin_set_slots",
            {
                "user_id": "alice",
                "slots": [{"date": "2026-09-28", "start_time": "11:00", "end_time": "13:00"}],
            },
        )
        check("mcp: admin_set_slots ok", res.data["slot_count"] == 1)

        res = await c.call_tool(
            "admin_add_venue", {"user_id": "alice", "name": "Admin Pizza", "type": "food"}
        )
        check("mcp: admin_add_venue ok", res.data is not None and "venue_id" in str(res.data))

        res = await c.call_tool("admin_close_voting", {"user_id": "alice", "closed": True})
        check("mcp: admin_close_voting ok", res.data["ok"] is True)

        with_error = None
        try:
            await c.call_tool(
                "save_vote",
                {"user_id": "bob", "availability": [], "food_venue_ids": [], "activity_venue_ids": []},
            )
        except ToolError as exc:
            with_error = str(exc)
        check("mcp: save blocked after close", with_error is not None and "closed" in with_error.lower())

        res = await c.call_tool("admin_get_votes", {"user_id": "alice"})
        check("mcp: admin_get_votes ok", res.data is not None and "people" in str(res.data))

        res = await c.call_tool("admin_list_users", {"user_id": "bob"})
        check(
            "mcp: admin_list_users ok",
            res.data is not None and len(res.data) >= 3,
        )

        with_error = None
        try:
            await c.call_tool("admin_set_admin", {"user_id": "bob", "target_user_id": "bob", "is_admin": False})
        except ToolError as exc:
            with_error = str(exc)
        check(
            "mcp: self-demote guard",
            with_error is not None and "own admin" in with_error,
        )


if __name__ == "__main__":
    main()
