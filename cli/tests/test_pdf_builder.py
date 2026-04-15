import io
from pathlib import Path

import pytest
from PIL import Image

from docsend_to_pdf.pdf_builder import process_image, build_pdf


def _make_rgba_png(width: int = 100, height: int = 80, alpha: int = 128) -> bytes:
    """Create a minimal RGBA PNG as bytes."""
    img = Image.new("RGBA", (width, height), (255, 0, 0, alpha))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgb_png(width: int = 100, height: int = 80) -> bytes:
    """Create a minimal RGB PNG as bytes (no alpha)."""
    img = Image.new("RGB", (width, height), (0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestProcessImage:
    def test_rgba_to_rgb(self):
        png_bytes = _make_rgba_png()
        result = process_image(png_bytes)
        assert result.mode == "RGB"

    def test_composites_on_white(self):
        # Fully transparent red on white should be white
        png_bytes = _make_rgba_png(alpha=0)
        result = process_image(png_bytes)
        pixel = result.getpixel((50, 40))
        assert pixel == (255, 255, 255)

    def test_opaque_preserved(self):
        # Fully opaque red should stay red
        png_bytes = _make_rgba_png(alpha=255)
        result = process_image(png_bytes)
        pixel = result.getpixel((50, 40))
        assert pixel == (255, 0, 0)

    def test_handles_rgb_input(self):
        png_bytes = _make_rgb_png()
        result = process_image(png_bytes)
        assert result.mode == "RGB"


class TestBuildPdf:
    def test_single_page(self, tmp_path: Path):
        img = process_image(_make_rgba_png())
        output = tmp_path / "test.pdf"
        build_pdf([img], str(output))
        assert output.exists()
        assert output.stat().st_size > 0

    def test_multi_page(self, tmp_path: Path):
        images = [process_image(_make_rgba_png()) for _ in range(3)]
        output = tmp_path / "multi.pdf"
        build_pdf(images, str(output))
        assert output.exists()
        assert output.stat().st_size > 0

    def test_empty_raises(self, tmp_path: Path):
        output = tmp_path / "empty.pdf"
        with pytest.raises(ValueError, match="No images"):
            build_pdf([], str(output))
