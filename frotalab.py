"""FrotaLab Windows: auditoria conservadora de packs FiveM/QBCore."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import queue
import shutil
import threading
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import xml.etree.ElementTree as ET

SOURCES = [
    ("PLOKMJNB - Civ Car Pack", "https://codeload.github.com/PLOKMJNB/FiveM-Civ-Car-Pack/zip/refs/heads/master"),
    ("SpiritsCreations - Lore Friendly", "https://codeload.github.com/SpiritsCreations/FiveM-Lore-Friendly-Pack/zip/refs/heads/main"),
    ("Aweetumn-LLC - Lorefriendly", "https://codeload.github.com/Aweetumn-LLC/FiveM-Lorefriendly-Vehicles/zip/refs/heads/main"),
    ("LividDS - Lorefriendly Cars", "https://codeload.github.com/LividDS/Lorefriendly-Cars/zip/refs/tags/pack.0.5"),
]
BINARY_EXTS = {".yft", ".ytd", ".ydr", ".ycd", ".awc", ".rel", ".rpf", ".ytyp"}
MAX_ENTRY = 2 * 1024 ** 3
MAX_TOTAL = 35 * 1024 ** 3


def safe_unpack(archive: Path, destination: Path, notify=lambda _: None):
    """Extract only regular safe files, checking limits and CRC."""
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        total = 0
        for entry in entries:
            name = entry.filename.replace("\\", "/")
            parts = Path(name).parts
            if name.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
                raise ValueError(f"Caminho inseguro no ZIP: {name}")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Link simbólico no ZIP: {name}")
            if entry.flag_bits & 1:
                raise ValueError(f"Arquivo criptografado: {name}")
            total += entry.file_size
            if entry.file_size > MAX_ENTRY or total > MAX_TOTAL:
                raise ValueError("Limite de extração excedido")
        if z.testzip() is not None:
            raise ValueError("Falha no teste CRC do ZIP")
        destination.mkdir(parents=True, exist_ok=True)
        base = destination.resolve()
        for idx, entry in enumerate(entries):
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(base):
                raise ValueError(f"Caminho fora da pasta: {entry.filename}")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(entry) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            if idx % 300 == 0:
                notify(f"Extraindo {archive.name}: {idx}/{len(entries)}")
    return len(entries)


def download_file(url: str, target: Path, notify):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".part")
    request = urllib.request.Request(url, headers={"User-Agent": "FrotaLab/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temp.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            got = 0
            while True:
                part = response.read(1024 * 1024)
                if not part:
                    break
                output.write(part)
                got += len(part)
                if got % (32 * 1024 * 1024) < len(part):
                    notify(f"Download {target.name}: {got / 1024**3:.2f} GiB"
                           + (f" / {total / 1024**3:.2f} GiB" if total else ""))
        with zipfile.ZipFile(temp) as z:
            if z.testzip() is not None:
                raise ValueError(f"ZIP com erro CRC: {target.name}")
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            sha.update(part)
    return sha.hexdigest()


def audit(root: Path, report_dir: Path, notify=lambda _: None):
    report_dir.mkdir(parents=True, exist_ok=True)
    records, invalid_xml, heavy, duplicates = [], [], [], []
    by_digest = defaultdict(list)
    for idx, file in enumerate(sorted(root.rglob("*"))):
        if not file.is_file() or report_dir in file.parents:
            continue
        rel = file.relative_to(root).as_posix()
        size = file.stat().st_size
        ext = file.suffix.lower()
        digest = sha256_file(file)
        row = {"arquivo": rel, "bytes": size, "extensao": ext, "sha256": digest}
        records.append(row)
        by_digest[(size, digest)].append(rel)
        if ext in {".meta", ".xml"}:
            try:
                ET.parse(file)
            except ET.ParseError as exc:
                invalid_xml.append({"arquivo": rel, "erro": str(exc)})
        if ext in {".yft", ".ytd"} and size >= 13 * 1024**2:
            heavy.append(row)
        if idx % 200 == 0:
            notify(f"Analisando arquivos: {idx + 1}")
    for (size, digest), paths in by_digest.items():
        if len(paths) > 1:
            duplicates.append({"sha256": digest, "bytes": size, "quantidade": len(paths),
                               "arquivos": paths})
    def write_csv(name, rows, columns):
        with (report_dir / name).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    write_csv("inventario.csv", records, ["arquivo", "bytes", "extensao", "sha256"])
    write_csv("xml_invalidos.csv", invalid_xml, ["arquivo", "erro"])
    write_csv("arquivos_pesados.csv", heavy, ["arquivo", "bytes", "extensao", "sha256"])
    (report_dir / "duplicados.json").write_text(
        json.dumps(duplicates, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivos": len(records),
        "tamanho_bytes": sum(r["bytes"] for r in records),
        "grupos_duplicados": len(duplicates),
        "arquivos_pesados": len(heavy),
        "xml_invalidos": len(invalid_xml),
        "observacao": "Somente auditoria. Duplicatas NÃO foram removidas; "
                      "tamanhos não provam problemas de FPS; nenhum modelo 3D foi otimizado.",
    }
    (report_dir / "resumo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def export_packages(input_dir: Path, output_dir: Path, notify=lambda _: None):
    """Export sources as archives, correcting the PLOKS_CARS resource wrapper.

    The other sources remain backups: they have NOT been normalized or checked
    for FiveM runtime conflicts. Nothing is deleted or 3D-optimized.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for folder in sorted(input_dir.iterdir()):
        if not folder.is_dir():
            continue
        source = folder
        output_name = folder.name + ".zip"
        include_resource_dir = False
        if folder.name == "pacote_01":
            candidates = list(folder.rglob("PLOKS_CARS/fxmanifest.lua"))
            if len(candidates) != 1:
                raise ValueError(
                    "PLOKS_CARS/fxmanifest.lua não encontrado de forma única. "
                    "Verifique a extração do Pack 1 antes de exportar."
                )
            source = candidates[0].parent
            if not (source / "stream").is_dir() or not (source / "data").is_dir():
                raise ValueError("PLOKS_CARS sem as pastas data/ e stream/.")
            output_name = "PLOKS_CARS.zip"
            include_resource_dir = True
        output = output_dir / output_name
        partial = output.with_suffix(".partial")
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=1, allowZip64=True) as z:
                for idx, path in enumerate(source.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(source).as_posix()
                    archive_path = (source.name + "/" + relative
                                    if include_resource_dir else relative)
                    z.write(path, archive_path)
                    if idx % 500 == 0:
                        notify(f"Empacotando {output_name}: {idx} entradas")
            with zipfile.ZipFile(partial) as z:
                if z.testzip() is not None:
                    raise ValueError(f"Falha CRC exportando {output_name}")
                if include_resource_dir:
                    names = set(z.namelist())
                    for required in ("PLOKS_CARS/fxmanifest.lua",
                                     "PLOKS_CARS/server.lua",
                                     "PLOKS_CARS/vehicle_names.lua"):
                        if required not in names:
                            raise ValueError(f"Arquivo ausente no ZIP: {required}")
            partial.replace(output)
            made.append(output.name)
        finally:
            partial.unlink(missing_ok=True)
    return made


class FrotaLab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FrotaLab | FiveM Vehicle Optimizer")
        self.geometry("1040x700")
        self.minsize(780, 560)
        self.configure(bg="#0d141d")
        self.events = queue.Queue()
        self.busy = False
        self.base = Path.home() / "Documents" / "FrotaLab"
        self.sources_var = []
        self._style()
        self._layout()
        self.after(120, self._poll)

    def _style(self):
        sty = ttk.Style(self)
        sty.theme_use("clam")
        sty.configure("TFrame", background="#0d141d")
        sty.configure("TLabel", background="#0d141d", foreground="#ddeaf3",
                      font=("Segoe UI", 10))
        sty.configure("Header.TLabel", font=("Segoe UI Semibold", 22),
                      foreground="#4ddab4")
        sty.configure("TButton", font=("Segoe UI Semibold", 10), padding=10,
                      background="#193c3a", foreground="#dcfff4",
                      borderwidth=0)
        sty.map("TButton", background=[("active", "#23685a")])
        sty.configure("TCheckbutton", background="#0d141d", foreground="#dce9f3",
                      font=("Segoe UI", 10))
        sty.configure("TNotebook", background="#0d141d", borderwidth=0)
        sty.configure("TNotebook.Tab", background="#182633", foreground="#aabbc9",
                      padding=(17, 10))
        sty.map("TNotebook.Tab", background=[("selected", "#1e594d")],
                foreground=[("selected", "#e8fff6")])

    def _layout(self):
        head = ttk.Frame(self)
        head.pack(fill="x", padx=24, pady=(20, 8))
        ttk.Label(head, text="FROTA LAB", style="Header.TLabel").pack(anchor="w")
        ttk.Label(head, text="Auditoria e preparação segura de veículos FiveM / QBCore").pack(anchor="w")
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=22, pady=12)
        download_tab, audit_tab, export_tab = (ttk.Frame(notebook) for _ in range(3))
        notebook.add(download_tab, text="Downloads")
        notebook.add(audit_tab, text="Auditoria")
        notebook.add(export_tab, text="Exportação")
        ttk.Label(download_tab, text="Fontes configuradas").pack(anchor="w", pady=(20, 12))
        for name, url in SOURCES:
            v = tk.BooleanVar(value=True)
            self.sources_var.append(v)
            ttk.Checkbutton(download_tab, text=name, variable=v).pack(anchor="w", pady=5)
        ttk.Button(download_tab, text="Baixar e extrair selecionados",
                   command=self.start_download).pack(anchor="w", pady=20)
        ttk.Label(audit_tab, text="Analise arquivos por tamanho, hash SHA-256 e XML.",
                  wraplength=710).pack(anchor="w", pady=(25, 12))
        ttk.Button(audit_tab, text="Auditar pacotes extraídos",
                   command=self.start_audit).pack(anchor="w", pady=12)
        ttk.Label(audit_tab, text="Relatórios: inventario.csv, duplicados.json, "
                  "arquivos_pesados.csv, xml_invalidos.csv e resumo.json",
                  wraplength=710).pack(anchor="w", pady=12)
        ttk.Label(export_tab, text="Cria um ZIP para cada fonte importada, preservando "
                  "estrutura e dependências. Não remove cópias automaticamente.",
                  wraplength=700).pack(anchor="w", pady=(25, 12))
        ttk.Button(export_tab, text="Gerar ZIPs verificados",
                   command=self.start_export).pack(anchor="w", pady=12)
        ttk.Button(export_tab, text="Abrir pasta de trabalho",
                   command=self.open_folder).pack(anchor="w", pady=8)
        bottom = ttk.Frame(self)
        bottom.pack(fill="both", expand=False, padx=22, pady=(0, 20))
        ttk.Label(bottom, text="Pasta de trabalho: " + str(self.base),
                  wraplength=880).pack(anchor="w", pady=5)
        self.status = tk.StringVar(value="Pronto. Nenhum arquivo foi alterado.")
        ttk.Label(bottom, textvariable=self.status, wraplength=890).pack(anchor="w", pady=5)
        self.log = tk.Text(bottom, height=9, bg="#12202c", fg="#d0e5ed",
                           insertbackground="#fff", relief="flat",
                           font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, pady=(7, 0))

    def _poll(self):
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "log":
                    self.status.set(text)
                    self.log.configure(state="normal")
                    self.log.insert("end", text + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "done":
                    self.busy = False
                    self.status.set(text)
                    messagebox.showinfo("FrotaLab", text)
                elif kind == "error":
                    self.busy = False
                    self.status.set("Erro: " + text)
                    messagebox.showerror("FrotaLab", text)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _background(self, fn):
        if self.busy:
            messagebox.showwarning("FrotaLab", "Aguarde o processo atual terminar.")
            return
        self.busy = True
        def runner():
            try:
                message = fn(lambda text: self.events.put(("log", text)))
                self.events.put(("done", message))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=runner, daemon=True).start()

    def start_download(self):
        selected = [(name, url) for (name, url), flag in
                    zip(SOURCES, self.sources_var) if flag.get()]
        if not selected:
            messagebox.showwarning("FrotaLab", "Selecione uma fonte.")
            return
        def work(notify):
            for index, (name, url) in enumerate(selected, start=1):
                slug = f"pacote_{SOURCES.index((name, url)) + 1:02d}"
                downloaded = self.base / "downloads" / (slug + ".zip")
                extracted = self.base / "originais" / slug
                if not downloaded.exists():
                    notify(f"Baixando {index}/{len(selected)}: {name}")
                    download_file(url, downloaded, notify)
                else:
                    notify(f"Reutilizando download: {downloaded.name}")
                if extracted.exists():
                    notify(f"Já extraído: {slug}. Pasta original preservada.")
                    continue
                staging = extracted.with_name(extracted.name + "_extraindo")
                if staging.exists():
                    shutil.rmtree(staging)
                try:
                    safe_unpack(downloaded, staging, notify)
                    staging.replace(extracted)
                except Exception:
                    shutil.rmtree(staging, ignore_errors=True)
                    raise
            return "Downloads e extrações concluídos. Originais preservados."
        self._background(work)

    def start_audit(self):
        if not (self.base / "originais").exists():
            messagebox.showwarning("FrotaLab", "Primeiro baixe os pacotes.")
            return
        def work(notify):
            result = audit(self.base / "originais", self.base / "relatorios", notify)
            return (f"Auditoria concluída: {result['arquivos']} arquivos; "
                    f"{result['grupos_duplicados']} grupos duplicados; "
                    f"{result['xml_invalidos']} XML inválidos.")
        self._background(work)

    def start_export(self):
        if not (self.base / "originais").exists():
            messagebox.showwarning("FrotaLab", "Primeiro baixe os pacotes.")
            return
        def work(notify):
            made = export_packages(self.base / "originais",
                                   self.base / "exportados", notify)
            return f"ZIPs gerados e CRC verificado: {len(made)}. Veja a pasta exportados."
        self._background(work)

    def open_folder(self):
        self.base.mkdir(parents=True, exist_ok=True)
        os.startfile(self.base)


if __name__ == "__main__":
    FrotaLab().mainloop()
