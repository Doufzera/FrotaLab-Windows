"""FrotaLab Windows: auditoria conservadora de packs FiveM/QBCore."""
from __future__ import annotations
import csv
import hashlib
import json
import os
import queue
import re
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
from installer import GROUPS, destination_for, install_pack

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


def split_pack1_by_brand(input_dir: Path, output_dir: Path, notify=lambda _: None):
    """Build self-contained diagnostic FiveM resources per manufacturer.

    Original source content remains untouched. This separates initialization
    pressure; it does NOT optimize 3D assets nor prove runtime compatibility.
    """
    pack = input_dir / "pacote_01"
    if not pack.is_dir():
        raise ValueError("Pack 1 não foi extraído em originais/pacote_01.")
    matches = list(pack.rglob("PLOKS_CARS/fxmanifest.lua"))
    if len(matches) != 1:
        raise ValueError("PLOKS_CARS/fxmanifest.lua ausente ou duplicado.")
    source = matches[0].parent
    data_dir, stream_dir = source / "data", source / "stream"
    if not data_dir.is_dir() or not stream_dir.is_dir():
        raise ValueError("A origem não contém data/ e stream/.")

    data_groups = {d.name.upper(): d for d in data_dir.iterdir() if d.is_dir()}
    stream_groups = {d.name.upper(): d for d in stream_dir.iterdir() if d.is_dir()}
    if set(data_groups) != set(stream_groups):
        missing_data = sorted(set(stream_groups) - set(data_groups))
        missing_stream = sorted(set(data_groups) - set(stream_groups))
        raise ValueError(
            f"Fabricantes sem par data/stream: data={missing_data}, stream={missing_stream}")
    if not data_groups:
        raise ValueError("Nenhum fabricante reconhecido no Pack 1.")

    names_source = (source / "vehicle_names.lua").read_text(
        encoding="utf-8", errors="replace") if (source / "vehicle_names.lua").is_file() else ""
    parsed_names = []
    for line in names_source.splitlines():
        match = re.search(r"AddTextEntry\(\s*['\"]([^'\"]+)['\"]\s*,", line)
        if match:
            parsed_names.append((match.group(1).lower(), line.strip()))

    output_dir.mkdir(parents=True, exist_ok=True)
    created, manifest_report = [], []
    for index, group_name in enumerate(sorted(data_groups), start=1):
        data_group, stream_group = data_groups[group_name], stream_groups[group_name]
        if not (group_name.startswith("[") and group_name.endswith("]")):
            raise ValueError(f"Grupo inesperado: {group_name}")
        brand = group_name[1:-1]
        if not re.fullmatch(r"[A-Z0-9_-]+", brand):
            raise ValueError(f"Nome de fabricante inseguro: {group_name}")
        files_data = sorted(p for p in data_group.rglob("*") if p.is_file())
        files_stream = sorted(p for p in stream_group.rglob("*") if p.is_file())
        if not files_data or not files_stream:
            raise ValueError(f"Grupo incompleto: {group_name}")

        models = set()
        for meta_file in data_group.rglob("vehicles.meta"):
            try:
                root = ET.parse(meta_file).getroot()
            except ET.ParseError as exc:
                raise ValueError(f"vehicles.meta inválido: {meta_file}: {exc}") from exc
            for item in root.findall(".//InitDatas/Item"):
                for tag in ("modelName", "gameName"):
                    value = item.findtext(tag)
                    if value:
                        models.add(value.strip().lower())

        resource_name = f"CIV_{brand}"
        final_zip = output_dir / f"{resource_name}.zip"
        partial = final_zip.with_suffix(".partial")
        manifest = (
            "fx_version 'cerulean'\n"
            "game 'gta5'\n"
            "author 'PLOKMJNB - pack reorganizado para diagnóstico'\n"
            f"description 'Pack 1 - {brand} (original preservado)'\n"
            "files {\n"
            "    'data/**/*.meta',\n"
            "    'data/**/*.xml',\n"
            "    'data/**/*.dat',\n"
            "    'data/**/*.ytyp'\n"
            "}\n"
            "data_file 'HANDLING_FILE' 'data/**/handling*.meta'\n"
            "data_file 'VEHICLE_LAYOUTS_FILE' 'data/**/vehiclelayouts*.meta'\n"
            "data_file 'VEHICLE_METADATA_FILE' 'data/**/vehicles*.meta'\n"
            "data_file 'CARCOLS_FILE' 'data/**/carcols*.meta'\n"
            "data_file 'VEHICLE_VARIATION_FILE' 'data/**/carvariations*.meta'\n"
            "data_file 'CONTENT_UNLOCKING_META_FILE' 'data/**/*unlocks.meta'\n"
            "data_file 'PTFXASSETINFO_FILE' 'data/**/ptfxassetinfo.meta'\n"
            "client_script 'vehicle_names.lua'\n"
        )
        relevant = [line for key, line in parsed_names if key in models]
        names_lua = "CreateThread(function()\n"
        if relevant:
            names_lua += "    " + "\n    ".join(relevant) + "\n"
        names_lua += "end)\n"
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=1, allowZip64=True) as z:
                z.writestr(f"{resource_name}/fxmanifest.lua", manifest)
                z.writestr(f"{resource_name}/vehicle_names.lua", names_lua)
                for file in files_data:
                    rel = file.relative_to(data_group).as_posix()
                    z.write(file, f"{resource_name}/data/{group_name}/{rel}")
                for file in files_stream:
                    rel = file.relative_to(stream_group).as_posix()
                    z.write(file, f"{resource_name}/stream/{group_name}/{rel}")
            with zipfile.ZipFile(partial) as z:
                if z.testzip() is not None:
                    raise ValueError(f"CRC inválido: {resource_name}")
                if f"{resource_name}/fxmanifest.lua" not in z.namelist():
                    raise ValueError(f"Manifest ausente: {resource_name}")
            partial.replace(final_zip)
        finally:
            partial.unlink(missing_ok=True)
        created.append(final_zip.name)
        manifest_report.append({"resource": resource_name, "brand": brand,
                                "models_found": sorted(models),
                                "data_files": len(files_data), "stream_files": len(files_stream)})
        notify(f"Pack 1 dividido: {index}/{len(data_groups)} - {resource_name}")

    (output_dir / "INSTRUCOES_PACK1.txt").write_text(
        "PACOTE 1 DIVIDIDO POR FABRICANTE - DIAGNOSTICO\n"
        "1. Faça backup do servidor e DESATIVE o recurso PLOKS_CARS original.\n"
        "2. Não use ensure [carros] para ligar TODOS os grupos simultaneamente.\n"
        "3. Extraia inicialmente apenas CIV_ACURA.zip em resources/[carros]/.\n"
        "4. No console, use refresh e ensure CIV_ACURA.\n"
        "5. Se funcionar, inclua outra marca por vez. Ex.: ensure CIV_AUDI.\n"
        "6. Se uma marca causar travamento, pare e confira log do FXServer/txAdmin.\n"
        "7. Os .yft/.ytd são originais; esta separação NÃO otimiza FPS, RAM ou LODs.\n"
        "8. Confirme in-game cada modelo, tuning, texturas e áudio.\n",
        encoding="utf-8")
    (output_dir / "relatorio_marcas.json").write_text(
        json.dumps(manifest_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return created


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
        self.install_paths = [tk.StringVar(value="") for _ in range(4)]
        self.pack1_split = tk.BooleanVar(value=True)
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
        download_tab, audit_tab, export_tab, install_tab = (
            ttk.Frame(notebook) for _ in range(4))
        notebook.add(download_tab, text="Downloads")
        notebook.add(audit_tab, text="Auditoria")
        notebook.add(export_tab, text="Exportação")
        notebook.add(install_tab, text="Instalação")
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
        ttk.Button(export_tab, text="Dividir Pack 1 por fabricante (diagnóstico)",
                   command=self.start_split_pack1).pack(anchor="w", pady=12)
        ttk.Button(export_tab, text="Abrir pasta de trabalho",
                   command=self.open_folder).pack(anchor="w", pady=8)
        ttk.Label(install_tab, text="Selecione o destino de CADA pack (pasta resources do seu servidor).",
                  wraplength=920).pack(anchor="w", pady=(16, 4))
        ttk.Label(install_tab, text="O FrotaLab criará [carros], [carros2], [carros3] e [carros4]. "
                  "Se você escolher a própria categoria, não criará uma pasta duplicada.",
                  wraplength=920).pack(anchor="w", pady=(0, 10))
        for i, (name, _) in enumerate(SOURCES):
            frame = ttk.Frame(install_tab)
            frame.pack(fill="x", padx=5, pady=(5, 3))
            ttk.Label(frame, text=f"Pack {i+1} — {name} → {GROUPS[i+1]}").pack(anchor="w")
            controls = ttk.Frame(frame)
            controls.pack(fill="x", pady=(3, 0))
            ttk.Entry(controls, textvariable=self.install_paths[i], width=62).pack(
                side="left", fill="x", expand=True, padx=(0, 9))
            ttk.Button(controls, text="Escolher pasta", command=lambda index=i:
                       self.choose_install_folder(index)).pack(side="left", padx=(0, 8))
            ttk.Button(controls, text=f"Instalar Pack {i+1}",
                       command=lambda index=i: self.start_install_pack(index)).pack(side="left")
        ttk.Checkbutton(install_tab,
                        text="Pack 1: dividir por fabricantes (recomendado: testar uma marca por vez)",
                        variable=self.pack1_split).pack(anchor="w", padx=5, pady=(12, 3))
        ttk.Label(install_tab,
                  text="Segurança: pastas de destino com conteúdo nunca são sobrescritas. "
                  "Os arquivos originais permanecem intactos. Evite iniciar todos os "
                  "recursos simultaneamente, especialmente o Pack 1.",
                  wraplength=850).pack(anchor="w", padx=5, pady=(1, 7))
        ttk.Button(install_tab, text="Instalar os 4 packs nos destinos escolhidos",
                   command=self.start_install_all).pack(anchor="w", padx=5, pady=5)
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

    def start_split_pack1(self):
        if not (self.base / "originais" / "pacote_01").is_dir():
            messagebox.showwarning("FrotaLab", "Primeiro baixe e extraia o Pack 1.")
            return
        def work(notify):
            output = self.base / "exportados" / "pack1_por_marca"
            made = split_pack1_by_brand(self.base / "originais", output, notify)
            return (f"Pack 1 dividido em {len(made)} ZIPs de fabricantes. "
                    "Leia INSTRUCOES_PACK1.txt e teste uma marca por vez.")
        self._background(work)

    def choose_install_folder(self, index):
        current = self.install_paths[index].get().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        folder = filedialog.askdirectory(
            parent=self, title=f"Destino do Pack {index + 1}: escolha resources ou {GROUPS[index+1]}",
            initialdir=initial, mustexist=True)
        if folder:
            self.install_paths[index].set(folder)
            try:
                target = destination_for(index + 1, Path(folder))
                self.status.set(f"Destino do Pack {index + 1}: {target}")
            except ValueError as exc:
                messagebox.showwarning("FrotaLab", str(exc))

    def start_install_pack(self, index):
        selected = self.install_paths[index].get().strip()
        if not selected:
            messagebox.showwarning(
                "FrotaLab", f"Escolha a pasta de destino do Pack {index+1}.")
            return
        split = self.pack1_split.get()
        def work(notify):
            target, resources = install_pack(
                self.base / "originais", index+1, Path(selected),
                split_pack1=split, notify=notify)
            return (f"Pack {index+1} instalado em {target}: "
                    f"{len(resources)} recursos. Leia INSTRUCOES_FROTALAB.txt. "
                    "Não inicie todos os packs antes de validar conflitos.")
        self._background(work)

    def start_install_all(self):
        selected = [item.get().strip() for item in self.install_paths]
        if not all(selected):
            messagebox.showwarning(
                "FrotaLab", "Escolha as quatro pastas antes de instalar todos os packs.")
            return
        if not messagebox.askyesno(
                "FrotaLab", "Instalar os quatro packs em seus destinos escolhidos?\n\n"
                "Essa operação copia muitos gigabytes e não substitui pastas existentes.\n"
                "Instale e teste os recursos individualmente antes de ativar todos."):
            return
        split = self.pack1_split.get()
        def work(notify):
            completed = []
            for idx, folder in enumerate(selected, start=1):
                notify(f"Iniciando Pack {idx}/4...")
                target, resources = install_pack(
                    self.base / "originais", idx, Path(folder),
                    split_pack1=split, notify=notify)
                completed.append(f"Pack {idx}: {target} ({len(resources)} recursos)")
            return ("Instalações concluídas:\n" + "\n".join(completed) +
                    "\nConsulte INSTRUCOES_FROTALAB.txt de cada categoria.")
        self._background(work)

    def open_folder(self):
        self.base.mkdir(parents=True, exist_ok=True)
        os.startfile(self.base)


if __name__ == "__main__":
    FrotaLab().mainloop()
