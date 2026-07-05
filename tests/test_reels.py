"""Tests for ytk.reels — Instagram DM self-thread link discovery."""

from types import SimpleNamespace

import pytest

from ytk.reels import (
    ReelsState,
    extract_links,
    fetch_new_links,
    find_self_thread,
    load_state,
    save_state,
)


def _clip(msg_id: str, code: str):
    return SimpleNamespace(id=msg_id, item_type="clip", clip=SimpleNamespace(code=code))


def _media_share(msg_id: str, code: str):
    return SimpleNamespace(
        id=msg_id, item_type="media_share", media_share=SimpleNamespace(code=code)
    )


def _text(msg_id: str, text: str):
    return SimpleNamespace(id=msg_id, item_type="text", text=text)


# --- extract_links -----------------------------------------------------------


def test_extract_clip_becomes_reel_url():
    assert extract_links([_clip("1", "AbC-12_x")]) == [
        "https://www.instagram.com/reel/AbC-12_x/"
    ]


def test_extract_media_share_becomes_post_url():
    assert extract_links([_media_share("1", "XyZ99")]) == [
        "https://www.instagram.com/p/XyZ99/"
    ]


def test_extract_bare_links_from_text():
    msg = _text(
        "1",
        "look at these https://www.instagram.com/reel/aaa/ and "
        "https://www.instagram.com/p/bbb/?igsh=tracking",
    )
    assert extract_links([msg]) == [
        "https://www.instagram.com/reel/aaa/",
        "https://www.instagram.com/p/bbb/",
    ]


def test_extract_ignores_plain_text_and_unknown_types():
    msgs = [
        _text("1", "note to self: buy milk"),
        SimpleNamespace(id="2", item_type="voice_media"),
    ]
    assert extract_links(msgs) == []


def test_extract_ignores_clip_with_missing_payload():
    msg = SimpleNamespace(id="1", item_type="clip", clip=None)
    assert extract_links([msg]) == []


def test_extract_dedupes_preserving_order():
    msgs = [
        _clip("1", "aaa"),
        _clip("2", "bbb"),
        _text("3", "https://www.instagram.com/reel/aaa/"),
    ]
    assert extract_links(msgs) == [
        "https://www.instagram.com/reel/aaa/",
        "https://www.instagram.com/reel/bbb/",
    ]


# --- find_self_thread --------------------------------------------------------


class FakeClient:
    def __init__(self, threads, messages_by_thread=None, user_id="42"):
        self.user_id = user_id
        self._threads = threads
        self._messages = messages_by_thread or {}

    def direct_threads(self, amount=0):
        return self._threads

    def direct_messages(self, thread_id, amount=0):
        return self._messages[thread_id]


def _thread(thread_id: str, user_pks: list[str]):
    return SimpleNamespace(
        id=thread_id, users=[SimpleNamespace(pk=pk) for pk in user_pks]
    )


def test_find_self_thread_empty_users():
    client = FakeClient([_thread("t1", ["7"]), _thread("t2", [])])
    assert find_self_thread(client).id == "t2"


def test_find_self_thread_only_me():
    client = FakeClient([_thread("t1", ["7", "8"]), _thread("t2", ["42"])])
    assert find_self_thread(client).id == "t2"


def test_find_self_thread_missing_raises():
    client = FakeClient([_thread("t1", ["7"])])
    with pytest.raises(ValueError, match="self"):
        find_self_thread(client)


# --- fetch_new_links (cursor) ------------------------------------------------


def _client_with_thread(messages):
    """Client whose self-thread 'ts' holds messages, newest first (API order)."""
    return FakeClient([_thread("ts", [])], {"ts": messages})


def test_first_run_drains_backlog_oldest_first():
    # API returns newest first: msg 3, 2, 1
    msgs = [_clip("3", "ccc"), _clip("2", "bbb"), _clip("1", "aaa")]
    links, state = fetch_new_links(_client_with_thread(msgs), ReelsState())
    assert links == [
        "https://www.instagram.com/reel/aaa/",
        "https://www.instagram.com/reel/bbb/",
        "https://www.instagram.com/reel/ccc/",
    ]
    assert state.last_seen_message_id == "3"
    assert state.thread_id == "ts"


def test_cursor_skips_already_seen_messages():
    msgs = [_clip("3", "ccc"), _clip("2", "bbb"), _clip("1", "aaa")]
    links, state = fetch_new_links(
        _client_with_thread(msgs), ReelsState(thread_id="ts", last_seen_message_id="2")
    )
    assert links == ["https://www.instagram.com/reel/ccc/"]
    assert state.last_seen_message_id == "3"


def test_cursor_at_newest_yields_nothing():
    msgs = [_clip("3", "ccc"), _clip("2", "bbb")]
    links, state = fetch_new_links(
        _client_with_thread(msgs), ReelsState(thread_id="ts", last_seen_message_id="3")
    )
    assert links == []
    assert state.last_seen_message_id == "3"


# --- state persistence -------------------------------------------------------


def test_state_round_trip(tmp_path):
    path = tmp_path / "reels_state.json"
    save_state(ReelsState(thread_id="ts", last_seen_message_id="99"), path)
    state = load_state(path)
    assert state.thread_id == "ts"
    assert state.last_seen_message_id == "99"


def test_load_state_missing_file_returns_empty(tmp_path):
    state = load_state(tmp_path / "nope.json")
    assert state.thread_id is None
    assert state.last_seen_message_id is None


# --- get_client (session persistence contract) --------------------------------


class FakeInstagrapiClient:
    def __init__(self):
        self.calls = []

    def load_settings(self, path):
        self.calls.append(("load_settings", str(path)))

    def login_by_sessionid(self, sessionid):
        self.calls.append(("login_by_sessionid", sessionid))

    def dump_settings(self, path):
        self.calls.append(("dump_settings", str(path)))


def _patch_instagrapi(monkeypatch, fake):
    import sys
    import types

    mod = types.ModuleType("instagrapi")
    mod.Client = lambda: fake
    monkeypatch.setitem(sys.modules, "instagrapi", mod)


def test_get_client_fresh_login_dumps_settings(monkeypatch, tmp_path):
    from ytk.reels import get_client

    fake = FakeInstagrapiClient()
    _patch_instagrapi(monkeypatch, fake)
    settings = tmp_path / "instagram_session.json"

    client = get_client("sess-123", settings_path=settings)

    assert client is fake
    assert fake.calls == [
        ("login_by_sessionid", "sess-123"),
        ("dump_settings", str(settings)),
    ]


def test_get_client_reuses_persisted_device(monkeypatch, tmp_path):
    from ytk.reels import get_client

    fake = FakeInstagrapiClient()
    _patch_instagrapi(monkeypatch, fake)
    settings = tmp_path / "instagram_session.json"
    settings.write_text("{}", encoding="utf-8")

    get_client("sess-123", settings_path=settings)

    assert fake.calls == [
        ("load_settings", str(settings)),
        ("login_by_sessionid", "sess-123"),
        ("dump_settings", str(settings)),
    ]


def test_get_client_requires_sessionid(tmp_path):
    from ytk.reels import get_client

    with pytest.raises(ValueError, match="INSTAGRAM_SESSIONID"):
        get_client("", settings_path=tmp_path / "s.json")


# --- find_peer_thread (two-account capture thread) -----------------------------


def _thread_named(thread_id: str, users: list[tuple[str, str]]):
    return SimpleNamespace(
        id=thread_id,
        users=[SimpleNamespace(pk=pk, username=name) for pk, name in users],
    )


def test_find_peer_thread_matches_username():
    from ytk.reels import find_peer_thread

    client = FakeClient(
        [
            _thread_named("t1", [("7", "somefriend")]),
            _thread_named("t2", [("8", "integratederivate")]),
        ]
    )
    assert find_peer_thread(client, "integratederivate").id == "t2"


def test_find_peer_thread_is_case_insensitive():
    from ytk.reels import find_peer_thread

    client = FakeClient([_thread_named("t2", [("8", "IntegrateDerivate")])])
    assert find_peer_thread(client, "integratederivate").id == "t2"


def test_find_peer_thread_ignores_group_threads():
    from ytk.reels import find_peer_thread

    client = FakeClient(
        [
            _thread_named("g1", [("8", "integratederivate"), ("9", "other")]),
            _thread_named("t2", [("8", "integratederivate")]),
        ]
    )
    assert find_peer_thread(client, "integratederivate").id == "t2"


def test_find_peer_thread_missing_raises():
    from ytk.reels import find_peer_thread

    client = FakeClient([_thread_named("t1", [("7", "somefriend")])])
    with pytest.raises(ValueError, match="integratederivate"):
        find_peer_thread(client, "integratederivate")


def test_fetch_new_links_uses_peer_thread_when_given():
    msgs = [_clip("2", "bbb"), _clip("1", "aaa")]
    client = FakeClient(
        [_thread_named("tp", [("8", "integratederivate")]), _thread("ts", [])],
        {"tp": msgs, "ts": []},
    )
    links, state = fetch_new_links(client, ReelsState(), peer="integratederivate")
    assert links == [
        "https://www.instagram.com/reel/aaa/",
        "https://www.instagram.com/reel/bbb/",
    ]
    assert state.thread_id == "tp"


# --- xma message shapes (current Instagram share format) -----------------------


def _xma(msg_id: str, item_type: str, **fields):
    return SimpleNamespace(
        id=msg_id, item_type=item_type, xma_share=SimpleNamespace(**fields)
    )


def test_extract_xma_clip_video_url():
    msg = _xma(
        "1",
        "xma_clip",
        video_url="https://www.instagram.com/reel/DZr18tXD01B/?id=39214_735&is_sponsored=false",
        target_url=None,
    )
    assert extract_links([msg]) == ["https://www.instagram.com/reel/DZr18tXD01B/"]


def test_extract_xma_media_share_target_url():
    msg = _xma(
        "1",
        "xma_media_share",
        video_url=None,
        target_url="https://www.instagram.com/p/Cpost123/?igsh=xyz",
    )
    assert extract_links([msg]) == ["https://www.instagram.com/p/Cpost123/"]


def test_extract_xma_without_payload_ignored():
    msg = SimpleNamespace(id="1", item_type="xma_clip", xma_share=None)
    assert extract_links([msg]) == []


def test_get_client_is_cached_per_session(monkeypatch, tmp_path):
    from ytk.reels import get_client

    fake = FakeInstagrapiClient()
    _patch_instagrapi(monkeypatch, fake)
    settings = tmp_path / "instagram_session.json"

    first = get_client("sess-123", settings_path=settings)
    second = get_client("sess-123", settings_path=settings)

    assert first is second
    # exactly one login, not one per call
    assert [c for c in fake.calls if c[0] == "login_by_sessionid"] == [
        ("login_by_sessionid", "sess-123")
    ]
