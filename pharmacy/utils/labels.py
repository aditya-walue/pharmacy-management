"""Barcodes for label print formats (exposed to Jinja via hooks)."""

import base64
from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter


def barcode_img(value, height=12, show_text=False):
	"""Code128 barcode as a data-URI PNG, which renders in both the browser and PDF."""
	if not value:
		return ""
	buffer = BytesIO()
	Code128(str(value), writer=ImageWriter()).write(
		buffer, options={"module_height": height, "quiet_zone": 2, "write_text": show_text, "dpi": 300}
	)
	return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
