"""Page images of one resume PDF, for a visual reading by an agent that cannot open a PDF's pages itself.

  process-resumes visual render FILE   # write the pages as images under `output/visual/pages/` and list their paths

Poppler's `pdftoppm` draws every page when it is installed. Without it, the JPEG page images already embedded in a
scanned PDF are copied out as they are, read with `pypdf` (Pillow is not needed), but only for a plain scan: each page's
parsed content draws one unmasked JPEG over the whole page and nothing else (no text, tiles, clip, vector painting,
annotations or rotation); any other PDF fails with the poppler advice instead of returning something that is not
what the page shows. A PDF longer than `MAX_PAGES` pages is refused, never cut short. The
resume folder is only read. The images are personal data, so they stay under the home folder and are removed when the
transcript for that PDF is confirmed. Library module.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from jk import common
from jk.resumes import resume_data as rd

PAGES_DIR: Final[Path] = rd.TEXT_DIR / "visual" / "pages"
MAX_PAGES: Final[int] = 30
DPI: Final[int] = 110
TOO_LONG: Final[str] = ("{name} has more than {limit} pages, so no page images were written (a partial reading "
                        "would look complete). Split the file, or give it as text, docx or md.")
NO_RENDERER: Final[str] = ("Cannot draw the pages of {name}: poppler's `pdftoppm` is not installed and the PDF is not "
                           "a plain scan (one JPEG covering each whole page) that can be copied out. Install poppler (macOS: `brew install poppler`; "
                           "Linux: the `poppler-utils` package), or give the file as text, docx or md.")


def pages_folder(transcript: Path) -> Path:
    """The folder for the page images of the PDF whose transcript is `transcript`."""
    return PAGES_DIR / transcript.stem


def clear(folder: Path) -> None:
    """Remove the page images in a folder (nothing happens when there are none)."""
    shutil.rmtree(folder, ignore_errors=True)


def _natural(path: Path) -> tuple[int, str]:
    """Sort key that puts page-2 before page-10."""
    match = re.search(r"(\d+)", path.stem)
    return (int(match.group(1)) if match else 0, path.name)


def _poppler(pdf: Path, folder: Path) -> list[Path]:
    """Draw the pages with `pdftoppm`; an empty list when it is not installed. Raises ToolError when it fails."""
    exe = shutil.which("pdftoppm")
    if exe is None:
        return []
    done = subprocess.run([exe, "-r", str(DPI), "-l", str(MAX_PAGES + 1), "-png", str(pdf), str(folder / "page")],
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise common.ToolError(f"pdftoppm could not draw {pdf.name}: {done.stderr.strip() or 'unknown error'}")
    return sorted(folder.glob("page-*.png"), key=_natural)


def _page_jpegs(page: Any) -> list[bytes]:
    """The JPEG images of a page: raw bytes of its image streams whose last filter is DCTDecode (no Pillow needed)."""
    jpegs: list[bytes] = []
    resources = page.get("/Resources")
    xobjects = resources.get_object().get("/XObject") if resources is not None else None
    for reference in xobjects.get_object().values() if xobjects is not None else []:
        item = reference.get_object()
        if item.get("/Subtype") != "/Image":
            continue
        filters = item.get("/Filter")
        names = list(filters) if isinstance(filters, list) else [filters]
        data = item.get_data() if names and names[-1] == "/DCTDecode" else b""
        if data[:2] == b"\xff\xd8":
            jpegs.append(data)
    return jpegs


PAINT_ONLY: Final[tuple[tuple[bytes, ...], ...]] = ((b"q", b"cm", b"Do", b"Q"), (b"cm", b"Do"))
COLOR_SPACES: Final[frozenset[str]] = frozenset({"/DeviceGray", "/DeviceRGB"})
TOLERANCE: Final[float] = 0.03       # share of the page an image may miss or overhang at an edge


def _plain_image(item: Any) -> bool:
    """True when an image is drawn exactly as its JPEG looks: no mask, soft mask, decode array or unusual colours."""
    if any(item.get(key) is not None for key in ("/SMask", "/Mask", "/Decode")) or item.get("/ImageMask"):
        return False
    space = item.get("/ColorSpace")
    space = space.get_object() if space is not None else None
    if isinstance(space, list) and len(space) == 2 and space[0] == "/ICCBased":
        return int(space[1].get_object().get("/N", 0)) in (1, 3)
    return space in COLOR_SPACES


def _fills_page(page: Any, matrix: list[float]) -> bool:
    """True when the `cm` matrix draws the image unrotated over the whole visible page, within TOLERANCE."""
    box, crop = page.mediabox, page.cropbox
    if [float(v) for v in box] != [float(v) for v in crop] or float(box.left) != 0 or float(box.bottom) != 0:
        return False
    width, height = float(box.width), float(box.height)
    a, b, c, d, e, f = matrix
    return b == 0 and c == 0 and abs(a - width) <= TOLERANCE * width and abs(d - height) <= TOLERANCE * height \
        and abs(e) <= TOLERANCE * width and abs(f) <= TOLERANCE * height


def _whole_page_jpeg(page: Any) -> bytes | None:
    """The page's one JPEG when the page is nothing but that image drawn over the whole page, else None.

    The content stream is parsed, not searched: it may hold only `q`, one `cm`, one `Do` of that image and `Q`.
    Anything else (text, a clip, vector painting over the image, a graphics state, a second image), annotations, a
    rotation, a crop box, a mask or an image placed anywhere but over the whole page means a copy of the JPEG would
    not be the page as it looks, so None is returned.
    """
    jpegs = _page_jpegs(page)
    resources = page.get("/Resources")
    xobjects = resources.get_object().get("/XObject") if resources is not None else None
    images = dict(xobjects.get_object()) if xobjects is not None else {}
    contents = page.get_contents()
    if len(jpegs) != 1 or len(images) != 1 or contents is None or page.get("/Annots"):
        return None
    name, image = next(iter(images.items()))
    if int(page.get("/Rotate", 0) or 0) % 360 != 0 or not _plain_image(image.get_object()):
        return None
    operations = contents.operations
    if tuple(op for _, op in operations) not in PAINT_ONLY:
        return None
    matrix = next(args for args, op in operations if op == b"cm")
    drawn = next(args for args, op in operations if op == b"Do")
    if drawn != [name] or not _fills_page(page, [float(v) for v in matrix]):
        return None
    return jpegs[0]


def _embedded(pdf: Path, folder: Path) -> list[Path]:
    """Copy out the JPEG of each page of a scanned PDF; an empty list when some page is not a plain whole-page scan."""
    try:
        found: list[Path] = []
        for number, page in enumerate(PdfReader(str(pdf)).pages, 1):
            jpeg = _whole_page_jpeg(page)
            if jpeg is None:
                return []
            target = folder / f"page-{number}.jpg"
            target.write_bytes(jpeg)
            found.append(target)
    except (OSError, ValueError, KeyError, NotImplementedError, PyPdfError):
        return []
    return found


def render(pdf: Path, folder: Path) -> list[Path]:
    """Write the pages of a PDF as images into `folder` (emptied first) and return their paths in page order.

    Raises:
        ToolError: no way to draw the pages is available.
    """
    clear(folder)
    folder.mkdir(parents=True, exist_ok=True)
    images = _poppler(pdf, folder) or _embedded(pdf, folder)
    if not images:
        clear(folder)
        raise common.ToolError(NO_RENDERER.format(name=pdf.name))
    if len(images) > MAX_PAGES:
        clear(folder)
        raise common.ToolError(TOO_LONG.format(name=pdf.name, limit=MAX_PAGES))
    return images
