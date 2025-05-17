import os
import re
import cv2
import fitz
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
from paddleocr import PaddleOCR
from PIL import Image, ImageTk, ImageDraw
import numpy as np
import io
from collections import OrderedDict

# ---- UTILS ---- #

ocr = PaddleOCR(
    use_angle_cls=True,
    det_model_dir="_internal/.paddleocr/whl/det/en/en_PP-OCRv3_det_infer",
    rec_model_dir="_internal/.paddleocr/whl/rec/latin/latin_PP-OCRv3_rec_infer",
    cls_model_dir="_internal/.paddleocr/whl/cls/ch_ppocr_mobile_v2.0_cls_infer"
)
print(f"Model dir: {ocr.args.det_model_dir}")

def extract_numbers(text):
    return re.findall(r'\b\d{10}\b', text)

def preprocess_image(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image = cv2.bilateralFilter(image, 9, 75, 75)
    image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    return image

def save_image_as_pdf_pil(image_path, output_path):
    image = Image.open(image_path).convert("RGB")
    image = image.resize((595, 842), Image.LANCZOS)
    image.save(output_path, "PDF", resolution=100.0)

def pdf_to_images(pdf_path, zoom_factor=3):  # zoom 3 ≈ 300 DPI
    images = []
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(zoom_factor, zoom_factor)
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("ppm"))).convert("RGB")
        images.append(img)
    doc.close()
    return images

def crop_to_roi(image: Image.Image, x_perc=(0.00, 1.00), y_perc=(0.30, 0.85)):
    width, height = image.size
    x1 = int(width * x_perc[0])
    x2 = int(width * x_perc[1])
    y1 = int(height * y_perc[0])
    y2 = int(height * y_perc[1])
    return image.crop((x1, y1, x2, y2))

def image_to_numbers(image_path):
    image = Image.open(image_path)
    cropped = crop_to_roi(image)
    
    # Preprocessing
    image_np = cv2.cvtColor(np.array(cropped), cv2.COLOR_RGB2GRAY)
    image_np = cv2.resize(image_np, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image_np = cv2.bilateralFilter(image_np, 9, 75, 75)
    image_np = cv2.adaptiveThreshold(image_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    
    # OCR con gestione file temporaneo
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
        cv2.imwrite(temp_file.name, image_np)
        result = ocr.ocr(temp_file.name, cls=True)
    
    os.remove(temp_file.name)
    
    # Estrazione numeri con confidenza
    numbers_with_conf = []
    for line in result[0]:
        if not line or len(line) < 2:  # Controllo sicurezza
            continue
            
        text_entry = line[1]
        if not text_entry or len(text_entry) < 2:  # Ulteriore controllo
            continue
            
        text, conf = text_entry[0], text_entry[1]
        found_numbers = extract_numbers(text)
        
        for num in found_numbers:
            numbers_with_conf.append((num, float(conf)))  # Converti esplicitamente a float
    
    return numbers_with_conf

# ---- PROCESSOR CLASS ---- #

class PDFProcessor:
    def __init__(self, root):
        self.root = root
        self.folderpath = ""
        self.output_dir = ""
        self.pdf_files = []
        self.all_numbers = OrderedDict()

    def run(self):
        self.select_folders()
        if self.folderpath and self.output_dir:
            self.process_pdfs()
            self.process_next_pdf()

    def select_folders(self):
        self.folderpath = filedialog.askdirectory(title="Seleziona una cartella contenente PDF")
        if not self.folderpath: return

        self.output_dir = filedialog.askdirectory(title="Seleziona la cartella di output")
        if not self.output_dir: return

        # Ordina alfabeticamente i PDF
        self.pdf_files = sorted(
            [f for f in os.listdir(self.folderpath) if f.lower().endswith(".pdf")],
            key=lambda x: x.lower()
        )
    def process_pdfs(self):
        for filename in self.pdf_files:
            pdf_path = os.path.join(self.folderpath, filename)
            images = pdf_to_images(pdf_path)
            if images:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                    images[0].save(temp_img.name)
                    numbers_with_conf = image_to_numbers(temp_img.name)  # Ora restituisce (num, conf)
                    if numbers_with_conf:
                        self.all_numbers[filename] = (numbers_with_conf, temp_img.name)

    def process_next_pdf(self):
        if not self.all_numbers:
            messagebox.showinfo("Completato", "Tutti i PDF sono stati elaborati.")
            return

        # Prendi il PRIMO elemento invece dell'ultimo
        filename = next(iter(self.all_numbers))
        numbers, image_path = self.all_numbers[filename]
        del self.all_numbers[filename]
        
        ReviewWindow(self.root, numbers, image_path, 
                    os.path.join(self.output_dir, os.path.splitext(filename)[0]), 
                    filename, self.process_next_pdf)
# ---- REVIEW WINDOW CLASS ---- #

class ReviewWindow:
    def __init__(self, root, numbers_with_conf, image_path, output_dir, pdf_filename, callback):
        self.root = root
        self.numbers_with_conf = numbers_with_conf
        self.image_path = image_path
        self.output_dir = output_dir
        self.pdf_filename = pdf_filename
        self.callback = callback
        self.scale_factor = 1.0
        self.entries = []
        self.confidence_threshold = 0.7
        self.img_tk = None
        self.image_id = None
        self.build_window()

    def build_window(self):
        self.win = tk.Toplevel(self.root)
        self.win.title(f"Revisione CMR - {self.pdf_filename}")
        self.win.geometry("1000x700")

        # Frames
        left_frame = tk.Frame(self.win)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        right_frame = tk.Frame(self.win)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Scrollable Frame (Entries)
        canvas_scroll = tk.Canvas(left_frame)
        scrollbar = tk.Scrollbar(left_frame, orient="vertical", command=canvas_scroll.yview)
        scrollable_frame = tk.Frame(canvas_scroll)

        scrollable_frame.bind("<Configure>", lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all")))
        canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        #Entries frame
        entries_frame = tk.Frame(scrollable_frame)
        entries_frame.pack(fill=tk.X, pady=10)

        # Canvas for image
        controls_frame = tk.Frame(right_frame)
        controls_frame.pack(side=tk.TOP, pady=5)

        self.canvas = tk.Canvas(right_frame, bg='white')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        tk.Button(controls_frame, text="Zoom +", command=lambda: self.zoom_with_button(1.1)).pack(side=tk.LEFT, padx=5)
        tk.Button(controls_frame, text="Zoom -", command=lambda: self.zoom_with_button(0.9)).pack(side=tk.LEFT, padx=5)

        # Load image directly via PIL
        numbers_to_highlight = [num for num, conf in self.numbers_with_conf]
        self.img = self.load_and_highlight_image(self.image_path, numbers_to_highlight)
        self.update_canvas_image()

        # Bindings
        self.canvas.bind("<MouseWheel>", self.zoom_with_mouse)
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)

        # Entries for CMR codes
        for number, confidence in self.numbers_with_conf:
            self.add_entry(entries_frame, number, confidence)

        # Aggiungi Codice Button
        add_entry_btn = tk.Button(scrollable_frame, text="Aggiungi Codice", command=lambda: self.add_entry(entries_frame))
        add_entry_btn.pack(pady=10)

        # Frame per Conferma e Annulla
        buttons_frame = tk.Frame(scrollable_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        tk.Button(buttons_frame, text="Conferma", command=self.confirm).pack(side=tk.LEFT, padx=10)
        tk.Button(buttons_frame, text="Annulla", command=self.cancel).pack(side=tk.RIGHT, padx=10)

    def load_and_highlight_image(self, image_path, numbers_to_highlight):
        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        # Rilevamento OCR
        result = ocr.ocr(image_path, cls=True)[0]

        for line in result:
            if not line:
                continue
            bbox, (text, conf) = line[0], line[1]
            
            if any(num in text for num in numbers_to_highlight):
                bbox = [(int(p[0]), int(p[1])) for p in bbox]
                draw.polygon(bbox, outline="red", width=3)

        return image

    # Image controls
    def update_canvas_image(self):
        resized_img = self.img.resize((int(self.img.width * self.scale_factor), int(self.img.height * self.scale_factor)), Image.LANCZOS)
        self.img_tk = ImageTk.PhotoImage(resized_img)
        if self.image_id:
            self.canvas.delete(self.image_id)
        self.image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def zoom_with_mouse(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self.scale_factor = min(max(self.scale_factor * factor, 0.1), 10)
        self.update_canvas_image()

    def zoom_with_button(self, factor):
        self.scale_factor = min(max(self.scale_factor * factor, 0.1), 10)
        self.update_canvas_image()

    def start_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def do_pan(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    # Entry management
    def add_entry(self, parent, number="", confidence=1.0):
        frame = tk.Frame(parent, bg=self.get_bg_color(confidence))
        frame.pack(fill=tk.X, pady=2)

        tk.Label(frame, text="Codice CMR:", bg=self.get_bg_color(confidence)).pack(side=tk.LEFT)
        entry = tk.Entry(frame)
        entry.insert(0, number)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Aggiungi tooltip con la confidenza
        self.add_tooltip(frame, f"Confidenza OCR: {confidence:.2f}")

        tk.Button(frame, text="X", command=lambda: self.remove_entry(frame)).pack(side=tk.RIGHT)
        self.entries.append((frame, confidence))
    
    def get_bg_color(self, confidence):
        return "#ffcccc" if confidence < self.confidence_threshold else "#ffffff"

    def add_tooltip(self, widget, text):
        tooltip = tk.Toplevel(self.win)
        tooltip.withdraw()
        tooltip.overrideredirect(True)

        label = tk.Label(tooltip, text=text, bg="lightyellow", relief="solid", borderwidth=1)
        label.pack()

        def enter(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            tooltip.geometry(f"+{x}+{y}")
            tooltip.deiconify()

        def leave(event):
            tooltip.withdraw()

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def remove_entry(self, frame):
        self.entries.remove(frame)
        frame.destroy()

    # Confirm & Cancel
    def confirm(self):
        os.makedirs(self.output_dir, exist_ok=True)
        for frame in self.entries:
            entry = frame.winfo_children()[1]
            number = entry.get()
            if number.strip():
                output_pdf = os.path.join(self.output_dir, f"{number}.pdf")
                save_image_as_pdf_pil(self.image_path, output_pdf)

        self.cleanup_and_next()

    def cancel(self):
        self.cleanup_and_next()

    def cleanup_and_next(self):
        self.win.destroy()
        try:
            os.remove(self.image_path)
        except FileNotFoundError:
            pass
        self.callback()

# ---- MAIN ---- #

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Estrai Codici e Crea PDF")
    root.geometry("400x200")

    tk.Label(root, text="Seleziona una cartella contenente PDF da elaborare", pady=20).pack()
    tk.Button(root, text="Scegli Cartella", command=lambda: PDFProcessor(root).run(), width=20).pack(pady=10)

    root.mainloop()
