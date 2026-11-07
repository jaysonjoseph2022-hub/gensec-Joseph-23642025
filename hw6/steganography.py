"""Educational PNG text steganography using RGB least-significant bits."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_PIXELS = 20_000_000
MAX_MESSAGE_BYTES = 64 * 1024
LENGTH_HEADER_BYTES = 4


def _validate_dimensions(size: tuple[int, int]) -> None:
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("The image has invalid dimensions.")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("The image is too large to process safely.")


def load_png_image(path: str | Path) -> Image.Image:
    """Load a real PNG image and return an independent, fully loaded copy."""
    try:
        with Image.open(path) as source:
            if source.format != "PNG":
                raise ValueError("Please select a PNG image.")
            _validate_dimensions(source.size)
            source.load()
            return source.copy()
    except ValueError:
        raise
    except (OSError, EOFError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("The selected file is not a valid, readable PNG image.") from exc


def message_capacity_bytes(image: Image.Image) -> int:
    """Return the supported UTF-8 payload capacity for an image."""
    _validate_dimensions(image.size)
    carrier_capacity = image.width * image.height * 3 // 8 - LENGTH_HEADER_BYTES
    return max(0, min(carrier_capacity, MAX_MESSAGE_BYTES))


def _rgb_image(image: Image.Image) -> Image.Image:
    if not isinstance(image, Image.Image):
        raise ValueError("A valid Pillow image is required.")
    _validate_dimensions(image.size)
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def _color_channel_indices(data_length: int, stride: int):
    for pixel_start in range(0, data_length, stride):
        yield pixel_start
        yield pixel_start + 1
        yield pixel_start + 2


def _bits_from_bytes(data: bytes):
    for byte in data:
        for shift in range(7, -1, -1):
            yield (byte >> shift) & 1


def encode_message(image: Image.Image, message: str) -> Image.Image:
    """Return a new image containing a UTF-8 message in RGB channel LSBs."""
    if not isinstance(message, str) or not message:
        raise ValueError("Enter a non-empty message to encode.")
    if len(message) > MAX_MESSAGE_BYTES:
        raise ValueError(f"Messages are limited to {MAX_MESSAGE_BYTES:,} UTF-8 bytes.")

    normalized = _rgb_image(image)
    payload = message.encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError(f"Messages are limited to {MAX_MESSAGE_BYTES:,} UTF-8 bytes.")
    framed_message = len(payload).to_bytes(LENGTH_HEADER_BYTES, "big") + payload
    pixel_data = bytearray(normalized.tobytes())
    stride = len(normalized.getbands())
    capacity_bits = normalized.width * normalized.height * 3
    required_bits = len(framed_message) * 8
    if required_bits > capacity_bits:
        raise ValueError(
            f"Message is too long for this image. It needs {required_bits} bits, "
            f"but the image holds {capacity_bits} bits."
        )

    # Store the length first, then each UTF-8 bit in the RGB channel LSBs.
    channel_indices = _color_channel_indices(len(pixel_data), stride)
    for index, bit in zip(channel_indices, _bits_from_bytes(framed_message)):
        pixel_data[index] = (pixel_data[index] & 0xFE) | bit

    return Image.frombytes(normalized.mode, normalized.size, bytes(pixel_data))


def decode_message(image: Image.Image) -> str:
    """Extract and return a UTF-8 message stored by :func:`encode_message`."""
    normalized = _rgb_image(image)
    capacity_bits = normalized.width * normalized.height * 3
    if capacity_bits < LENGTH_HEADER_BYTES * 8:
        raise ValueError("The image is too small to contain a message header.")

    pixel_data = normalized.tobytes()
    stride = len(normalized.getbands())
    channel_indices = _color_channel_indices(len(pixel_data), stride)

    def read_bytes(count: int) -> bytes:
        result = bytearray()
        for _ in range(count):
            value = 0
            for _ in range(8):
                try:
                    value = (value << 1) | (pixel_data[next(channel_indices)] & 1)
                except StopIteration as exc:
                    raise ValueError("The image does not contain a complete message.") from exc
            result.append(value)
        return bytes(result)

    payload_length = int.from_bytes(read_bytes(LENGTH_HEADER_BYTES), "big")
    if payload_length == 0:
        raise ValueError("No encoded message was found in this image.")
    if payload_length > MAX_MESSAGE_BYTES:
        raise ValueError(f"Encoded message exceeds the {MAX_MESSAGE_BYTES:,}-byte limit.")
    if (LENGTH_HEADER_BYTES + payload_length) * 8 > capacity_bits:
        raise ValueError("No complete encoded message was found in this image.")

    payload = read_bytes(payload_length)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("The image contains data that is not a valid text message.") from exc


def save_encoded_png(image: Image.Image, source_path: str | Path, destination_path: str | Path) -> Path:
    """Save a PNG only to a new path; existing files are never replaced."""
    try:
        source = Path(source_path).resolve()
        destination = Path(destination_path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("The selected save path could not be resolved.") from exc
    if destination == source:
        raise ValueError("Choose a different file name; the source image is never overwritten.")
    if destination.suffix.lower() != ".png":
        raise ValueError("Save the encoded image with a .png extension.")

    created = False
    try:
        with destination.open("xb") as output:
            created = True
            image.save(output, format="PNG")
    except FileExistsError as exc:
        raise FileExistsError("A file already exists at that location. Choose a new name.") from exc
    except Exception:
        if created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    return destination