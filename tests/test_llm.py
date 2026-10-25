import pytest

from ip_finder.llm import LLMError, OllamaClient
from ip_finder.llm.ollama_client import assert_local, label_schema


@pytest.mark.parametrize("host", ["http://example.com:11434", "http://192.168.0.5:11434", "https://api.openai.com"])
def test_external_hosts_rejected(host):
    with pytest.raises(LLMError):
        assert_local(host)
    with pytest.raises(LLMError):
        OllamaClient(host, "m")


@pytest.mark.parametrize("host", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_local_hosts_accepted(host):
    assert_local(host)


def test_label_schema_fixes_length():
    s = label_schema(7)
    assert s["properties"]["labels"]["minItems"] == 7 == s["properties"]["labels"]["maxItems"]
    assert "X" in s["properties"]["labels"]["items"]["enum"]
