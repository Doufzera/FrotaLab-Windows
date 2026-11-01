"""Interface Windows independente para unir quatro packs FiveM em [carros]."""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from fusion_core import SOURCES, build_fusion, download_archives


class FrotaFusion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FrotaFusion | 4 packs FiveM / QBCore")
        self.geometry("990x740")
        self.minsize(820, 590)
        self.configure(bg="#0f1824")
        self.events = queue.Queue()
        self.busy = False
        self.paths = [tk.StringVar() for _ in range(4)]
        previous = Path.home() / "Documents" / "FrotaLab" / "originais"
        for i in range(4):
            possible = previous / f"pacote_{i + 1:02d}"
            if possible.is_dir():
                self.paths[i].set(str(possible))
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="Selecione os ZIPs/pastas originais e o destino resources.")
        self._layout()
        self.after(120, self._poll)

    def _layout(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#0f1824")
        style.configure("TLabel", background="#0f1824", foreground="#dde8f8",
                        font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 21),
                        foreground="#5dd7b2")
        style.configure("TButton", font=("Segoe UI Semibold", 10),
                        padding=(9, 7), background="#224f4d", foreground="#ffffff")
        style.map("TButton", background=[("active", "#307368")])
        style.configure("TEntry", padding=5)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=23, pady=20)
        ttk.Label(frame, text="FROTA FUSION", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame,
                  text="Une os 4 packs em resources/[carros] e remove cópias "
                       "com o mesmo spawn da SAÍDA (sem apagar os originais).",
                  wraplength=880).pack(anchor="w", pady=(6, 14))
        for idx, (title, _) in enumerate(SOURCES):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=7)
            ttk.Label(row, text=f"Pack {idx + 1} — {title}").pack(anchor="w", pady=(0, 3))
            inputs = ttk.Frame(row)
            inputs.pack(fill="x")
            ttk.Entry(inputs, textvariable=self.paths[idx], width=63).pack(
                side="left", fill="x", expand=True, padx=(0, 6))
            ttk.Button(inputs, text="Pasta",
                       command=lambda i=idx: self.choose_folder(i)).pack(side="left", padx=(0, 4))
            ttk.Button(inputs, text="ZIP",
                       command=lambda i=idx: self.choose_zip(i)).pack(side="left")
        ttk.Button(frame, text="Baixar os 4 packs originais (ZIPs grandes)",
                   command=self.download_all).pack(anchor="w", pady=(12, 8))
        ttk.Label(frame, text="Destino: selecione a pasta resources do seu FXServer.").pack(
            anchor="w", pady=(14, 4))
        destination = ttk.Frame(frame)
        destination.pack(fill="x")
        ttk.Entry(destination, textvariable=self.output_path, width=68).pack(
            side="left", fill="x", expand=True, padx=(0, 7))
        ttk.Button(destination, text="Escolher resources",
                   command=self.choose_destination).pack(side="left")
        ttk.Label(frame,
                  text="O resultado ficará em resources/[carros] com manifestos e "
                       "recursos originais separados. O processo NÃO sobrescreve "
                       "uma [carros] existente. Pare o servidor e faça backup antes.",
                  wraplength=880).pack(anchor="w", pady=(16, 9))
        ttk.Button(frame, text="ANALISAR, REMOVER REPETIDOS E GERAR [carros]",
                   command=self.run_merge).pack(anchor="w", pady=(2, 9))
        ttk.Label(frame,
                  text="Critério: arquivo YFT de base presente, texturas/metadados "
                       "consistentes e menor tamanho estimado. Tamanho não garante "
                       "melhor FPS nem qualidade visual; consulte relatório JSON.",
                  wraplength=880).pack(anchor="w", pady=8)
        ttk.Label(frame, textvariable=self.status, wraplength=900).pack(
            anchor="w", pady=(12, 4))
        self.log = tk.Text(frame, bg="#142334", fg="#e2f1f5", height=11,
                           state="disabled", relief="flat", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def choose_folder(self, idx):
        value = filedialog.askdirectory(parent=self, title=f"Pack {idx+1}: pasta original")
        if value:
            self.paths[idx].set(value)

    def choose_zip(self, idx):
        value = filedialog.askopenfilename(
            parent=self, title=f"Pack {idx+1}: ZIP original",
            filetypes=[("Arquivos ZIP", "*.zip")])
        if value:
            self.paths[idx].set(value)

    def choose_destination(self):
        value = filedialog.askdirectory(
            parent=self, title="Pasta resources do seu servidor")
        if value:
            self.output_path.set(value)

    def _start_worker(self, action):
        if self.busy:
            messagebox.showwarning("FrotaFusion", "Já existe um trabalho em andamento.")
            return
        self.busy = True

        def work():
            try:
                result = action(lambda msg: self.events.put(("log", msg)))
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", f"{type(exc).__name__}: {exc}"))
        threading.Thread(target=work, daemon=True).start()

    def download_all(self):
        if not messagebox.askyesno(
                "FrotaFusion", "Baixar os 4 ZIPs originais?\n\n"
                "Eles podem ocupar muitos gigabytes em disco. "
                "Se já possui os arquivos originais, utilize Pasta ou ZIP."):
            return

        def work(notify):
            dest = Path.home() / "Documents" / "FrotaFusion" / "downloads"
            files = download_archives(dest, notify)
            self.events.put(("downloaded", [str(p) for p in files]))
            return "Downloads concluídos. Agora selecione resources e inicie a fusão."
        self._start_worker(work)

    def run_merge(self):
        inputs = [p.get().strip() for p in self.paths]
        destination = self.output_path.get().strip()
        if not all(inputs) or not destination:
            messagebox.showwarning(
                "FrotaFusion", "Selecione os quatro packs e a pasta resources.")
            return
        if not messagebox.askyesno(
            "FrotaFusion", "Criar nova categoria [carros]?\n\n"
            "O programa excluirá as variantes repetidas apenas da SAÍDA. "
            "Os quatro arquivos originais serão preservados. "
            "A categoria [carros] existente não será substituída. "
            "Desligue o servidor FiveM antes de executar."
        ):
            return

        def work(notify):
            directory, report = build_fusion(
                [Path(x) for x in inputs], Path(destination), notify)
            r = report["resumo"]
            return (
                f"Fusão pronta em {directory}. "
                f"Spawns distintos: {r['spawns_incluidos']} / "
                f"{r['spawns_distintos_identificados']}; "
                f"variantes repetidas: {len(report['conflitos_de_spawn'])}; "
                f"alertas: {len(report['alertas'])}. "
                "Confira RELATORIO_FROTAFUSION.json antes de executar ensure [carros]."
            )
        self._start_worker(work)

    def _poll(self):
        try:
            while True:
                action, value = self.events.get_nowait()
                if action == "log":
                    self.status.set(value)
                    self.log.configure(state="normal")
                    self.log.insert("end", value + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif action == "downloaded":
                    for var, val in zip(self.paths, value):
                        var.set(val)
                elif action == "done":
                    self.busy = False
                    self.status.set(value)
                    messagebox.showinfo("FrotaFusion", value)
                elif action == "error":
                    self.busy = False
                    self.status.set("Erro: " + value)
                    messagebox.showerror("FrotaFusion", value)
        except queue.Empty:
            pass
        self.after(120, self._poll)


if __name__ == "__main__":
    FrotaFusion().mainloop()
