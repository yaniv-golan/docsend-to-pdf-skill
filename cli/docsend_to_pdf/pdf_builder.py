from __future__ import annotations

import io

from PIL import Image


def process_image(png_bytes: bytes) -> Image.Image:
    """Load a PNG and composite RGBA onto a white RGB background."""
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def build_pdf(images: list[Image.Image], output_path: str) -> None:
    """Assemble a list of RGB images into a multi-page PDF."""
    if not images:
        raise ValueError("No images to assemble into PDF")
    first, *rest = images
    first.save(
        output_path,
        format="PDF",
        save_all=True,
        append_images=rest,
    )
