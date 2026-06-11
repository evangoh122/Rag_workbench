import os
from unittest.mock import patch
import pytest
from api.config import Config

class TestConfig:
    @pytest.fixture(autouse=True)
    def clear_env(self):
        """Clear relevant env vars before each test."""
        keys = [
            "DB_PATH", "REVIEW_DB_PATH", "CHAT_PROVIDER", "CHAT_MODEL",
            "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY", "MIMO_API_KEY", "API_KEY", "READ_API_KEY",
            "WRITE_API_KEY", "ADMIN_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING"
        ]
        old_values = {k: os.environ.get(k) for k in keys}
        for k in keys:
            if k in os.environ:
                del os.environ[k]
        yield
        for k, v in old_values.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    def test_singleton_behavior(self):
        from api.config import config as c1
        from api.config import config as c2
        assert c1 is c2

    def test_default_values(self):
        # Config is already initialized as a singleton at module level.
        # We need to test its properties which read from os.environ.
        assert Config.CHAT_PROVIDER == "deepseek"
        assert Config.LANGSMITH_PROJECT == "rag-workbench"
        assert Config.DRIFT_AGREEMENT_FLOOR == 0.95

    def test_env_override(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "openai", "DRIFT_AGREEMENT_FLOOR": "0.80"}):
            # Since Config is a singleton and properties are evaluated on access
            assert Config.CHAT_PROVIDER == "openai"
            assert Config.DRIFT_AGREEMENT_FLOOR == 0.80

    def test_db_path_validation(self):
        # Test fallback for empty path
        with patch.dict(os.environ, {"DB_PATH": ""}):
            # Reset cached _db_path
            from api.config import config
            config._db_path = None 
            path = Config.DB_PATH
            assert "rag.duckdb" in path
            assert "data" in path

    def test_get_provider_config_deepseek(self):
        with patch.dict(os.environ, {"CHAT_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "sk-123"}):
            cfg = Config.get_provider_config()
            assert cfg["api_key"] == "sk-123"
            assert "deepseek" in cfg["base_url"]

    def test_get_provider_config_openai_override(self):
        with patch.dict(os.environ, {
            "CHAT_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-oa",
            "CHAT_MODEL": "gpt-o-mini"
        }):
            cfg = Config.get_provider_config()
            assert cfg["api_key"] == "sk-oa"
            assert cfg["model"] == "gpt-o-mini"

    def test_validate_startup_warnings(self, caplog):
        from loguru import logger
        handler_id = logger.add(caplog.handler, format="{message}", level="WARNING")
        try:
            with patch.dict(os.environ, {"CHAT_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""}):
                Config.validate_startup()
                assert "ANTHROPIC_API_KEY not set" in caplog.text
        finally:
            logger.remove(handler_id)
