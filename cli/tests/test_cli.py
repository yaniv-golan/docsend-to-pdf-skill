import base64
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from docsend_to_pdf.cli import serialize_session, deserialize_session, format_output, _run_conversion


class TestSessionSerialization:
    def test_round_trip_blob(self):
        state = {
            "url": "https://docsend.com/view/abc",
            "cookies": {"_docsend_session": "sess123"},
            "csrf_token": "tok",
            "gates_cleared": ["email"],
            "pending_gate": "verification",
            "email": "me@co.com",
        }
        blob = serialize_session(state)
        decoded = json.loads(base64.b64decode(blob))
        assert decoded["url"] == state["url"]
        result = deserialize_session(blob=blob)
        assert result == state

    def test_round_trip_file(self, tmp_path: Path):
        state = {
            "url": "https://docsend.com/view/xyz",
            "cookies": {},
            "csrf_token": "tok2",
            "gates_cleared": [],
            "pending_gate": "email",
            "email": "",
        }
        state_file = tmp_path / "state.json"
        blob = serialize_session(state, state_file=str(state_file))
        assert state_file.exists()
        result = deserialize_session(state_file=str(state_file))
        assert result == state

    def test_deserialize_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            deserialize_session(state_file=str(tmp_path / "nope.json"))

    def test_deserialize_no_source_raises(self):
        with pytest.raises(ValueError, match="either blob or state_file"):
            deserialize_session()


class TestFormatOutput:
    def test_complete(self):
        result = format_output(status="complete", pages=12, output="deck.pdf", title="My Deck")
        parsed = json.loads(result)
        assert parsed["status"] == "complete"
        assert parsed["pages"] == 12
        assert parsed["output"] == "deck.pdf"
        assert parsed["title"] == "My Deck"

    def test_needs_email_with_blob(self):
        result = format_output(status="needs_email", session="abc123")
        parsed = json.loads(result)
        assert parsed["status"] == "needs_email"
        assert parsed["session"] == "abc123"

    def test_needs_verification_with_state_file(self):
        result = format_output(
            status="needs_verification", email="me@co.com", state_file="/tmp/state.json",
        )
        parsed = json.loads(result)
        assert parsed["status"] == "needs_verification"
        assert parsed["state_file"] == "/tmp/state.json"
        assert "session" not in parsed

    def test_error(self):
        result = format_output(status="error", message="Link expired")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["message"] == "Link expired"


# ---------------------------------------------------------------------------
# Helpers for integration tests
# ---------------------------------------------------------------------------

def _make_test_png() -> bytes:
    """Create a small valid PNG for testing."""
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestRunConversionEmailGate:
    """Test that the CLI correctly stops at the email gate and outputs JSON."""

    def test_needs_email_json(self, fixture_html, capsys):
        html = fixture_html("email_gate.html")

        # Mock the client functions that _run_conversion calls
        with patch("docsend_to_pdf.cli.fetch_page") as mock_fetch:
            from docsend_to_pdf.types import Gate, GateKind, PageResponse
            mock_fetch.return_value = PageResponse(
                gate=Gate(kind=GateKind.EMAIL),
                csrf_token="csrf-token-123",
                title=None,
                page_count=None,
            )

            exit_code = _run_conversion(
                url="https://docsend.com/view/abc123",
                email=None, passcode=None, verification_code=None,
                accept_nda_flag=False, output_path=None, json_mode=True,
                quiet=True, session_blob=None, state_file=None,
            )

        assert exit_code == 2
        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "needs_email"
        assert "session" in output


class TestRunConversionSuccess:
    """Test the full happy path with mocked responses."""

    def test_no_gate_downloads_and_builds_pdf(self, fixture_json, capsys, tmp_path):
        page_data_json = fixture_json("page_data_1.json")
        test_png = _make_test_png()
        output_path = str(tmp_path / "output.pdf")

        with patch("docsend_to_pdf.cli.fetch_page") as mock_fetch, \
             patch("docsend_to_pdf.cli.fetch_page_data") as mock_page_data, \
             patch("docsend_to_pdf.cli.download_image") as mock_download:

            from docsend_to_pdf.types import Gate, GateKind, PageResponse, PageData

            # fetch_page returns authenticated (no gate)
            mock_fetch.return_value = PageResponse(
                gate=Gate(kind=GateKind.NONE),
                csrf_token="csrf-token-auth",
                title="Series A Deck",
                page_count=3,
            )

            # fetch_page_data returns image URLs for pages 1-3
            mock_page_data.side_effect = lambda sess, url, n: PageData(
                image_url=f"https://cloudfront.net/page{n}.png",
                page_num=n,
            ) if n <= 3 else None

            # download_image returns test PNG
            mock_download.return_value = test_png

            exit_code = _run_conversion(
                url="https://docsend.com/view/abc123",
                email=None, passcode=None, verification_code=None,
                accept_nda_flag=False, output_path=output_path, json_mode=True,
                quiet=True, session_blob=None, state_file=None,
            )

        assert exit_code == 0
        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "complete"
        assert output["pages"] == 3
        assert Path(output_path).exists()
