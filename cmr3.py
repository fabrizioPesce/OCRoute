import re
import cv2
import fitz
import tempfile
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from paddleocr import PaddleOCR
from pdf2image import convert_from_path
from reportlab.pdfgen import canvas
from PIL import Image, ImageTk

ocr = PaddleOCR(use_angle_cls=True, lang='it')

def extract_numbers(text):
    return re.findall(r'\b\d{10}\b', text)

def preprocess_image(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image = cv2.bilateralFilter(image, 9, 75, 75)
    image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 31, 2)
    return image

def save_image_as_pdf(image_path, output_path):
    c = canvas.Canvas(output_path)
    c.drawImage(image_path, 0, 0, width=595, height=842)
    c.save()

def image_to_pdf_with_names(image_path, output_dir):
    processed_image = preprocess_image(image_path)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    cv2.imwrite(temp_file.name, processed_image)

    result = ocr.ocr(temp_file.name, cls=True)
    text = " ".join([line[1][0] for line in result[0]])
    numbers = extract_numbers(text)

    if not numbers:
        print(f"Nessun numero trovato in {image_path}")
        return

    review_window(numbers, image_path, output_dir)

def pdf_to_images(pdf_path):
    return convert_from_path(pdf_path)

def process_file():
    filepath = filedialog.askopenfilename(filetypes=[("PDF and Images", "*.pdf *.jpg *.jpeg *.png")])
    if not filepath:
        return

    output_dir = filedialog.askdirectory()
    if not output_dir:
        return

    try:
        if filepath.lower().endswith(".pdf"):
            images = pdf_to_images(filepath)
            for i, img in enumerate(images):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                    img.save(temp_img.name)
                    image_to_pdf_with_names(temp_img.name, output_dir)
        else:
            image_to_pdf_with_names(filepath, output_dir)

    except Exception as e:
        messagebox.showerror("Errore", str(e))

def review_window(numbers, image_path, output_dir):
    review_win = tk.Toplevel(root)
    review_win.title("Revisione Codici CMR")
    review_win.geometry("900x600")

    scroll_frame = tk.Frame(review_win)
    scroll_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

    canvas_scroll = tk.Canvas(scroll_frame)
    scrollbar = tk.Scrollbar(scroll_frame, orient="vertical", command=canvas_scroll.yview)
    scrollable_frame = tk.Frame(canvas_scroll)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
    )

    canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas_scroll.configure(yscrollcommand=scrollbar.set)

    canvas_scroll.pack(side="left", fill="y", expand=True)
    scrollbar.pack(side="right", fill="y")

    canvas_frame = tk.Frame(review_win)
    canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    zoom_controls = tk.Frame(canvas_frame)
    zoom_controls.pack(side=tk.TOP, pady=5)

    canvas = tk.Canvas(canvas_frame, bg='white')
    canvas.pack(fill=tk.BOTH, expand=True)

    zoom_in_btn = tk.Button(zoom_controls, text="Zoom +", command=lambda: zoom_with_button(1.1))
    zoom_in_btn.pack(side=tk.LEFT, padx=5)

    zoom_out_btn = tk.Button(zoom_controls, text="Zoom -", command=lambda: zoom_with_button(0.9))
    zoom_out_btn.pack(side=tk.LEFT, padx=5)

    doc = fitz.open(image_path)
    page = doc.load_page(0)
    pix = page.get_pixmap()
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    scale_factor = 1.0
    img_tk = None
    image_id = None

    def update_canvas_image():
        nonlocal img_tk, image_id, scale_factor
        resized_img = img.resize((int(img.width * scale_factor), int(img.height * scale_factor)), Image.LANCZOS)
        img_tk = ImageTk.PhotoImage(resized_img)
        if image_id is not None:
            canvas.delete(image_id)
        image_id = canvas.create_image(0, 0, anchor=tk.NW, image=img_tk)
        canvas.configure(scrollregion=canvas.bbox("all"))

    def zoom_with_mouse(event):
        nonlocal scale_factor
        factor = 1.1 if event.delta > 0 else 0.9
        scale_factor *= factor
        update_canvas_image()

    def zoom_with_button(factor):
        nonlocal scale_factor
        scale_factor *= factor
        update_canvas_image()

    def start_pan(event):
        canvas.scan_mark(event.x, event.y)

    def do_pan(event):
        canvas.scan_dragto(event.x, event.y, gain=1)

    canvas.bind("<MouseWheel>", zoom_with_mouse)
    canvas.bind("<ButtonPress-1>", start_pan)
    canvas.bind("<B1-Motion>", do_pan)

    update_canvas_image()

    entries = []
    for number in numbers:
        label = tk.Label(scrollable_frame, text="Codice CMR:")
        label.pack()
        entry = tk.Entry(scrollable_frame)
        entry.insert(0, number)
        entry.pack()
        entries.append(entry)

    def confirm():
        for entry in entries:
            number = entry.get()
            output_pdf = os.path.join(output_dir, f"{number}.pdf")
            save_image_as_pdf(image_path, output_pdf)
        review_win.destroy()
        if image_path.startswith("/tmp/"):
            try:
                os.remove(image_path)
            except FileNotFoundError:
                pass
        messagebox.showinfo("Successo", "PDF creati con successo!")

    def cancel():
        review_win.destroy()

    confirm_btn = tk.Button(scrollable_frame, text="Conferma", command=confirm)
    confirm_btn.pack(side=tk.LEFT, padx=10, pady=10)

    cancel_btn = tk.Button(scrollable_frame, text="Annulla", command=cancel)
    cancel_btn.pack(side=tk.RIGHT, padx=10, pady=10)

# GUI principale
root = tk.Tk()
root.title("Estrai Codici e Crea PDF")
root.geometry("400x200")

label = tk.Label(root, text="Seleziona un file JPG/PNG o PDF da elaborare", pady=20)
label.pack()

btn = tk.Button(root, text="Scegli File", command=process_file, width=20)
btn.pack(pady=10)

root.mainloop()
