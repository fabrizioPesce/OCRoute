import os
import re
import cv2
import fitz
import tempfile
import tkinter as tk
from tkcalendar import DateEntry
from tkinter import filedialog, messagebox
from tkinter import Spinbox
from paddleocr import PaddleOCR
from PIL import Image, ImageTk
import numpy as np
import io
from datetime import datetime, timedelta
import json
import sys
import requests
import uuid

def resource_path(relative_path):
    try:
        # PyInstaller crea una cartella temporanea e ci estrae i file
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS  # se congelato
    return os.path.abspath(".")

CONFIG_FILE = os.path.join(get_base_path(), "config.json")

def save_config(source, output):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"source_folder": source, "output_folder": output}, f)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"source_folder": "", "output_folder": ""}

# ---- UTILS ---- #

ocr = PaddleOCR(use_angle_cls=True, lang='it')
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
    
    # Converti in numpy e preprocessa
    image_np = cv2.cvtColor(np.array(cropped), cv2.COLOR_RGB2GRAY)
    image_np = cv2.resize(image_np, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image_np = cv2.bilateralFilter(image_np, 9, 75, 75)
    image_np = cv2.adaptiveThreshold(image_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
        cv2.imwrite(temp_file.name, image_np)
        result = ocr.ocr(temp_file.name, cls=True)
    os.remove(temp_file.name)
    
    text = " ".join([line[1][0] for line in result[0]])
    numbers = extract_numbers(text)
    return numbers

# ---- PROCESSOR CLASS ---- #

class PDFProcessor:
    def __init__(self, root, progress_label):
        self.root = root
        self.progress_label = progress_label
        self.folderpath = ""
        self.output_dir = ""
        self.pdf_files = []
        self.all_numbers = {}
        self.total_files = 0
        self.processed_files = 0

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

        self.pdf_files = [f for f in os.listdir(self.folderpath) if f.lower().endswith(".pdf")]

    def process_pdfs(self):
        self.total_files = len(self.pdf_files)
        self.processed_files = 0
        self.progress_label.config(text=f"Elaborati: 0 / {self.total_files}")
        self.progress_label.update()
        for idx, filename in enumerate(self.pdf_files, 1):
            pdf_path = os.path.join(self.folderpath, filename)
            images = pdf_to_images(pdf_path)
            if images:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                    images[0].save(temp_img.name)
                    numbers = image_to_numbers(temp_img.name)
                    if numbers:
                        self.all_numbers[filename] = (numbers, temp_img.name)
            self.processed_files += 1
            self.progress_label.config(text=f"Elaborati: {self.processed_files} / {self.total_files}")
            self.progress_label.update()

    def process_next_pdf(self):
        if not self.all_numbers:
            messagebox.showinfo("Completato", "Tutti i PDF sono stati elaborati.")
            return

        filename, (numbers, image_path) = self.all_numbers.popitem()
        ReviewWindow(self.root, numbers, image_path, os.path.join(self.output_dir, os.path.splitext(filename)[0]), filename, self.process_next_pdf)

# ---- REVIEW WINDOW CLASS ---- #

class ReviewWindow:
    def __init__(self, root, numbers, image_path, output_dir, pdf_filename, callback):
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

    def build_window(self):

        
        self.win = tk.Toplevel(self.root)
        self.win.title(f"Revisione CMR - {self.pdf_filename}")
        
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        self.win.geometry(f"{screen_width}x{screen_height}")
        

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

        # Label per numero di codici letti
        self.count_label = tk.Label(scrollable_frame, text=f"Codici letti: {len(self.numbers)}")
        self.count_label.pack(pady=5)

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
        self.img = Image.open(self.image_path).convert("RGB")
        self.update_canvas_image()

        # Bindings
        self.canvas.bind("<MouseWheel>", self.zoom_with_mouse)
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.do_pan)

        # Date picker
        date_time_frame = tk.Frame(scrollable_frame)
        date_time_frame.pack(pady=5)
        
        tk.Label(date_time_frame, text="Data:").pack(side=tk.LEFT)
        self.calendar = DateEntry(date_time_frame, date_pattern="dd-mm-yyyy")
        self.calendar.pack(side=tk.LEFT, padx=5)

        vcmd_hours = date_time_frame.register(lambda P: self.validate_input(P, min_value=0, max_value=23))
        vcmd_minutes = date_time_frame.register(lambda P: self.validate_input(P, min_value=0, max_value=59))

        tk.Label(date_time_frame, text="Orario (HH:MM):").pack(side=tk.LEFT)
        self.hours_spinbox = Spinbox(date_time_frame, width=3, from_=0, to=23, format="%02.0f", validate="key", validatecommand=(vcmd_hours, "%P") )
        self.hours_spinbox.pack(side=tk.LEFT, padx=5)
        self.minutes_spinbox = Spinbox(date_time_frame, width=3, from_=0, to=59, format="%02.0f", validate="key", validatecommand=(vcmd_minutes, "%P"))
        self.minutes_spinbox.pack(side=tk.LEFT, padx=5)

        # Entries for CMR codes
        for number in self.numbers:
            self.add_entry(entries_frame, number)

        # Aggiungi Codice Button
        add_entry_btn = tk.Button(scrollable_frame, text="Aggiungi Codice", command=lambda: self.add_entry(entries_frame))
        add_entry_btn.pack(pady=10)

        # Frame per Conferma e Annulla
        buttons_frame = tk.Frame(scrollable_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        tk.Button(buttons_frame, text="Conferma", command=self.confirm).pack(side=tk.LEFT, padx=10)
        tk.Button(buttons_frame, text="Annulla", command=self.cancel).pack(side=tk.RIGHT, padx=10)

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
    def add_entry(self, parent, number=""):
        frame = tk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)

        tk.Label(frame, text="Codice CMR:").pack(side=tk.LEFT)
        entry = tk.Entry(frame)
        entry.insert(0, number)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(frame, text="X", command=lambda: self.remove_entry(frame)).pack(side=tk.RIGHT)
        self.entries.append(frame)

        self.update_count_label()

    def remove_entry(self, frame):
        self.entries.remove(frame)
        frame.destroy()
        self.update_count_label()

    def update_count_label(self):
        self.count_label.config(text=f"Codici letti: {len(self.entries)}")

    # Confirm & Cancel
    def confirm(self):
        os.makedirs(self.output_dir, exist_ok=True)
        
        try:
            selected_date = self.calendar.get()
            datetime.strptime(selected_date, "%d-%m-%Y")  # Validazione
            formatted_date = datetime.strptime(selected_date, "%d-%m-%Y").strftime("%Y%m%d")
        except ValueError:
            messagebox.showerror("Errore", "Formato data non valido. Usa DD-MM-YYYY.")
            return

        selected_date = self.calendar.get_date().strftime("%Y%m%d")
        selected_time = str(self.hours_spinbox.get())+str(self.minutes_spinbox.get())

        for frame in self.entries:
            entry = frame.winfo_children()[1]
            number = entry.get()
            if number.strip():
                output_pdf = os.path.join(self.output_dir, f"POD_{number}_{selected_date+selected_time}.pdf")
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
    
    def validate_input(self, P, min_value, max_value, *args):
        if P == "":
            return True
        try:
            value = int(P)
            return min_value <= value <= max_value
        except ValueError:
            return False

# ---- LICECENSE ---- #

LICENSE_FILE = os.path.join(get_base_path(), "license.json")
VALIDATION_URL = "http://fabriziopesce.atwebpages.com/validate_licenses.php" 

def is_license_valid():
    if not os.path.exists(LICENSE_FILE):
        return False

    with open(LICENSE_FILE, "r") as f:
        data = json.load(f)

    expires_on = datetime.fromisoformat(data.get("expires_on"))
    if expires_on < datetime.now():
        return False
    return True

def ask_license():
    def on_submit():
        code = entry.get().strip()
        if not code:
            messagebox.showwarning("Errore", "Inserisci un codice di licenza.")
            return

        try:
            machine_id = str(uuid.uuid4())
            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.post(
                VALIDATION_URL,
                data={"code": code, "uuid": machine_id},
                headers=headers,
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
                top.destroy()
            else:
                messagebox.showerror("Licenza non valida", result.get("error", "Errore sconosciuto"))
        except Exception as e:
            messagebox.showerror("Errore", f"Errore durante la convalida: {e}")

    top = tk.Toplevel()
    top.title("Inserisci codice di licenza")
    tk.Label(top, text="Inserisci il codice di licenza per attivare l'applicazione").pack(padx=10, pady=10)
    entry = tk.Entry(top, width=30)
    entry.pack(pady=5)
    tk.Button(top, text="Conferma", command=on_submit).pack(pady=10)
    top.grab_set()
    top.wait_window()


# ---- MAIN ---- #

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # Nasconde la finestra principale fino a licenza verificata

    if not is_license_valid():
        ask_license()

    if not is_license_valid():
        messagebox.showerror("Licenza non valida", "Impossibile avviare l'app: licenza non valida o scaduta.")
        sys.exit()

    root.deiconify()  # Mostra la finestra principale se la licenza è valida
    root.title("Estrai Codici e Crea PDF")
    root.geometry("500x300")

    config = load_config()

    selected_source = tk.StringVar(value=config["source_folder"])
    selected_output = tk.StringVar(value=config["output_folder"])

    def choose_source_folder():
        folder = filedialog.askdirectory(title="Seleziona cartella PDF")
        if folder:
            selected_source.set(folder)

    def choose_output_folder():
        folder = filedialog.askdirectory(title="Seleziona cartella Output")
        if folder:
            selected_output.set(folder)

    def start_processing():
        source = selected_source.get()
        output = selected_output.get()
        if not source or not output:
            messagebox.showwarning("Attenzione", "Seleziona entrambe le cartelle.")
            return
        save_config(source, output)
        processor = PDFProcessor(root, progress_label)
        processor.folderpath = source
        processor.output_dir = output
        processor.pdf_files = [f for f in os.listdir(source) if f.lower().endswith(".pdf")]
        processor.process_pdfs()
        processor.process_next_pdf()

    tk.Label(root, text="Cartella PDF:").pack(pady=5)
    tk.Entry(root, textvariable=selected_source, width=50).pack()
    tk.Button(root, text="Scegli Cartella PDF", command=choose_source_folder).pack(pady=5)

    tk.Label(root, text="Cartella Output:").pack(pady=5)
    tk.Entry(root, textvariable=selected_output, width=50).pack()
    tk.Button(root, text="Scegli Cartella Output", command=choose_output_folder).pack(pady=5)

    tk.Button(root, text="Conferma ed Elabora", command=start_processing, width=30).pack(pady=20)

    progress_label = tk.Label(root, text="", fg="blue")
    progress_label.pack()

    icon_path = resource_path("ocroute_icon.ico")
    root.iconbitmap(icon_path)

    root.mainloop()

