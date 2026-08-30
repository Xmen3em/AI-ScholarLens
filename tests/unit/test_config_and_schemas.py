import os
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings
from src.config import Settings

PROJECT_ROOT = Path(__file__).parents[2]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_TEST = PROJECT_ROOT / ".env.test"

#: Not deployment configuration: the arXiv Atom XML namespaces are part of the feed
#: format, so they belong in code rather than in an operator's .env.
NOT_ENV_CONFIGURABLE = {"ARXIV__NAMESPACES"}


def test_settings_parse_comma_separated_ollama_models():
    configured = Settings(_env_file=None, ollama_models="llama3.2:1b, qwen2.5:1.5b")

    assert configured.ollama_models == ["llama3.2:1b", "qwen2.5:1.5b"]


def test_paper_create_defaults_to_unprocessed(paper_create_data):
    assert paper_create_data.pdf_processed is False


def test_the_suite_reads_env_test_rather_than_a_developer_env_file():
    """pytest-dotenv loads .env.test into the environment (see pyproject.toml).

    Environment variables outrank the .env file in pydantic-settings, so whatever a
    developer keeps locally cannot change what the tests exercise. ENVIRONMENT is the
    discriminator: both the code default and a typical .env say "development".
    """
    assert os.environ.get("ENVIRONMENT") == "test", ".env.test was not loaded"
    assert Settings().environment == "test"


def settings_env_names(model: type[BaseSettings], prefix: str = "") -> set[str]:
    """Every environment variable name the settings tree can be configured with.

    Walks nested settings models rather than listing names, so a new setting — or a
    whole new nested group — is covered here the moment it is declared.
    """
    names: set[str] = set()
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseSettings):
            names |= settings_env_names(annotation, f"{prefix}{name.upper()}__")
        else:
            names.add(f"{prefix}{name.upper()}")
    return names - NOT_ENV_CONFIGURABLE


def declared_names(env_file: Path) -> set[str]:
    """The variable names an env file assigns, ignoring comments and blank lines."""
    names = set()
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.add(line.split("=", 1)[0].strip())
    return names


@pytest.mark.parametrize("env_file", [ENV_EXAMPLE, ENV_TEST], ids=["env.example", "env.test"])
def test_env_file_documents_every_setting(env_file):
    """.env.example is the template developers copy; .env.test is what shields the suite.

    A setting missing from .env.test falls through to whatever the developer has in
    their own .env, which is the isolation hole this file exists to close.
    """
    missing = settings_env_names(Settings) - declared_names(env_file)

    assert not missing, f"{env_file.name} is missing: {sorted(missing)}"


@pytest.mark.parametrize("env_file", [ENV_EXAMPLE, ENV_TEST], ids=["env.example", "env.test"])
def test_env_file_declares_nothing_the_settings_do_not_read(env_file):
    """Catches names left behind after a setting is renamed or retired."""
    unknown = declared_names(env_file) - settings_env_names(Settings) - NOT_ENV_CONFIGURABLE

    assert not unknown, f"{env_file.name} sets variables nothing reads: {sorted(unknown)}"


def test_env_example_values_produce_working_settings(monkeypatch):
    """`cp .env.example .env` has to yield a config that actually loads."""
    for name in settings_env_names(Settings):
        monkeypatch.delenv(name, raising=False)  # otherwise .env.test would mask the file

    configured = Settings(_env_file=ENV_EXAMPLE)

    assert configured.environment == "development"
    assert configured.arxiv.max_results == 10
    assert configured.ollama_models == ["llama3.2:1b"]
