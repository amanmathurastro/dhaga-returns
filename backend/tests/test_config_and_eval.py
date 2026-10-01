import pytest

from app import config
from app.evalmetrics import EvalRow, Guess, accuracy, at_threshold, confidence_separation, per_reason_accuracy, routed_guess

ALL = {
    "OPENROUTER_API_KEY": "sk-test", "MODEL_A_ID": "a/model", "MODEL_B_ID": "b/model",
    "SUPABASE_DB_URL": "postgresql://localhost/x", "CONFIDENCE_THRESHOLD": "0.7",
    "MIN_RETURNS_TO_FLAG": "5", "LIFT_THRESHOLD": "2",
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    def apply(**values):
        monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
        monkeypatch.setitem(config.Settings.model_config, "env_file", None)
        for key in list(config.Settings.model_fields):
            monkeypatch.delenv(key, raising=False)
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        config._load.cache_clear()

    yield apply
    config._load.cache_clear()


def test_complete_config_loads(env):
    env(**ALL)
    settings = config.get_settings()
    assert settings.CONFIDENCE_THRESHOLD == 0.7 and settings.MIN_RETURNS_TO_FLAG == 5
    assert settings.JUNK_MIN_CHARS == 3
    assert settings.frontend_origins == ["http://localhost:3000"]


def test_missing_and_blank_values_are_named(env):
    env(**{**ALL, "MODEL_B_ID": "", "LIFT_THRESHOLD": "   "})
    with pytest.raises(config.ConfigError) as exc:
        config.get_settings()
    assert "MODEL_B_ID" in str(exc.value) and "LIFT_THRESHOLD" in str(exc.value)
    assert "MODEL_A_ID" not in str(exc.value)


def test_invalid_value_is_named(env):
    env(**{**ALL, "CONFIDENCE_THRESHOLD": "1.5"})
    with pytest.raises(config.ConfigError, match="CONFIDENCE_THRESHOLD"):
        config.get_settings()


def test_eval_can_run_before_the_threshold_is_decided(env):
    env(**{k: v for k, v in ALL.items() if k != "CONFIDENCE_THRESHOLD"})
    assert config.get_settings(config.EVAL_REQUIRED).CONFIDENCE_THRESHOLD is None
    with pytest.raises(config.ConfigError, match="CONFIDENCE_THRESHOLD"):
        config.get_settings()


ROWS = [
    EvalRow("R1", "fit", Guess("fit", 0.95), Guess("fit", 0.9)),  # A right and sure
    EvalRow("R2", "fit", Guess("other", 0.5), Guess("fit", 0.9)),  # A wrong and unsure, B rescues
    EvalRow("R3", "defect_quality", Guess("fit", 0.9), Guess("defect_quality", 0.9)),  # A wrong but sure
    EvalRow("R4", "changed_mind", Guess(None), Guess("changed_mind", 0.6)),  # A failed, B unsure
]


def test_routing_is_replayed_per_threshold():
    assert routed_guess(ROWS[1], 0.7) == ("fit", "B")
    assert routed_guess(ROWS[1], 0.4) == ("other", "A")
    assert routed_guess(ROWS[3], 0.7) == (None, "none")
    assert routed_guess(ROWS[3], 0.6) == ("changed_mind", "B")


def test_threshold_result():
    res = at_threshold(ROWS, 0.7)
    assert res.routed_share == 0.5  # R2 and R4 went to B
    assert res.unclassified_share == 0.25  # R4
    assert res.accuracy_overall == 0.5  # R1, R2 right; R3 wrong; R4 unanswered
    assert res.accuracy_on_answered == pytest.approx(2 / 3)


def test_accuracy_helpers():
    pairs = [(r.label, r.a.reason) for r in ROWS]
    assert accuracy(pairs) == 0.25
    assert per_reason_accuracy(pairs) == {"changed_mind": (0, 1), "defect_quality": (0, 1), "fit": (1, 2)}
    assert accuracy([]) is None


def test_confidence_separation():
    sep = confidence_separation(ROWS, "a")
    assert (sep.n_right, sep.n_wrong) == (1, 2)
    assert sep.mean_when_right == 0.95 and sep.mean_when_wrong == pytest.approx(0.7)


@pytest.mark.parametrize(
    "driver_message, expected",
    [
        ('connection failed: FATAL:  password authentication failed for user "postgres"', "rejected the password"),
        ("connection failed: FATAL:  Tenant or user not found", "postgres.<project-ref>"),
        ("connection is bad: Network is unreachable", "Session pooler"),
        ('failed to resolve host \'151622@db.x.supabase.co\': [Errno -2] Name or service not known', "host name"),
        ("connection timeout expired", "timed out"),
        ("something nobody predicted", "Could not connect to the database (OperationalError)"),
    ],
)
def test_database_problem_is_explained_without_leaking_the_url(monkeypatch, driver_message, expected):
    import psycopg

    from app import db

    def failing_connect():
        raise psycopg.OperationalError(driver_message)

    monkeypatch.setattr(db, "connect", failing_connect)
    problem = db.ping_problem()
    assert expected in problem
    assert "db.x.supabase.co" not in problem and "151622" not in problem  # nothing from the driver message
