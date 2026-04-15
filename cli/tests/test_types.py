import pytest
from docsend_to_pdf.types import DocSendURL, parse_url


class TestParseUrl:
    def test_standard_url(self):
        result = parse_url("https://docsend.com/view/abc123")
        assert result.doc_id == "abc123"
        assert result.normalized == "https://docsend.com/view/abc123"

    def test_subdomain_url(self):
        result = parse_url("https://company.docsend.com/view/xyz789")
        assert result.doc_id == "xyz789"
        assert result.normalized == "https://company.docsend.com/view/xyz789"

    def test_dropbox_variant(self):
        result = parse_url("https://www.docsend.dropbox.com/view/def456")
        assert result.doc_id == "def456"
        assert result.normalized == "https://www.docsend.dropbox.com/view/def456"

    def test_trailing_slash(self):
        result = parse_url("https://docsend.com/view/abc123/")
        assert result.doc_id == "abc123"

    def test_with_query_params(self):
        result = parse_url("https://docsend.com/view/abc123?ref=email")
        assert result.doc_id == "abc123"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid DocSend URL"):
            parse_url("https://google.com/doc/123")

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="Not a valid DocSend URL"):
            parse_url("https://docsend.com/view/")

    def test_preserves_original(self):
        url = "https://docsend.com/view/abc123?ref=email"
        result = parse_url(url)
        assert result.original == url

    def test_short_v_format(self):
        result = parse_url("https://docsend.com/v/wp8mh/something-big")
        assert result.doc_id == "wp8mh"
        assert result.normalized == "https://docsend.com/view/wp8mh"

    def test_short_v_without_slug(self):
        result = parse_url("https://docsend.com/v/abc123")
        assert result.doc_id == "abc123"
        assert result.normalized == "https://docsend.com/view/abc123"

    def test_short_v_subdomain(self):
        result = parse_url("https://company.docsend.com/v/xyz789/my-deck")
        assert result.doc_id == "xyz789"
        assert result.normalized == "https://company.docsend.com/view/xyz789"

    def test_space_url_raises(self):
        with pytest.raises(ValueError, match="Space.*folder"):
            parse_url("https://lool.docsend.com/view/s/pk5sbu2zm2fw2bia")

    def test_space_url_plain_domain_raises(self):
        with pytest.raises(ValueError, match="Space.*folder"):
            parse_url("https://docsend.com/view/s/abc123")
