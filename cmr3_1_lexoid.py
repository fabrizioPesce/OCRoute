import os
import re
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from datetime import datetime, timedelta
import json
import sys
import requests
import uuid
from typing import List, Dict, Callable
import pypdfium2
import time
from lexoid.api import parse
from paddleocr import PaddleOCR

# ---- CONSTANTS ----
CONFIG_FILE = os.path.join(os.path.abspath("."), "config.json")
LICENSE_FILE = os.path.join(os.path.abspath("."), "license.json")
VALIDATION_URL = "http://fabriziopesce.atwebpages.com/validate_licenses.php"

# ---- UTILITIES ----
def resource_path(relative_path: str) -> str:
    """Get absolute path to resource"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def save_config(source: str, output: str) -> None:
    """Save folder configuration"""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"source_folder": source, "output_folder": output}, f)

def load_config() -> Dict[str, str]:
    """Load folder configuration"""
    return json.load(open(CONFIG_FILE)) if os.path.exists(CONFIG_FILE) else {"source_folder": "", "output_folder": ""}

def extract_cmr_codes(text: str) -> List[str]:
    """Improved CMR code extraction with validation"""
    codes = re.findall(r'\b(?:CMR)?(\d{10})\b', text.upper())
    return [code[-10:] for code in codes if len(code) >= 10]

def pdf_to_images(pdf_path: str) -> List[Image.Image]:
    """Convert PDF to images using pypdfium2"""
    pdf = pypdfium2.PdfDocument(pdf_path)
    images = []
    for page in pdf:
        bitmap = page.render(scale=3.0)
        images.append(bitmap.to_pil().convert("RGB"))
        page.close()
        bitmap.close()
    pdf.close()
    return images

def enhance_image(image: Image.Image) -> np.ndarray:
    """Image preprocessing for OCR"""
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.medianBlur(enhanced, 3)

def safe_remove_file(file_path: str) -> None:
    """Safely remove files"""
    for _ in range(5):
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                break
        except Exception:
            time.sleep(0.1)

# ---- OCR PROCESSOR ----
class CombinedOCR:
    """Combined OCR processor using Lexoid and PaddleOCR"""
    def __init__(self):
        self.lexoid_enabled = True
        self.paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang='it',
            det_limit_type='max',
            rec_image_shape="3,48,320",
            drop_score=0.4
        )

    def process_pdf(self, pdf_path: str) -> List[str]:
        """Process PDF with combined OCR engines"""
        codes = set()
        
        try:
            # Lexoid processing
            if self.lexoid_enabled:
                lex_result = parse(pdf_path, parser_type="STATIC_PARSE")
                codes.update(extract_cmr_codes(lex_result.get("text", "")))
        except Exception as e:
            print(f"Lexoid error: {str(e)}")
            self.lexoid_enabled = False

        # PaddleOCR processing
        try:
            images = pdf_to_images(pdf_path)
            for img in images:
                enhanced = enhance_image(img)
                result = self.paddle_ocr.ocr(enhanced, cls=True)
                for line in result:
                    text = " ".join(word_info[-1][0] for word_info in line)
                    codes.update(extract_cmr_codes(text))
        except Exception as e:
            print(f"PaddleOCR error: {str(e)}")

        return sorted(list(codes), key=lambda x: x[-10:])

# ---- INTERFACE CLASSES ----
class PDFProcessorApp:
    """Main application class"""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.ocr = CombinedOCR()
        self.setup_ui()

    def setup_ui(self) -> None:
        """Initialize user interface"""
        self.root.title("CMR Code Extractor Pro")
        self.root.geometry("500x300")
        
        config = load_config()
        self.source_var = tk.StringVar(value=config["source_folder"])
        self.output_var = tk.StringVar(value=config["output_folder"])

        # UI components
        tk.Label(self.root, text="PDF Folder:").pack(pady=5)
        tk.Entry(self.root, textvariable=self.source_var, width=50).pack()
        tk.Button(self.root, text="Browse...", command=self.choose_source).pack(pady=5)

        tk.Label(self.root, text="Output Folder:").pack(pady=5)
        tk.Entry(self.root, textvariable=self.output_var, width=50).pack()
        tk.Button(self.root, text="Browse...", command=self.choose_output).pack(pady=5)

        tk.Button(self.root, text="Process Documents", command=self.start_processing,
                 bg="#4CAF50", fg="white").pack(pady=20)
        
        self.progress_label = tk.Label(self.root, text="Ready")
        self.progress_label.pack()

        # Set icon
        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

    def choose_source(self) -> None:
        """Select source folder"""
        if folder := filedialog.askdirectory():
            self.source_var.set(folder)

    def choose_output(self) -> None:
        """Select output folder"""
        if folder := filedialog.askdirectory():
            self.output_var.set(folder)

    def start_processing(self) -> None:
        """Start processing workflow"""
        source = self.source_var.get()
        output = self.output_var.get()
        
        if not all([source, output]):
            messagebox.showwarning("Error", "Please select both folders")
            return
        
        save_config(source, output)
        processor = PDFProcessor(
            self.root,
            self.ocr,
            source,
            output,
            self.update_progress
        )
        processor.process()

    def update_progress(self, current: int, total: int) -> None:
        """Update progress display"""
        self.progress_label.config(text=f"Processed: {current}/{total}")

class PDFProcessor:
    """Document processing handler"""
    def __init__(self, root: tk.Tk, ocr: CombinedOCR, 
                 source: str, output: str, update_callback: Callable):
        self.root = root
        self.ocr = ocr
        self.source = source
        self.output = output
        self.update = update_callback
        self.files = [f for f in os.listdir(source) if f.lower().endswith(".pdf")]
        self.results = {}

    def process(self) -> None:
        """Process all PDF files"""
        total = len(self.files)
        for idx, filename in enumerate(self.files, 1):
            pdf_path = os.path.join(self.source, filename)
            temp_img = None
            
            try:
                # OCR processing
                codes = self.ocr.process_pdf(pdf_path)
                
                # Create preview
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    images = pdf_to_images(pdf_path)
                    if images:
                        images[0].save(f.name)
                        temp_img = f.name
                
                self.results[filename] = (codes, temp_img)
                self.update(idx, total)
                
            except Exception as e:
                messagebox.showerror("Processing Error", 
                                   f"Error processing {filename}:\n{str(e)}")
                if temp_img:
                    safe_remove_file(temp_img)
        
        self.show_reviews()

    def show_reviews(self) -> None:
        """Show review windows sequentially"""
        if not self.results:
            messagebox.showinfo("Completato", "Nessun documento elaborato.")
            return

        for filename, (codes, img_path) in self.results.items():
            if img_path and os.path.exists(img_path):
                window = ReviewWindow(
                    self.root,
                    codes,
                    img_path,
                    os.path.join(self.output, os.path.splitext(filename)[0]),
                    filename
                )
                self.root.wait_window(window)

class ReviewWindow(tk.Toplevel):
    """Review window for validation with editing features"""
    def __init__(self, parent: tk.Tk, codes: List[str], 
                 img_path: str, output_dir: str, filename: str):
        super().__init__(parent)
        self.title(f"Review - {filename}")
        self.geometry("1000x700")
        
        self.codes = codes
        self.img_path = img_path
        self.output_dir = output_dir
        self.scale = 1.0
        
        self.create_widgets()
        self.load_image()
        self.transient(parent)
        self.grab_set()  # Modal behavior

    def create_widgets(self) -> None:
        """Create UI components"""
        # Left panel
        left_frame = tk.Frame(self)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Code list
        self.listbox = tk.Listbox(left_frame, width=30, height=20, font=('Arial', 12))
        self.listbox.pack(pady=5)
        for code in self.codes:
            self.listbox.insert(tk.END, code)

        # Entry for adding
        self.new_code_var = tk.StringVar()
        tk.Entry(left_frame, textvariable=self.new_code_var).pack(pady=5)

        # Buttons
        btn_frame = tk.Frame(left_frame)
        btn_frame.pack(pady=5)

        tk.Button(btn_frame, text="Aggiungi", command=self.add_code).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Rimuovi Selezionato", command=self.remove_selected).pack(side=tk.RIGHT, padx=2)

        # Canvas for image
        self.canvas = tk.Canvas(self, bg='white')
        self.canvas.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        # Confirm / Cancel
        ctrl_frame = tk.Frame(left_frame)
        ctrl_frame.pack(pady=10)
        tk.Button(ctrl_frame, text="Conferma", command=self.confirm).pack(side=tk.LEFT, padx=5)
        tk.Button(ctrl_frame, text="Annulla", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def add_code(self) -> None:
        """Add code from input"""
        code = self.new_code_var.get().strip()
        if code and code not in self.listbox.get(0, tk.END):
            self.listbox.insert(tk.END, code)
            self.new_code_var.set("")

    def remove_selected(self) -> None:
        """Remove selected code"""
        selected = self.listbox.curselection()
        for index in reversed(selected):
            self.listbox.delete(index)

    def load_image(self) -> None:
        try:
            self.original_image = Image.open(self.img_path)
            self.update_image()
            self.canvas.bind("<MouseWheel>", self.zoom_image)
            self.canvas.bind("<Button-1>", self.start_pan)
            self.canvas.bind("<B1-Motion>", self.do_pan)
        except Exception as e:
            messagebox.showerror("Image Error", f"Cannot load preview: {str(e)}")
            self.destroy()

    def update_image(self) -> None:
        width = int(self.original_image.width * self.scale)
        height = int(self.original_image.height * self.scale)
        resized = self.original_image.resize((width, height), Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))

    def zoom_image(self, event) -> None:
        self.scale *= 1.1 if event.delta > 0 else 0.9
        self.scale = max(0.1, min(self.scale, 5.0))
        self.update_image()

    def start_pan(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def do_pan(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def confirm(self) -> None:
        selected_codes = list(self.listbox.get(0, tk.END))
        if not selected_codes:
            messagebox.showwarning("Nessun codice", "Nessun codice selezionato o inserito.")
            return

        try:
            os.makedirs(self.output_dir, exist_ok=True)
            img = Image.open(self.img_path)
            for code in selected_codes:
                output_path = os.path.join(
                    self.output_dir,
                    f"CMR_{code}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                )
                img.save(output_path, "PDF", resolution=100.0)

            messagebox.showinfo("Successo", f"Salvati {len(selected_codes)} file")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Errore Salvataggio", str(e))

    def destroy(self) -> None:
        safe_remove_file(self.img_path)
        super().destroy()


# ---- LICENSE MANAGEMENT ----
class LicenseManager:
    """Handles license validation and management"""
    @staticmethod
    def is_valid() -> bool:
        """Check if license is valid and not expired"""
        if not os.path.exists(LICENSE_FILE):
            return False

        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)

        expires_on = datetime.fromisoformat(data.get("expires_on"))
        return expires_on >= datetime.now()

    @staticmethod
    def validate_license(code: str) -> bool:
        """Validate license with server"""
        try:
            machine_id = str(uuid.uuid4())
            response = requests.post(
                VALIDATION_URL,
                data={"code": code, "uuid": machine_id},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            result = response.json()

            if result.get("valid"):
                activation = datetime.now()
                expiration_date = activation + timedelta(days=result.get("valid_days", 365))
                license_data = {
                    "code": code,
                    "uuid": machine_id,
                    "activation_date": activation.isoformat(),
                    "expires_on": expiration_date.isoformat()
                }
                with open(LICENSE_FILE, "w") as f:
                    json.dump(license_data, f)
                return True
            return False
        except Exception:
            return False


# ---- MAIN ----
def main():
    """Application entry point"""
    root = tk.Tk()
    root.withdraw()

    # License check
    if not LicenseManager.is_valid():
        # License validation logic here
        pass

    root.deiconify()
    PDFProcessorApp(root).root.mainloop()

if __name__ == "__main__":
    main()