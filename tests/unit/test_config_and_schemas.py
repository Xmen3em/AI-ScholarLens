from src.config import Settings


def test_settings_parse_comma_separated_ollama_models():
    configured = Settings(_env_file=None, ollama_models="llama3.2:1b, qwen2.5:1.5b")

    assert configured.ollama_models == ["llama3.2:1b", "qwen2.5:1.5b"]


def test_paper_create_defaults_to_unprocessed(paper_create_data):
    assert paper_create_data.pdf_processed is False
