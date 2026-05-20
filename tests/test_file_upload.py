from fulcra_api.core import FulcraAPI


def test_file_content_type_preserves_explicit_type():
    client = FulcraAPI()

    assert client._file_content_type("text/plain", "README.md") == "text/plain"


def test_file_content_type_defaults_markdown_when_guess_missing():
    client = FulcraAPI()

    assert client._file_content_type(None, "README.md") == "text/markdown"
    assert client._file_content_type(None, "README.markdown") == "text/markdown"


def test_file_content_type_falls_back_to_octet_stream():
    client = FulcraAPI()

    assert (
        client._file_content_type(None, "data.unknownextension")
        == "application/octet-stream"
    )
