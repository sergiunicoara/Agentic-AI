from app import critic_agent, session_store


def test_critic_validation_persists_with_session_store(monkeypatch, tmp_path):
    monkeypatch.setattr(session_store, "DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(
        critic_agent,
        "call_mcp_tool",
        lambda *_args, **_kwargs: {
            "score": 4.5,
            "faithfulness": 1.0,
            "relevancy": 0.9,
            "factuality": 0.8,
            "label": "good",
            "issues": [],
            "reasoning": "Grounded response.",
        },
    )

    result = critic_agent.validate_turn(
        user_message="What is his experience?",
        agent_reply="He has relevant experience.",
        session_id="critic-persistence-test",
    )
    summary = critic_agent.get_critic_session_summary("critic-persistence-test")

    assert result["verdict"] == "PASS"
    assert summary["n_validations"] == 1
    assert summary["avg_score"] == 4.5
