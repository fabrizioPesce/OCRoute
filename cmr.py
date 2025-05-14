import tkinter as tk
from tkinter import filedialog, messagebox
import pytesseract
from PIL import Image
import cv2
import os
from pdf2image import convert_from_path
from reportlab.pdfgen import canvas
import re

# CONFIGURA QUI IL PERCORSO DI TESSERACT
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

def extract_numbers(text):
    return re.findall(r'\b\d{10}\b', text)

def image_to_pdf_with_names(image_path, output_dir):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
    text = pytesseract.image_to_string(preprocess_image(image_path), config=custom_config)
    numbers = extract_numbers(text)
    print(numbers)

    for number in numbers:
        output_pdf = os.path.join(output_dir, f"{number}.pdf")
        c = canvas.Canvas(output_pdf)
        c.drawImage(image_path, 0, 0, width=595, height=842)  # A4 size
        c.save()

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
                temp_img = f"temp_page_{i}.jpg"
                img.save(temp_img)
                image_to_pdf_with_names(temp_img, output_dir)
                os.remove(temp_img)
        else:
            image_to_pdf_with_names(filepath, output_dir)

        messagebox.showinfo("Successo", "PDF creati con successo!")
    except Exception as e:
        messagebox.showerror("Errore", str(e))

def preprocess_image(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    image = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    image = cv2.bilateralFilter(image, 9, 75, 75)  # riduce il rumore
    image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 31, 2)
    return image

# GUI
root = tk.Tk()
root.title("Estrai Codici e Crea PDF")
root.geometry("400x200")

label = tk.Label(root, text="Seleziona un file JPG/PNG o PDF da elaborare", pady=20)
label.pack()

btn = tk.Button(root, text="Scegli File", command=process_file, width=20)
btn.pack(pady=10)

root.mainloop()
