#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PhotoManager GUI - Lightweight local app (Windows 11)
- Redimensionne dans une boîte WxH en conservant les proportions
- Compresse en JPG (qualité ajustable)
- Renommage: <nom_dossier>_<YYYYMMDD>_<compteur>.jpg
- Sortie: dossier choisi (par défaut <input>/output)
- Option récursive (sous-dossiers)
- Support "glisser-déposer" du dossier via .bat (argv)
Dépendances: Pillow (PIL)
"""

import sys
import threading
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageOps, ExifTags

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}


def exif_datetime(img, src: Path):
    from datetime import datetime
    try:
        exif = img.getexif()
        if exif and len(exif) > 0:
            for k, v in exif.items():
                if ExifTags.TAGS.get(k, k) == 'DateTimeOriginal' and isinstance(v, str):
                    v2 = v.replace(':', '-', 2)
                    return datetime.fromisoformat(v2)
    except Exception:
        pass
    try:
        return datetime.fromtimestamp(src.stat().st_mtime)
    except Exception:
        return datetime.now()


def ensure_rgb(img):
    if img.mode in ('RGBA', 'LA', 'P', 'CMYK'):
        return img.convert('RGB')
    return img


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    i = 1
    while True:
        candidate = folder / f"{stem}{i:03d}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


class PhotoManagerGUI(tk.Tk):
    def __init__(self, preset_input: Path | None = None):
        super().__init__()
        self.title("PhotoManager GUI")
        self.geometry("600x400")
        self.resizable(False, False)

        self.input_dir = tk.StringVar(value=str(preset_input) if preset_input else "")
        self.output_dir = tk.StringVar(value=str((preset_input / "output").resolve()) if preset_input else "")
        self.max_w = tk.IntVar(value=800)
        self.max_h = tk.IntVar(value=600)
        self.quality = tk.IntVar(value=70)
        self.strip_metadata = tk.BooleanVar(value=False)
        self.recursive = tk.BooleanVar(value=True)  # par défaut: récursif activé

        self._build_ui()

        self.worker_thread = None
        self.progress_max = 0

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 6}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **pad)

        # Input folder
        row1 = ttk.Frame(frm)
        row1.pack(fill="x", **pad)
        ttk.Label(row1, text="Dossier d'entrée:").pack(side="left")
        ttk.Entry(row1, textvariable=self.input_dir, width=48).pack(side="left", padx=6)
        ttk.Button(row1, text="Parcourir...", command=self.browse_input).pack(side="left")

        # Output folder
        row2 = ttk.Frame(frm)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Dossier de sortie:").pack(side="left")
        ttk.Entry(row2, textvariable=self.output_dir, width=48).pack(side="left", padx=6)
        ttk.Button(row2, text="Parcourir...", command=self.browse_output).pack(side="left")

        # Options
        row3 = ttk.Frame(frm)
        row3.pack(fill="x", **pad)
        ttk.Label(row3, text="Largeur max:").pack(side="left")
        ttk.Entry(row3, textvariable=self.max_w, width=6).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Hauteur max:").pack(side="left")
        ttk.Entry(row3, textvariable=self.max_h, width=6).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Qualité JPG (1-100):").pack(side="left")
        ttk.Entry(row3, textvariable=self.quality, width=6).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(row3, text="Supprimer métadonnées (strip)", variable=self.strip_metadata).pack(side="left")

        row3b = ttk.Frame(frm)
        row3b.pack(fill="x", **pad)
        ttk.Checkbutton(row3b, text="Traiter aussi les sous-dossiers (récursif)", variable=self.recursive).pack(side="left")

        # Progress
        row4 = ttk.Frame(frm)
        row4.pack(fill="x", **pad)
        self.pb = ttk.Progressbar(row4, orient="horizontal", mode="determinate", length=520, maximum=100)
        self.pb.pack(side="left", padx=(0, 10))
        self.lbl_progress = ttk.Label(row4, text="0 / 0")
        self.lbl_progress.pack(side="left")

        # Buttons
        row5 = ttk.Frame(frm)
        row5.pack(fill="x", **pad)
        ttk.Button(row5, text="Lancer le traitement", command=self.on_run).pack(side="left")
        ttk.Button(row5, text="Quitter", command=self.destroy).pack(side="right")

        # Footer
        ttk.Label(frm, text="PhotoManager GUI — Python + Pillow — Windows 11").pack(side="bottom", pady=8)

    def browse_input(self):
        path = filedialog.askdirectory(title="Choisir le dossier d'entrée")
        if path:
            self.input_dir.set(path)
            out = Path(path) / "output"
            self.output_dir.set(str(out))

    def browse_output(self):
        path = filedialog.askdirectory(title="Choisir le dossier de sortie")
        if path:
            self.output_dir.set(path)

    def _gather_images(self, folder: Path, recursive: bool):
        exts = SUPPORTED_EXT
        if recursive:
            return [p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in exts]
        else:
            return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]

    def on_run(self):
        try:
            in_dir = Path(self.input_dir.get()).resolve()
            if not in_dir.exists() or not in_dir.is_dir():
                messagebox.showerror("Erreur", "Dossier d'entrée invalide.")
                return
            out_dir = Path(self.output_dir.get()).resolve() if self.output_dir.get().strip() else (in_dir / "output").resolve()
            out_dir.mkdir(parents=True, exist_ok=True)

            try:
                w = int(self.max_w.get())
                h = int(self.max_h.get())
                q = int(self.quality.get())
            except Exception:
                messagebox.showerror("Erreur", "Paramètres invalides (valeurs numériques requises).")
                return

            if w <= 0 or h <= 0 or not (1 <= q <= 100):
                messagebox.showerror("Erreur", "Paramètres invalides (w/h > 0, qualité 1..100).")
                return

            imgs = self._gather_images(in_dir, self.recursive.get())
            if not imgs:
                messagebox.showinfo("Info", "Aucune image trouvée dans le dossier (et sous-dossiers si activé).")
                return

            self.progress_max = len(imgs)
            self.pb['value'] = 0
            self.pb['maximum'] = self.progress_max
            self.lbl_progress.config(text=f"0 / {self.progress_max}")

            t = threading.Thread(target=self._process_images, args=(in_dir, out_dir, imgs, w, h, q, self.strip_metadata.get()), daemon=True)
            t.start()
            self._wait_thread(t)

        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _wait_thread(self, t: threading.Thread):
        if t.is_alive():
            self.after(100, lambda: self._wait_thread(t))
        else:
            pass

    def _process_images(self, in_dir: Path, out_dir: Path, imgs, max_w, max_h, quality, strip):
        try:
            parent_name = in_dir.name
            counters = {}
            processed = 0

            for src in imgs:
                try:
                    from PIL import Image
                    im = Image.open(src)
                    try:
                        im = ImageOps.exif_transpose(im)
                        dt = exif_datetime(im, src)
                        day_key = dt.strftime('%Y%m%d')

                        counters.setdefault(day_key, 0)
                        counters[day_key] += 1

                        stem = f"{parent_name}_{day_key}_"
                        im = ensure_rgb(im)
                        im.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

                        out_path = unique_path(out_dir, stem, '.jpg')
                        save_kwargs = dict(format='JPEG', quality=quality, optimize=True, subsampling='4:2:0')
                        if not strip:
                            exif = im.info.get('exif')
                            icc = im.info.get('icc_profile')
                            if exif:
                                save_kwargs['exif'] = exif
                            if icc:
                                save_kwargs['icc_profile'] = icc
                        im.save(out_path, **save_kwargs)
                    finally:
                        im.close()

                except Exception as e:
                    print(f"[ERREUR] {src}: {e}")

                processed += 1
                self.pb['value'] = processed
                self.lbl_progress.config(text=f"{processed} / {self.progress_max}")

            messagebox.showinfo("Terminé", f"Traitement terminé !\nSortie : {out_dir}")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))


def get_preset_from_argv():
    # Si on passe un dossier en argument (drag & drop sur le .bat), on le pré-remplit
    if len(sys.argv) >= 2:
        p = Path(sys.argv[1]).expanduser().resolve()
        if p.exists() and p.is_dir():
            return p
    return None


if __name__ == "__main__":
    preset = get_preset_from_argv()
    app = PhotoManagerGUI(preset_input=preset)
    app.mainloop()
