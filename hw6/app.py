"""Tkinter interface for educational PNG text steganography."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
		self.root.title("PNG Message Studio")
		self.root.geometry("820x650")
		self.root.minsize(700, 560)
		self.root.configure(bg="#edf2ef")

		self.encode_source: Image.Image | None = None
		self.encode_source_path: Path | None = None
		self.encoded_image: Image.Image | None = None
		self.decode_source: Image.Image | None = None
		self.encode_photo: ImageTk.PhotoImage | None = None
		self.decode_photo: ImageTk.PhotoImage | None = None

		self._configure_styles()
		self._build_interface()

	def _configure_styles(self) -> None:
		style = ttk.Style(self.root)
		style.configure("App.TFrame", background="#edf2ef")
		style.configure("Panel.TFrame", background="#ffffff")
		style.configure("Title.TLabel", background="#edf2ef", foreground="#172d27", font=("TkDefaultFont", 21, "bold"))
		style.configure("Subtitle.TLabel", background="#edf2ef", foreground="#52645e", font=("TkDefaultFont", 10))
		style.configure("Panel.TLabel", background="#ffffff", foreground="#263b34")
		style.configure("Muted.TLabel", background="#ffffff", foreground="#667770")
		style.configure("Accent.TButton", font=("TkDefaultFont", 10, "bold"))
		style.configure("Status.TLabel", background="#dfe9e3", foreground="#29483b", padding=(12, 8))

	def _build_interface(self) -> None:
		shell = ttk.Frame(self.root, style="App.TFrame", padding=(24, 20, 24, 14))
		shell.pack(fill="both", expand=True)

		ttk.Label(shell, text="PNG Message Studio", style="Title.TLabel").pack(anchor="w")
		ttk.Label(
			shell,
			text="Encode or recover a short text message locally in a PNG image.",
			style="Subtitle.TLabel",
		).pack(anchor="w", pady=(4, 18))

		self.tabs = ttk.Notebook(shell)
		self.tabs.pack(fill="both", expand=True)
		self._build_encode_tab()
		self._build_decode_tab()

		self.status = tk.StringVar(value="Ready")
		ttk.Label(shell, textvariable=self.status, style="Status.TLabel").pack(fill="x", pady=(14, 0))

	def _build_encode_tab(self) -> None:
		tab = ttk.Frame(self.tabs, style="App.TFrame", padding=18)
		self.tabs.add(tab, text="Encode")

		carrier = ttk.LabelFrame(tab, text="1. Choose a carrier PNG", padding=14)
		carrier.pack(fill="x", pady=(0, 14))
		carrier.columnconfigure(1, weight=1)
		self.encode_preview = ttk.Label(carrier, text="PNG\npreview", anchor="center", width=16)
		self.encode_preview.grid(row=0, column=0, rowspan=2, padx=(0, 14), sticky="ns")
		self.encode_info = ttk.Label(carrier, text="No image selected", style="Muted.TLabel", wraplength=430)
		self.encode_info.grid(row=0, column=1, sticky="w")
		ttk.Button(carrier, text="Browse PNG...", command=self._browse_encode_image).grid(
			row=1, column=1, sticky="w", pady=(10, 0)
		)

		message_panel = ttk.LabelFrame(tab, text="2. Enter a short message", padding=14)
		message_panel.pack(fill="both", expand=True, pady=(0, 14))
		self.capacity_info = ttk.Label(
			message_panel,
			text=f"Up to {MAX_MESSAGE_BYTES // 1024} KiB; select an image to see its capacity.",
			style="Muted.TLabel",
		)
		self.capacity_info.pack(anchor="w", pady=(0, 8))
		self.message_input = tk.Text(
			message_panel,
			height=7,
			wrap="word",
			undo=True,
			font=("TkFixedFont", 10),
			relief="solid",
			borderwidth=1,
			padx=10,
			pady=8,
		)
		self.message_input.pack(fill="both", expand=True)

		actions = ttk.Frame(tab, style="App.TFrame")
		actions.pack(fill="x")
		ttk.Button(actions, text="Encode message", style="Accent.TButton", command=self._encode).pack(side="left")
		self.save_button = ttk.Button(actions, text="Save encoded PNG...", command=self._save_encoded, state="disabled")
		self.save_button.pack(side="left", padx=(10, 0))

	def _build_decode_tab(self) -> None:
		tab = ttk.Frame(self.tabs, style="App.TFrame", padding=18)
		self.tabs.add(tab, text="Decode")

		carrier = ttk.LabelFrame(tab, text="1. Choose an encoded PNG", padding=14)
		carrier.pack(fill="x", pady=(0, 14))
		carrier.columnconfigure(1, weight=1)
		self.decode_preview = ttk.Label(carrier, text="PNG\npreview", anchor="center", width=16)
		self.decode_preview.grid(row=0, column=0, rowspan=2, padx=(0, 14), sticky="ns")
		self.decode_info = ttk.Label(carrier, text="No image selected", style="Muted.TLabel", wraplength=430)
		self.decode_info.grid(row=0, column=1, sticky="w")
		ttk.Button(carrier, text="Browse PNG...", command=self._browse_decode_image).grid(
			row=1, column=1, sticky="w", pady=(10, 0)
		)

		output = ttk.LabelFrame(tab, text="2. Recovered message", padding=14)
		output.pack(fill="both", expand=True, pady=(0, 14))
		self.decoded_output = tk.Text(
			output,
			height=9,
			wrap="word",
			font=("TkFixedFont", 10),
			relief="solid",
			borderwidth=1,
			padx=10,
			pady=8,
		)
		self.decoded_output.pack(fill="both", expand=True)
		self.decoded_output.configure(state="disabled")
		ttk.Button(tab, text="Decode message", style="Accent.TButton", command=self._decode).pack(anchor="w")

	def _set_preview(self, image: Image.Image, preview: ttk.Label, info: ttk.Label, encode: bool) -> None:
		thumbnail = image.copy()
		thumbnail.thumbnail((132, 92), Image.Resampling.LANCZOS)
		photo = ImageTk.PhotoImage(thumbnail)
		preview.configure(image=photo, text="")
		if encode:
			self.encode_photo = photo
		else:
			self.decode_photo = photo
		info.configure(text=f"{image.width} x {image.height} px\n{image.mode} color image")
		if encode:
			capacity = message_capacity_bytes(image)
			self.capacity_info.configure(
				text=f"Available message capacity: {capacity:,} bytes (maximum {MAX_MESSAGE_BYTES:,})."
			)

	def _browse_encode_image(self) -> None:
		selected = filedialog.askopenfilename(
			title="Select a carrier PNG", filetypes=(("PNG images", ("*.png", "*.PNG")),)
		)
		if not selected:
			return
		self.encode_source = None
		self.encode_source_path = None
		self.encoded_image = None
		self.save_button.configure(state="disabled")
		self.encode_preview.configure(image="", text="PNG\npreview")
		self.encode_photo = None
		self.encode_info.configure(text="No image selected")
		try:
			self.encode_source = load_png_image(selected)
			self.encode_source_path = Path(selected).resolve()
			self.encoded_image = None
			self.save_button.configure(state="disabled")
			self._set_preview(self.encode_source, self.encode_preview, self.encode_info, encode=True)
			self.status.set("Carrier PNG loaded. Enter a message to continue.")
		except (OSError, ValueError) as exc:
			messagebox.showerror("Could not load image", str(exc), parent=self.root)
			self.status.set("Image could not be loaded.")

	def _encode(self) -> None:
		if self.encode_source is None:
			messagebox.showerror("No image selected", "Choose a carrier PNG first.", parent=self.root)
			return
		try:
			self.encoded_image = encode_message(self.encode_source, self.message_input.get("1.0", "end-1c"))
			self.save_button.configure(state="normal")
			self.status.set("Message encoded. Save the new PNG to finish.")
			messagebox.showinfo("Encoding complete", "The message is ready to save as a new PNG.", parent=self.root)
		except (UnicodeError, ValueError) as exc:
			messagebox.showerror("Could not encode message", str(exc), parent=self.root)
			self.status.set("Encoding failed.")

	def _save_encoded(self) -> None:
		if self.encoded_image is None or self.encode_source_path is None:
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
			self.status.set(f"Encoded image saved to {destination.name}.")
			messagebox.showinfo("Image saved", f"Saved encoded PNG:\n{destination}", parent=self.root)
		except FileExistsError as exc:
			messagebox.showerror("Existing file protected", str(exc), parent=self.root)
			self.status.set("Choose a new file name; existing files are not replaced.")
		except ValueError as exc:
			messagebox.showerror("Invalid save location", str(exc), parent=self.root)
			self.status.set("Choose a different PNG destination.")
		except OSError as exc:
			messagebox.showerror("Could not save image", str(exc), parent=self.root)
			self.status.set("Saving failed.")

	def _browse_decode_image(self) -> None:
		selected = filedialog.askopenfilename(
			title="Select an encoded PNG", filetypes=(("PNG images", ("*.png", "*.PNG")),)
		)
		if not selected:
			return
		self.decode_source = None
		self.decode_preview.configure(image="", text="PNG\npreview")
		self.decode_photo = None
		self.decode_info.configure(text="No image selected")
		self.decoded_output.configure(state="normal")
		self.decoded_output.delete("1.0", "end")
		self.decoded_output.configure(state="disabled")
		try:
			self.decode_source = load_png_image(selected)
			self._set_preview(self.decode_source, self.decode_preview, self.decode_info, encode=False)
			self.status.set("PNG loaded. Decode it to inspect the message.")
		except (OSError, ValueError) as exc:
			messagebox.showerror("Could not load image", str(exc), parent=self.root)
			self.status.set("Image could not be loaded.")

	def _decode(self) -> None:
		if self.decode_source is None:
			messagebox.showerror("No image selected", "Choose an encoded PNG first.", parent=self.root)
			return
		try:
			message = decode_message(self.decode_source)
			self.decoded_output.configure(state="normal")
			self.decoded_output.delete("1.0", "end")
			self.decoded_output.insert("1.0", message)
			self.decoded_output.configure(state="disabled")
			self.status.set("Message recovered successfully.")
			messagebox.showinfo("Decoding complete", "The message was recovered.", parent=self.root)
		except ValueError as exc:
			messagebox.showerror("Could not decode message", str(exc), parent=self.root)
			self.status.set("No readable message was found.")


def main() -> None:
	root = tk.Tk()
	SteganographyApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()
