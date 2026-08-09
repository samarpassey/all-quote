"""Text and image redaction. See PLAN.md Task 3.

Will expose `redact_text(str)` (regex over ON licence/DOB/postal code/VIN/phone
patterns) and `redact_image(png_bytes, boxes)` (Pillow black-fill). This is the
only module allowed to touch raw evidence payloads before they're written.
"""
