import os
import re
import cv2
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
from paddleocr import PaddleOCR
from PIL import Image, ImageTk
import numpy as np
from datetime import datetime, timedelta
import json
import sys
import requests
import uuid
from pdf2image import convert_from_path
from typing import List, Tuple, Dict, Optional, Callable

# ---- CONSTANTS ----
CONFIG_FILE = os.path.join(os.path.abspath("."), "config.json")
LICENSE_FILE = os.path.join(os.path.abspath("."), "license.json")
VALIDATION_URL = "http://fabriziopesce.atwebpages.com/validate_licenses.php"
POPPLER_PATH = os.path.join(os.path.abspath("."), "poppler-24.08.0", "Library", "bin")

# ---- UTILS ----
def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def save_config(source: str, output: str) -> None:
    """Save source and output folders to config file"""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"source_folder": source, "output_folder": output}, f)

def load_config() -> Dict[str, str]:
    """Load config from file or return empty dict"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"source_folder": "", "output_folder": ""}

def extract_numbers(text: str) -> List[str]:
    """Extract 10-digit numbers from text"""
    return re.findall(r'\b\d{10}\b', text)

def preprocess_image(image_path: str) -> np.ndarray:
    """Preprocess image for OCR"""
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image = cv2.bilateralFilter(image, 9, 75, 75)
    return cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                               cv2.THRESH_BINARY, 31, 2)

def save_image_as_pdf(image_path: str, output_path: str) -> None:
    """Save image as PDF with standard size"""
    image = Image.open(image_path).convert("RGB")
    image = image.resize((595, 842), Image.LANCZOS)
    image.save(output_path, "PDF", resolution=100.0)

def pdf_to_images(pdf_path: str, dpi: int = 400) -> List[Image.Image]:
    """Convert PDF to list of PIL images"""
    return convert_from_path(pdf_path, dpi=dpi, poppler_path=POPPLER_PATH)

def crop_to_roi(image: Image.Image, 
               x_perc: Tuple[float, float] = (0.00, 1.00), 
               y_perc: Tuple[float, float] = (0.30, 0.85)) -> Image.Image:
    """Crop image to region of interest"""
    width, height = image.size
    x1 = int(width * x_perc[0])
    x2 = int(width * x_perc[1])
    y1 = int(height * y_perc[0])
    y2 = int(height * y_perc[1])
    return image.crop((x1, y1, x2, y2))

class OCRProcessor:
    """Handles OCR operations with caching"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.ocr = PaddleOCR(use_angle_cls=True, lang='it')
        return cls._instance
    
    def image_to_numbers(self, image_path: str) -> List[str]:
        """Extract numbers from image using OCR"""
        image = Image.open(image_path)
        cropped = crop_to_roi(image)
        
        # Preprocess image
        image_np = cv2.cvtColor(np.array(cropped), cv2.COLOR_RGB2GRAY)
        image_np = cv2.resize(image_np, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        image_np = cv2.bilateralFilter(image_np, 9, 75, 75)
        image_np = cv2.adaptiveThreshold(image_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 31, 2)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            cv2.imwrite(temp_file.name, image_np)
            result = self.ocr.ocr(temp_file.name, cls=True)
        os.remove(temp_file.name)
        
        text = " ".join([line[1][0] for line in result[0]])
        return extract_numbers(text)

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

# ---- MAIN APPLICATION ----
class PDFProcessorApp:
    """Main application class"""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.setup_ui()
        self.ocr_processor = OCRProcessor()
        
    def setup_ui(self) -> None:
        """Setup the main user interface"""
        self.root.title("Estrai Codici e Crea PDF")
        self.root.geometry("500x300")
        
        config = load_config()
        
        # Source folder selection
        tk.Label(self.root, text="Cartella PDF:").pack(pady=5)
        self.source_var = tk.StringVar(value=config["source_folder"])
        tk.Entry(self.root, textvariable=self.source_var, width=50).pack()
        tk.Button(self.root, text="Scegli Cartella PDF", 
                 command=self.choose_source_folder).pack(pady=5)
        
        # Output folder selection
        tk.Label(self.root, text="Cartella Output:").pack(pady=5)
        self.output_var = tk.StringVar(value=config["output_folder"])
        tk.Entry(self.root, textvariable=self.output_var, width=50).pack()
        tk.Button(self.root, text="Scegli Cartella Output", 
                 command=self.choose_output_folder).pack(pady=5)
        
        # Process button
        tk.Button(self.root, text="Conferma ed Elabora", 
                 command=self.start_processing, width=30).pack(pady=20)
        
        # Progress label
        self.progress_label = tk.Label(self.root, text="", fg="blue")
        self.progress_label.pack()
        
        # Set icon
        icon_path = resource_path("ocroute_icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)
    
    def choose_source_folder(self) -> None:
        """Select source folder dialog"""
        folder = filedialog.askdirectory(title="Seleziona cartella PDF")
        if folder:
            self.source_var.set(folder)
    
    def choose_output_folder(self) -> None:
        """Select output folder dialog"""
        folder = filedialog.askdirectory(title="Seleziona cartella Output")
        if folder:
            self.output_var.set(folder)
    
    def start_processing(self) -> None:
        """Start processing PDF files"""
        source = self.source_var.get()
        output = self.output_var.get()
        
        if not source or not output:
            messagebox.showwarning("Attenzione", "Seleziona entrambe le cartelle.")
            return
            
        save_config(source, output)
        processor = PDFProcessor(self.root, self.progress_label, self.ocr_processor)
        processor.folderpath = source
        processor.output_dir = output
        processor.pdf_files = [f for f in os.listdir(source) if f.lower().endswith(".pdf")]
        processor.process_pdfs()
        processor.process_next_pdf()

class PDFProcessor:
    """Handles PDF processing and review workflow"""
    def __init__(self, root: tk.Tk, progress_label: tk.Label, ocr_processor: OCRProcessor):
        self.root = root
        self.progress_label = progress_label
        self.ocr_processor = ocr_processor
        self.folderpath = ""
        self.output_dir = ""
        self.pdf_files = []
        self.all_numbers = {}
        self.total_files = 0
        self.processed_files = 0
    
    def process_pdfs(self) -> None:
        """Process all PDF files in the folder"""
        self.total_files = len(self.pdf_files)
        self.processed_files = 0
        self.update_progress()
        
        for filename in self.pdf_files:
            pdf_path = os.path.join(self.folderpath, filename)
            images = pdf_to_images(pdf_path)
            
            if images:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                    images[0].save(temp_img.name)
                    numbers = self.ocr_processor.image_to_numbers(temp_img.name)
                    if numbers:
                        self.all_numbers[filename] = (numbers, temp_img.name)
            
            self.processed_files += 1
            self.update_progress()
    
    def update_progress(self) -> None:
        """Update progress label"""
        self.progress_label.config(text=f"Elaborati: {self.processed_files} / {self.total_files}")
        self.progress_label.update_idletasks()
    
    def process_next_pdf(self) -> None:
        """Process next PDF in queue or show completion message"""
        if not self.all_numbers:
            messagebox.showinfo("Completato", "Tutti i PDF sono stati elaborati.")
            return
            
        filename, (numbers, image_path) = self.all_numbers.popitem()
        ReviewWindow(self.root, numbers, image_path, 
                   os.path.join(self.output_dir, os.path.splitext(filename)[0]), 
                   filename, self.process_next_pdf)

class ReviewWindow:
    """Window for reviewing and confirming extracted codes"""
    def __init__(self, root: tk.Tk, numbers: List[str], image_path: str, 
                 output_dir: str, pdf_filename: str, callback: Callable):
        self.root = root
        self.numbers = numbers
        self.image_path = image_path
        self.output_dir = output_dir
        self.pdf_filename = pdf_filename
        self.callback = callback
        self.scale_factor = 1.0
        self.entries = []
        self.img_tk = None
        self.image_id = None
        
        self.build_window()
    
    def build_window(self) -> None:
        """Build the review window UI"""
        self.win = tk.Toplevel(self.root)
        self.win.title(f"Revisione CMR - {self.pdf_filename}")
        self.win.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}")
        
        # Frames
        left_frame = tk.Frame(self.win)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        right_frame = tk.Frame(self.win)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Scrollable entries frame
        self.setup_entries_frame(left_frame)
        
        # Image viewer with controls
        self.setup_image_viewer(right_frame)
    
    def setup_entries_frame(self, parent: tk.Frame) -> None:
        """Setup the scrollable entries frame"""
        canvas_scroll = tk.Canvas(parent)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas_scroll.yview)
        scrollable_frame = tk.Frame(canvas_scroll)

        scrollable_frame.bind("<Configure>", 
                            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all")))
        canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Count label
        self.count_label = tk.Label(scrollable_frame, text=f"Codici letti: {len(self.numbers)}")
        self.count_label.pack(pady=5)

        # Entries frame
        entries_frame = tk.Frame(scrollable_frame)
        entries_frame.pack(fill=tk.X, pady=10)

        # Add entries for each number
        for number in self.numbers:
            self.add_entry(entries_frame, number)

        # Add entry button
        tk.Button(scrollable_frame, text="Aggiungi Codice", 
                 command=lambda: self.add_entry(entries_frame)).pack(pady=10)

        # Action buttons
        buttons_frame = tk.Frame(scrollable_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        tk.Button(buttons_frame, text="Conferma", command=self.confirm).pack(side=tk.LEFT, padx=10)
        tk.Button(buttons_frame, text="Annulla", command=self.cancel).pack(side=tk.RIGHT, padx=10)
    
    def setup_image_viewer(self, parent: tk.Frame) -> None:
        """Setup the image viewer with controls"""
        controls_frame = tk.Frame(parent)
        controls_frame.pack(side=tk.TOP, pady=5)

        self.canvas = tk.Canvas(parent, bg='white')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Zoom controls
        tk.Button(controls_frame, text="Zoom +", 
                 command=lambda: self.zoom_image(1.1)).pack(side=tk.LEFT, padx=5)
        tk.Button(controls_frame, text="Zoom -", 
                 command=lambda: self.zoom_image(0.9)).pack(side=tk.LEFT, padx=5)

        # Load and display image
        self.img = Image.open(self.image_path).convert("RGB")
        self.update_canvas_image()

        # Bind mouse events
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)
    
    # Image control methods
    def update_canvas_image(self) -> None:
        """Update the canvas with current image and scale"""
        resized_img = self.img.resize(
            (int(self.img.width * self.scale_factor), 
             int(self.img.height * self.scale_factor)), 
            Image.LANCZOS
        )
        self.img_tk = ImageTk.PhotoImage(resized_img)
        
        if self.image_id:
            self.canvas.delete(self.image_id)
            
        self.image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def zoom_image(self, factor: float) -> None:
        """Zoom image by factor"""
        self.scale_factor = min(max(self.scale_factor * factor, 0.1), 10)
        self.update_canvas_image()
    
    def on_mousewheel(self, event) -> None:
        """Handle mouse wheel zoom"""
        self.zoom_image(1.1 if event.delta > 0 else 0.9)
    
    def start_pan(self, event) -> None:
        """Start panning the image"""
        self.canvas.scan_mark(event.x, event.y)
    
    def do_pan(self, event) -> None:
        """Continue panning the image"""
        self.canvas.scan_dragto(event.x, event.y, gain=1)
    
    # Entry management methods
    def add_entry(self, parent: tk.Frame, number: str = "") -> None:
        """Add a new code entry field"""
        frame = tk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)

        tk.Label(frame, text="Codice CMR:").pack(side=tk.LEFT)
        entry = tk.Entry(frame)
        entry.insert(0, number)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(frame, text="X", command=lambda: self.remove_entry(frame)).pack(side=tk.RIGHT)
        self.entries.append(frame)
        self.update_count_label()
    
    def remove_entry(self, frame: tk.Frame) -> None:
        """Remove a code entry field"""
        self.entries.remove(frame)
        frame.destroy()
        self.update_count_label()
    
    def update_count_label(self) -> None:
        """Update the count of code entries"""
        self.count_label.config(text=f"Codici letti: {len(self.entries)}")
    
    # Action methods
    def confirm(self) -> None:
        """Confirm and save the codes"""
        os.makedirs(self.output_dir, exist_ok=True)
        
        for frame in self.entries:
            entry = frame.winfo_children()[1]
            number = entry.get().strip()
            
            if number:
                output_pdf = os.path.join(
                    self.output_dir, 
                    f"POD_{number}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                )
                save_image_as_pdf(self.image_path, output_pdf)
        
        self.cleanup()
    
    def cancel(self) -> None:
        """Cancel and close the window"""
        self.cleanup()
    
    def cleanup(self) -> None:
        """Cleanup resources and call callback"""
        self.win.destroy()
        try:
            os.remove(self.image_path)
        except FileNotFoundError:
            pass
        self.callback()

def ask_license() -> bool:
    """Show license input dialog"""
    def on_submit():
        code = entry.get().strip()
        if not code:
            messagebox.showwarning("Errore", "Inserisci un codice di licenza.")
            return
            
        if LicenseManager.validate_license(code):
            top.destroy()
        else:
            messagebox.showerror("Licenza non valida", "Codice di licenza non valido o errore di connessione")

    top = tk.Toplevel()
    top.title("Inserisci codice di licenza")
    tk.Label(top, text="Inserisci il codice di licenza per attivare l'applicazione").pack(padx=10, pady=10)
    entry = tk.Entry(top, width=30)
    entry.pack(pady=5)
    tk.Button(top, text="Conferma", command=on_submit).pack(pady=10)
    top.grab_set()
    top.wait_window()
    
    return LicenseManager.is_valid()

def main():
    """Main application entry point"""
    root = tk.Tk()
    root.withdraw()  # Hide main window until license is validated

    # License check
    if not LicenseManager.is_valid():
        if not ask_license():
            messagebox.showerror("Licenza non valida", "Impossibile avviare l'app: licenza non valida o scaduta.")
            sys.exit()

    root.deiconify()  # Show main window
    app = PDFProcessorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()