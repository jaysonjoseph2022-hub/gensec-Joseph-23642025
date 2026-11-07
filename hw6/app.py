"""Tkinter interface for educational PNG text steganography."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk

from steganography import (
	MAX_MESSAGE_BYTES,
	decode_message,
	encode_message,
	load_png_image,
	message_capacity_bytes,
	save_encoded_png,
)


class SteganographyApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("Pixel Signal | Local Steganography Studio")
		self.root.geometry("1120x760")
		self.root.minsize(900, 640)
		self.colors = {
			"background": "#0b1118",
			"sidebar": "#0e1722",
			"panel": "#111d29",
			"panel_alt": "#162635",
			"input": "#0a141e",
			"border": "#263b4e",
			"text": "#e5f0f8",
			"muted": "#91a7ba",
			"cyan": "#54d7e5",
			"blue": "#4e8cf5",
			"green": "#62d6a6",
			"red": "#ff7889",
		}

		self.encode_source: Image.Image | None = None
		self.encode_source_path: Path | None = None
		self.encoded_image: Image.Image | None = None
		self.decode_source: Image.Image | None = None
		self.encode_photo: ImageTk.PhotoImage | None = None
		self.decode_photo: ImageTk.PhotoImage | None = None
		self.pages: dict[str, tk.Frame] = {}
		self.nav_buttons: dict[str, tk.Button] = {}
		self.nav_indicators: dict[str, tk.Frame] = {}

		self._build_interface()

	def _build_interface(self) -> None:
		shell = tk.Frame(self.root, bg=self.colors["background"])
		shell.pack(fill="both", expand=True)
		shell.grid_columnconfigure(1, weight=1)
		shell.grid_rowconfigure(0, weight=1)

		self.sidebar = tk.Frame(shell, bg=self.colors["sidebar"], width=224)
		self.sidebar.grid(row=0, column=0, sticky="ns")
		self.sidebar.grid_propagate(False)
		self._build_sidebar()

		main = tk.Frame(shell, bg=self.colors["background"])
		main.grid(row=0, column=1, sticky="nsew")
		main.grid_columnconfigure(0, weight=1)
		main.grid_rowconfigure(1, weight=1)

		header = tk.Frame(main, bg=self.colors["background"], padx=34, pady=25)
		header.grid(row=0, column=0, sticky="ew")
		self.page_heading = tk.Label(
			header,
			text="",
			bg=self.colors["background"],
			fg=self.colors["text"],
			font=("TkDefaultFont", 22, "bold"),
			anchor="w",
		)
		self.page_heading.pack(anchor="w")
		self.page_subheading = tk.Label(
			header,
			text="",
			bg=self.colors["background"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 10),
			anchor="w",
		)
		self.page_subheading.pack(anchor="w", pady=(5, 0))

		self.page_area = tk.Frame(main, bg=self.colors["background"], padx=34, pady=0)
		self.page_area.grid(row=1, column=0, sticky="nsew")
		self.page_area.grid_columnconfigure(0, weight=1)
		self.page_area.grid_rowconfigure(0, weight=1)
		self._build_encode_page()
		self._build_decode_page()
		self._build_about_page()

		status_wrap = tk.Frame(main, bg=self.colors["panel"], padx=18, pady=11)
		status_wrap.grid(row=2, column=0, sticky="ew")
		status_wrap.grid_columnconfigure(1, weight=1)
		self.status_mark = tk.Label(
			status_wrap,
			text="●",
			bg=self.colors["panel"],
			fg=self.colors["cyan"],
			font=("TkDefaultFont", 9),
		)
		self.status_mark.grid(row=0, column=0, padx=(0, 10))
		self.status = tk.StringVar(value="Ready  /  Choose a PNG to begin")
		self.status_label = tk.Label(
			status_wrap,
			textvariable=self.status,
			bg=self.colors["panel"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 9),
			anchor="w",
		)
		self.status_label.grid(row=0, column=1, sticky="ew")
		self._show_page("encode")

	def _build_sidebar(self) -> None:
		brand = tk.Frame(self.sidebar, bg=self.colors["sidebar"], padx=22, pady=25)
		brand.pack(fill="x")
		tk_label = tk.Label(
			brand,
			text="PIXEL SIGNAL",
			bg=self.colors["sidebar"],
			fg=self.colors["text"],
			font=("TkDefaultFont", 15, "bold"),
			anchor="w",
		)
		tk_label.pack(anchor="w")
		tk_subtitle = tk.Label(
			brand,
			text="LOCAL STEGANOGRAPHY STUDIO",
			bg=self.colors["sidebar"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 8, "bold"),
			anchor="w",
		)
		tk_subtitle.pack(anchor="w", pady=(5, 0))

		nav_label = tk.Label(
			self.sidebar,
			text="WORKSPACE",
			bg=self.colors["sidebar"],
			fg="#647b8e",
			font=("TkDefaultFont", 8, "bold"),
			anchor="w",
			padx=22,
			pady=14,
		)
		nav_label.pack(fill="x", pady=(12, 0))
		for key, number, title in (
			("encode", "01", "Encode"),
			("decode", "02", "Decode"),
			("about", "03", "About"),
		):
			self._add_nav_item(key, number, title)

		footer = tk.Frame(self.sidebar, bg=self.colors["sidebar"], padx=22, pady=20)
		footer.pack(side="bottom", fill="x")
		tk.Frame(footer, bg=self.colors["border"], height=1).pack(fill="x", pady=(0, 14))
		local_note = tk.Label(
			footer,
			text="●  OFFLINE BY DESIGN\n   Files stay on this device",
			bg=self.colors["sidebar"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 9),
			justify="left",
			anchor="w",
		)
		local_note.pack(anchor="w")

	def _add_nav_item(self, key: str, number: str, title: str) -> None:
		row = tk.Frame(self.sidebar, bg=self.colors["sidebar"], padx=12, pady=2)
		row.pack(fill="x")
		indicator = tk.Frame(row, bg=self.colors["sidebar"], width=3)
		indicator.pack(side="left", fill="y", padx=(0, 8))
		button = tk.Button(
			row,
			text=f"{number}     {title}",
			command=lambda selected=key: self._show_page(selected),
			bg=self.colors["sidebar"],
			fg=self.colors["muted"],
			activebackground=self.colors["panel_alt"],
			activeforeground=self.colors["text"],
			font=("TkDefaultFont", 10, "bold"),
			anchor="w",
			padx=13,
			pady=12,
			relief="flat",
			borderwidth=0,
			cursor="hand2",
		)
		button.pack(side="left", fill="x", expand=True)
		self.nav_buttons[key] = button
		self.nav_indicators[key] = indicator

	def _build_encode_page(self) -> None:
		page = tk.Frame(self.page_area, bg=self.colors["background"])
		self.pages["encode"] = page
		body = tk.Frame(page, bg=self.colors["background"])
		body.pack(fill="both", expand=True)
		body.grid_columnconfigure(0, weight=4, minsize=250)
		body.grid_columnconfigure(1, weight=6, minsize=320)
		body.grid_rowconfigure(0, weight=1)

		image_card, self.encode_preview, self.encode_info = self._image_card(
			body, "01  /  CARRIER IMAGE", "Choose a PNG", self._browse_encode_image
		)
		image_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

		message_card = self._card(body)
		message_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
		self._card_heading(message_card, "02  /  MESSAGE", "Write your message", "Text is stored locally in the PNG color data.")
		self.capacity_info = tk.Label(
			message_card,
			text="Select an image to view its available capacity.",
			bg=self.colors["panel"],
			fg=self.colors["cyan"],
			font=("TkDefaultFont", 9, "bold"),
			anchor="w",
		)
		self.capacity_info.pack(fill="x", padx=20, pady=(16, 8))
		self.message_input = tk.Text(
			message_card,
			height=10,
			wrap="word",
			undo=True,
			font=("TkFixedFont", 10),
			bg=self.colors["input"],
			fg=self.colors["text"],
			insertbackground=self.colors["cyan"],
			selectbackground="#28516a",
			selectforeground=self.colors["text"],
			relief="flat",
			borderwidth=0,
			padx=12,
			pady=12,
		)
		self.message_input.pack(fill="both", expand=True, padx=20)
		self.message_input.bind("<KeyRelease>", self._update_message_count)
		self.message_count = tk.Label(
			message_card,
			text=f"0 / {MAX_MESSAGE_BYTES:,} bytes",
			bg=self.colors["panel"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 9),
			anchor="e",
		)
		self.message_count.pack(fill="x", padx=20, pady=(8, 14))

		actions = tk.Frame(message_card, bg=self.colors["panel"])
		actions.pack(fill="x", padx=20, pady=(0, 20))
		self.save_button = self._button(
			actions, "Save PNG", self._save_encoded, "secondary", state="disabled"
		)
		self.save_button.pack(side="right")
		self._button(actions, "Encode message", self._encode, "primary").pack(side="right", padx=(0, 9))

	def _build_decode_page(self) -> None:
		page = tk.Frame(self.page_area, bg=self.colors["background"])
		self.pages["decode"] = page
		body = tk.Frame(page, bg=self.colors["background"])
		body.pack(fill="both", expand=True)
		body.grid_columnconfigure(0, weight=4, minsize=250)
		body.grid_columnconfigure(1, weight=6, minsize=320)
		body.grid_rowconfigure(0, weight=1)

		image_card, self.decode_preview, self.decode_info = self._image_card(
			body, "01  /  ENCODED IMAGE", "Choose a PNG", self._browse_decode_image
		)
		image_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

		message_card = self._card(body)
		message_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
		self._card_heading(message_card, "02  /  RECOVERED TEXT", "Decoded message", "Recovered content is displayed as plain text only.")
		self.decoded_output = tk.Text(
			message_card,
			height=14,
			wrap="word",
			font=("TkFixedFont", 10),
			bg=self.colors["input"],
			fg=self.colors["text"],
			insertbackground=self.colors["cyan"],
			selectbackground="#28516a",
			selectforeground=self.colors["text"],
			relief="flat",
			borderwidth=0,
			padx=12,
			pady=12,
		)
		self.decoded_output.pack(fill="both", expand=True, padx=20, pady=(18, 12))
		self.decoded_output.configure(state="disabled")

		actions = tk.Frame(message_card, bg=self.colors["panel"])
		actions.pack(fill="x", padx=20, pady=(0, 20))
		self._button(actions, "Copy message", self._copy_message, "secondary").pack(side="right")
		self._button(actions, "Decode message", self._decode, "primary").pack(side="right", padx=(0, 9))

	def _build_about_page(self) -> None:
		page = tk.Frame(self.page_area, bg=self.colors["background"])
		self.pages["about"] = page
		page.grid_columnconfigure(0, weight=1)
		for row in range(3):
			page.grid_rowconfigure(row, weight=1)
		sections = (
			(
				"THE IDEA",
				"What is image steganography?",
				"Steganography places a message inside an ordinary-looking file so the message is less apparent. This app demonstrates the idea with short text stored in PNG images.",
				self.colors["cyan"],
			),
			(
				"THE METHOD",
				"Least significant bit (LSB)",
				"Each red, green, or blue channel value is represented by bits. The encoder changes selected final bits to carry message data; those tiny changes are generally hard to notice, but image editing or lossy conversion can destroy them.",
				self.colors["blue"],
			),
			(
				"THE DISTINCTION",
				"Steganography is not encryption",
				"Steganography aims to conceal that a message exists. Encryption transforms message contents so they are difficult to read without a key. This educational app does not encrypt messages, so do not use it to protect sensitive information.",
				self.colors["green"],
			),
		)
		for row, (eyebrow, title, description, accent) in enumerate(sections):
			card = self._card(page)
			card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
			tk_accent = tk.Frame(card, bg=accent, width=3)
			tk_accent.pack(side="left", fill="y")
			content = tk.Frame(card, bg=self.colors["panel"], padx=20, pady=14)
			content.pack(side="left", fill="both", expand=True)
			tk_label = tk.Label(
				content, text=eyebrow, bg=self.colors["panel"], fg=accent,
				font=("TkDefaultFont", 8, "bold"), anchor="w",
			)
			tk_label.pack(anchor="w")
			title_label = tk.Label(
				content, text=title, bg=self.colors["panel"], fg=self.colors["text"],
				font=("TkDefaultFont", 13, "bold"), anchor="w",
			)
			title_label.pack(anchor="w", pady=(5, 4))
			description_label = tk.Label(
				content, text=description, bg=self.colors["panel"], fg=self.colors["muted"],
				font=("TkDefaultFont", 10), anchor="w", justify="left", wraplength=760,
			)
			description_label.pack(fill="x", anchor="w")

	def _card(self, parent: tk.Widget) -> tk.Frame:
		return tk.Frame(
			parent,
			bg=self.colors["panel"],
			highlightbackground=self.colors["border"],
			highlightthickness=1,
		)

	def _card_heading(self, card: tk.Frame, eyebrow: str, title: str, description: str) -> None:
		eyebrow_label = tk.Label(
			card, text=eyebrow, bg=self.colors["panel"], fg=self.colors["cyan"],
			font=("TkDefaultFont", 8, "bold"), anchor="w",
		)
		eyebrow_label.pack(fill="x", padx=20, pady=(19, 7))
		title_label = tk.Label(
			card, text=title, bg=self.colors["panel"], fg=self.colors["text"],
			font=("TkDefaultFont", 15, "bold"), anchor="w",
		)
		title_label.pack(fill="x", padx=20)
		description_label = tk.Label(
			card, text=description, bg=self.colors["panel"], fg=self.colors["muted"],
			font=("TkDefaultFont", 9), anchor="w", justify="left", wraplength=430,
		)
		description_label.pack(fill="x", padx=20, pady=(5, 0))

	def _image_card(
		self, parent: tk.Widget, eyebrow: str, title: str, browse_command
	) -> tuple[tk.Frame, tk.Label, tk.Label]:
		card = self._card(parent)
		self._card_heading(card, eyebrow, title, "PNG images are checked before processing.")
		preview = tk.Label(
			card,
			text="Select a PNG\nto preview it",
			bg=self.colors["input"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 10),
			width=24,
			height=10,
			justify="center",
			anchor="center",
		)
		preview.pack(fill="both", expand=True, padx=20, pady=(18, 14))
		info = tk.Label(
			card,
			text="No image selected",
			bg=self.colors["panel"],
			fg=self.colors["muted"],
			font=("TkDefaultFont", 9),
			justify="left",
			anchor="w",
		)
		info.pack(fill="x", padx=20, pady=(0, 14))
		self._button(card, "Browse PNG", browse_command, "secondary").pack(
			fill="x", padx=20, pady=(0, 20)
		)
		return card, preview, info

	def _button(
		self,
		parent: tk.Widget,
		text: str,
		command,
		kind: str,
		state: str = "normal",
	) -> tk.Button:
		primary = kind == "primary"
		background = self.colors["blue"] if primary else self.colors["panel_alt"]
		foreground = "#ffffff" if primary else self.colors["text"]
		return tk.Button(
			parent,
			text=text,
			command=command,
			state=state,
			bg=background,
			fg=foreground,
			activebackground=self.colors["cyan"] if primary else self.colors["border"],
			activeforeground=self.colors["text"],
			disabledforeground="#647b8e",
			font=("TkDefaultFont", 10, "bold"),
			padx=16,
			pady=10,
			borderwidth=0,
			relief="flat",
			cursor="hand2" if state == "normal" else "arrow",
		)

	def _show_page(self, key: str) -> None:
		titles = {
			"encode": ("Encode a message", "Place a short text message into a PNG image."),
			"decode": ("Decode a message", "Recover text from a PNG created with this application."),
			"about": ("About this tool", "A local, educational demonstration of image steganography."),
		}
		for page in self.pages.values():
			page.pack_forget()
		self.pages[key].pack(fill="both", expand=True)
		self.page_heading.configure(text=titles[key][0])
		self.page_subheading.configure(text=titles[key][1])
		for item, button in self.nav_buttons.items():
			active = item == key
			button.configure(
				bg=self.colors["panel_alt"] if active else self.colors["sidebar"],
				fg=self.colors["text"] if active else self.colors["muted"],
			)
			self.nav_indicators[item].configure(bg=self.colors["cyan"] if active else self.colors["sidebar"])

	def _notify(self, message: str, kind: str = "info") -> None:
		color = {
			"info": self.colors["cyan"],
			"success": self.colors["green"],
			"error": self.colors["red"],
		}.get(kind, self.colors["cyan"])
		self.status.set(message)
		self.status_label.configure(fg=color)
		self.status_mark.configure(fg=color)

	def _set_preview(self, image: Image.Image, preview: tk.Label, info: tk.Label, encode: bool) -> None:
		thumbnail = image.copy()
		thumbnail.thumbnail((200, 160), Image.Resampling.LANCZOS)
		photo = ImageTk.PhotoImage(thumbnail)
		preview.configure(image=photo, text="", width=0, height=0)
		if encode:
			self.encode_photo = photo
		else:
			self.decode_photo = photo
		info.configure(text=f"{image.width} × {image.height} px   /   {image.mode}")
		if encode:
			capacity = message_capacity_bytes(image)
			self.capacity_info.configure(
				text=f"Available capacity: {capacity:,} bytes  /  Maximum {MAX_MESSAGE_BYTES:,} bytes"
			)
			self._update_message_count()

	def _update_message_count(self, _event=None) -> None:
		if not hasattr(self, "message_input"):
			return
		message = self.message_input.get("1.0", "end-1c")
		byte_count = len(message.encode("utf-8"))
		limit = min(
			MAX_MESSAGE_BYTES,
			message_capacity_bytes(self.encode_source) if self.encode_source is not None else MAX_MESSAGE_BYTES,
		)
		self.message_count.configure(
			text=f"{byte_count:,} / {limit:,} bytes",
			fg=self.colors["red"] if byte_count > limit else self.colors["muted"],
		)

	def _browse_encode_image(self) -> None:
		selected = filedialog.askopenfilename(
			title="Select a carrier PNG",
			filetypes=(("PNG images", ("*.png", "*.PNG")),),
		)
		if not selected:
			return
		self.encode_source = None
		self.encode_source_path = None
		self.encoded_image = None
		self.encode_photo = None
		self.encode_preview.configure(image="", text="Select a PNG\nto preview it", width=24, height=10)
		self.encode_info.configure(text="No image selected")
		self.capacity_info.configure(text="Select an image to view its available capacity.")
		self.save_button.configure(state="disabled")
		try:
			self.encode_source = load_png_image(selected)
			self.encode_source_path = Path(selected).resolve()
			self._set_preview(self.encode_source, self.encode_preview, self.encode_info, encode=True)
			self._notify("Carrier PNG loaded. Enter a message to continue.", "success")
		except (OSError, RuntimeError, ValueError) as exc:
			self.encode_source = None
			self.encode_source_path = None
			self._notify(f"Could not load image: {exc}", "error")

	def _encode(self) -> None:
		if self.encode_source is None:
			self._notify("Choose a carrier PNG before encoding.", "error")
			return
		try:
			self.encoded_image = encode_message(
				self.encode_source,
				self.message_input.get("1.0", "end-1c"),
			)
			self.save_button.configure(state="normal")
			self._notify("Message encoded. Save it as a new PNG to finish.", "success")
		except (UnicodeError, ValueError) as exc:
			self.encoded_image = None
			self.save_button.configure(state="disabled")
			self._notify(f"Could not encode message: {exc}", "error")

	def _save_encoded(self) -> None:
		if self.encoded_image is None or self.encode_source_path is None:
			self._notify("Encode a message before saving.", "error")
			return
		selected = filedialog.asksaveasfilename(
			title="Save encoded PNG",
			defaultextension=".png",
			initialfile=f"{self.encode_source_path.stem}_encoded.png",
			filetypes=(("PNG images", "*.png"),),
		)
		if not selected:
			return
		try:
			destination = save_encoded_png(self.encoded_image, self.encode_source_path, selected)
			self._notify(f"Encoded image saved as {destination.name}.", "success")
		except FileExistsError as exc:
			self._notify(str(exc), "error")
		except (OSError, RuntimeError, ValueError) as exc:
			self._notify(f"Could not save image: {exc}", "error")
		except Exception as exc:
			self._notify(f"Unexpected save error: {exc}", "error")

	def _browse_decode_image(self) -> None:
		selected = filedialog.askopenfilename(
			title="Select an encoded PNG",
			filetypes=(("PNG images", ("*.png", "*.PNG")),),
		)
		if not selected:
			return
		self.decode_source = None
		self.decode_photo = None
		self.decode_preview.configure(image="", text="Select a PNG\nto preview it", width=24, height=10)
		self.decode_info.configure(text="No image selected")
		self._set_decoded_text("")
		try:
			self.decode_source = load_png_image(selected)
			self._set_preview(self.decode_source, self.decode_preview, self.decode_info, encode=False)
			self._notify("PNG loaded. Decode it to inspect the recovered text.", "success")
		except (OSError, RuntimeError, ValueError) as exc:
			self.decode_source = None
			self._notify(f"Could not load image: {exc}", "error")

	def _decode(self) -> None:
		if self.decode_source is None:
			self._notify("Choose an encoded PNG before decoding.", "error")
			return
		try:
			message = decode_message(self.decode_source)
			self._set_decoded_text(message)
			self._notify("Message recovered and displayed as plain text.", "success")
		except ValueError as exc:
			self._set_decoded_text("")
			self._notify(f"Could not decode message: {exc}", "error")

	def _set_decoded_text(self, message: str) -> None:
		self.decoded_output.configure(state="normal")
		self.decoded_output.delete("1.0", "end")
		if message:
			self.decoded_output.insert("1.0", message)
		self.decoded_output.configure(state="disabled")

	def _copy_message(self) -> None:
		message = self.decoded_output.get("1.0", "end-1c")
		if not message:
			self._notify("There is no recovered message to copy yet.", "error")
			return
		try:
			self.root.clipboard_clear()
			self.root.clipboard_append(message)
			self.root.update_idletasks()
			self._notify("Recovered message copied to the clipboard.", "success")
		except tk.TclError as exc:
			self._notify(f"Could not access the clipboard: {exc}", "error")


def main() -> None:
	root = tk.Tk()
	SteganographyApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()