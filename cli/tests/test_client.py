import pytest
from docsend_to_pdf.client import detect_gate, parse_page_response
from docsend_to_pdf.types import GateKind


class TestDetectGate:
    def test_email_gate(self, fixture_html):
        html = fixture_html("email_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.EMAIL

    def test_passcode_gate(self, fixture_html):
        html = fixture_html("passcode_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.PASSCODE

    def test_nda_gate(self, fixture_html):
        html = fixture_html("nda_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.NDA
        assert "confidential" in gate.text.lower()

    def test_verification_gate(self, fixture_html):
        html = fixture_html("verification_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.VERIFICATION
        assert "user@example.com" in gate.text

    def test_rejected(self, fixture_html):
        html = fixture_html("rejected.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.REJECTED
        assert "not authorized" in gate.text.lower()

    def test_authenticated(self, fixture_html):
        html = fixture_html("authenticated.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.NONE


class TestParsePageResponse:
    def test_extracts_csrf_token(self, fixture_html):
        html = fixture_html("email_gate.html")
        resp = parse_page_response(html)
        assert resp.csrf_token == "csrf-token-123"

    def test_extracts_page_count_when_authenticated(self, fixture_html):
        html = fixture_html("authenticated.html")
        resp = parse_page_response(html)
        assert resp.page_count == 12

    def test_page_count_none_when_gated(self, fixture_html):
        html = fixture_html("email_gate.html")
        resp = parse_page_response(html)
        assert resp.page_count is None

    def test_extracts_title(self, fixture_html):
        html = fixture_html("authenticated.html")
        resp = parse_page_response(html)
        assert resp.title == "Series A Deck"
