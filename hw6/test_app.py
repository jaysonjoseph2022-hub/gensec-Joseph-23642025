import tempfile
import unittest
from pathlib import Path

from PIL import Image

from steganography import (
    MAX_MESSAGE_BYTES,
    decode_message,
    encode_message,
    load_png_image,
    save_encoded_png,
)


class SteganographyTests(unittest.TestCase):
    def test_encoded_message_round_trips(self) -> None:
        carrier = Image.new("RGB", (40, 40), color=(126, 181, 145))
        message = "A local message: café and tea."

        encoded = encode_message(carrier, message)

        self.assertEqual(decode_message(encoded), message)
        self.assertEqual(carrier.getpixel((0, 0)), (126, 181, 145))

    def test_rgba_alpha_channel_is_preserved(self) -> None:
        carrier = Image.new("RGBA", (40, 40), color=(126, 181, 145, 73))

        encoded = encode_message(carrier, "alpha stays unchanged")

        self.assertEqual(encoded.getpixel((0, 0))[3], 73)
        self.assertEqual(decode_message(encoded), "alpha stays unchanged")

    def test_empty_message_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            encode_message(Image.new("RGB", (20, 20)), "")

    def test_insufficient_capacity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "too long"):
            encode_message(Image.new("RGB", (3, 3)), "message")

    def test_message_size_limit_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, "limited"):
            encode_message(Image.new("RGB", (500, 500)), "x" * (MAX_MESSAGE_BYTES + 1))

    def test_decoder_rejects_oversized_length_header(self) -> None:
        carrier = Image.new("RGB", (200, 200))
        pixel_data = bytearray(carrier.tobytes())
        header = (MAX_MESSAGE_BYTES + 1).to_bytes(4, "big")
        header_bits = ((byte >> shift) & 1 for byte in header for shift in range(7, -1, -1))
        for index, bit in enumerate(header_bits):
            pixel_data[index] = (pixel_data[index] & 0xFE) | bit

        malformed = Image.frombytes("RGB", carrier.size, bytes(pixel_data))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            decode_message(malformed)

    def test_invalid_image_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_path = Path(temporary_directory) / "invalid.png"
            invalid_path.write_bytes(b"not a PNG image")

            with self.assertRaisesRegex(ValueError, "valid, readable PNG"):
                load_png_image(invalid_path)

    def test_non_png_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            jpeg_path = Path(temporary_directory) / "carrier.jpg"
            Image.new("RGB", (4, 4)).save(jpeg_path, format="JPEG")

            with self.assertRaisesRegex(ValueError, "select a PNG"):
                load_png_image(jpeg_path)

    def test_truncated_png_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            truncated_path = Path(temporary_directory) / "truncated.png"
            image_path = Path(temporary_directory) / "complete.png"
            Image.new("RGB", (20, 20)).save(image_path)
            truncated_path.write_bytes(image_path.read_bytes()[:24])

            with self.assertRaisesRegex(ValueError, "valid, readable PNG"):
                load_png_image(truncated_path)

    def test_malformed_png_chunk_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            malformed_path = Path(temporary_directory) / "malformed.png"
            valid_path = Path(temporary_directory) / "valid.png"
            Image.new("RGB", (20, 20)).save(valid_path)
            png_data = bytearray(valid_path.read_bytes())
            chunk_type = png_data.find(b"IDAT")
            self.assertNotEqual(chunk_type, -1)
            png_data[chunk_type : chunk_type + 4] = b"JUNK"
            malformed_path.write_bytes(png_data)

            with self.assertRaisesRegex(ValueError, "valid, readable PNG"):
                load_png_image(malformed_path)

    def test_existing_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_path = directory / "source.png"
            destination_path = directory / "already-there.png"
            source = Image.new("RGB", (40, 40), color=(126, 181, 145))
            source.save(source_path)
            destination_path.write_bytes(b"keep this file")
            encoded = encode_message(source, "protected output")

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                save_encoded_png(encoded, source_path, destination_path)

            self.assertEqual(destination_path.read_bytes(), b"keep this file")

    def test_source_image_cannot_be_used_as_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "source.png"
            source = Image.new("RGB", (40, 40), color=(126, 181, 145))
            source.save(source_path)
            original_bytes = source_path.read_bytes()
            encoded = encode_message(source, "do not overwrite")

            with self.assertRaisesRegex(ValueError, "never overwritten"):
                save_encoded_png(encoded, source_path, source_path)

            self.assertEqual(source_path.read_bytes(), original_bytes)

    def test_new_destination_saves_and_decodes_as_png(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "source.png"
            destination_path = Path(temporary_directory) / "encoded.png"
            source = Image.new("RGB", (40, 40), color=(126, 181, 145))
            source.save(source_path)
            original_bytes = source_path.read_bytes()
            encoded = encode_message(source, "saved locally")

            saved_path = save_encoded_png(encoded, source_path, destination_path)

            self.assertEqual(saved_path, destination_path.resolve())
            with Image.open(saved_path) as saved_image:
                self.assertEqual(saved_image.format, "PNG")
            self.assertEqual(decode_message(load_png_image(saved_path)), "saved locally")
            self.assertEqual(source_path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()