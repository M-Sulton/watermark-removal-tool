# Panduan Instalasi & Menjalankan (Windows & Linux)

## Kebutuhan Sistem
- Python 3.10 - 3.14 (pastikan centang **Add Python to PATH** saat install)
- Git (opsional)

---

## 1. Instalasi Windows (Manual via PowerShell / CMD)

Masuk ke folder project:
```powershell
cd "D:\Socmed Project\windows-pkg"
```

Buat dan aktifkan Virtual Environment:
```powershell
python -m venv venv
venv\Scripts\activate
```

Install semua dependency yang dibutuhkan:
```powershell
pip install fastapi uvicorn[standard] opencv-python numpy aiofiles python-multipart
```
Atau jika ada file `requirements.txt`:
```powershell
pip install -r requirements.txt
```

### Daftar Library Wajib:
- `fastapi` : Web framework backend API
- `uvicorn[standard]` : ASGI Server untuk running FastAPI
- `python-multipart` : Parsing upload file / form data di endpoint `/api/upload`
- `opencv-python` : Algoritma computer vision Telea & Navier-Stokes inpainting
- `numpy` : Manipulasi array pixel gambar & mask
- `aiofiles` : Operasi file I/O async FastAPI

---

## 2. Cara Menjalankan Server

Pastikan virtual environment aktif `(venv)`:
```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
> **Penting**: Jalankan `main:app` (bukan `app.main:app`) karena file `main.py` ada di root folder.

Tunggu hingga muncul log:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Buka browser:
[http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 3. Jalankan Otomatis via Batch Script (Windows)

Cukup double-click file:
`run_windows.bat` atau `install_and_run.bat`
