"""sdk.py returns usage to callers (#197 P4): activity rows need model,
tokens, duration_ms, so the ResultMessage fields stop being discarded."""

from claude_agent_sdk import ResultMessage

from ytk import sdk


def _msg(**overrides) -> ResultMessage:
    base = {
        "subtype": "success",
        "duration_ms": 4200,
        "duration_api_ms": 4000,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s",
        "structured_output": {"thesis": "t"},
        "usage": {"input_tokens": 900, "output_tokens": 100, "cache_read_input_tokens": 5000},
        "model_usage": {"claude-sonnet-5": {"input_tokens": 900}},
    }
    base.update(overrides)
    return ResultMessage(**base)


def test_result_carries_data_and_usage():
    res = sdk.result_from(_msg(), requested_model="claude-sonnet-5")
    assert res.data == {"thesis": "t"}
    assert res.model == "claude-sonnet-5"
    assert res.tokens == 1000  # input + output; cache reads ride in usage
    assert res.duration_ms == 4200
    assert res.usage["cache_read_input_tokens"] == 5000


def test_model_falls_back_to_model_usage_key():
    res = sdk.result_from(_msg(), requested_model=None)
    assert res.model == "claude-sonnet-5"


def test_usage_absent_under_subscription_auth_is_tolerated():
    # Recorded spec uncertainty: usage may not arrive on subscription auth.
    res = sdk.result_from(_msg(usage=None, model_usage=None), requested_model=None)
    assert res.tokens is None
    assert res.model is None
    assert res.usage is None
    assert res.duration_ms == 4200
