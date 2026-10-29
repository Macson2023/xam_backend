from app.core.config import Settings


def build_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_cors_origins_are_split_from_comma_separated_string() -> None:
    settings = build_settings(cors_origins="http://a.test, http://b.test , ")

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_empty_string_produces_empty_list() -> None:
    assert build_settings(cors_origins="").cors_origins == []


def test_cors_origins_list_is_preserved() -> None:
    assert build_settings(cors_origins=["http://a.test"]).cors_origins == ["http://a.test"]


def test_default_settings(monkeypatch) -> None:
    for name in (
        "APP_NAME",
        "API_V1_PREFIX",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "AUTO_CREATE_TABLES",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = build_settings()

    assert settings.app_name == "xam_backend"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 60 * 24
    assert settings.auto_create_tables is False
    assert settings.cors_origins == ["http://localhost:5173"]


def test_numeric_settings_are_coerced() -> None:
    settings = build_settings(access_token_expire_minutes="15", database_echo="true")

    assert settings.access_token_expire_minutes == 15
    assert settings.database_echo is True
