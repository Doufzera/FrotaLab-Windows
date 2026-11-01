import concurrent.futures
import csv
import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

OUT = Path("inventario_veiculos")
OUT.mkdir(parents=True, exist_ok=True)
REPOS = [
 ("FiveM-Civ-Car-Pack", "PLOKMJNB", "FiveM-Civ-Car-Pack", "master", "PLOKS_CARS/data/"),
 ("FiveM-Lore-Friendly-Pack", "SpiritsCreations", "FiveM-Lore-Friendly-Pack", "main", "Lore_Friendly_Car_Pack/data/"),
 ("FiveM-Lorefriendly-Vehicles", "Aweetumn-LLC", "FiveM-Lorefriendly-Vehicles", "main", "LNWK-CARS/data/"),
 ("Lorefriendly-Cars", "LividDS", "Lorefriendly-Cars", "pack.0.5", "data/")
]
COLS = ["ID", "Nome do veículo", "Nome de spawn", "Modelo", "Marca", "Pacote de origem", "Spawn repetido", "Caminho vehicles.meta", "gameName", "Fonte do nome"]
BRANDS = ["Mercedes-Benz", "Rolls-Royce", "Aston Martin", "Land Rover", "Range Rover", "W Motors", "Alfa Romeo", "Acura", "Audi", "Bentley", "BMW", "Bugatti", "Cadillac", "Chevrolet", "Dacia", "Dodge", "Ferrari", "Ford", "Honda", "Hyundai", "Jaguar", "Jeep", "Koenigsegg", "Lamborghini", "Lexus", "Lotus", "Maserati", "Mazda", "McLaren", "Mercedes", "Mitsubishi", "Nissan", "Peugeot", "Porsche", "Renault", "Subaru", "Suzuki", "Tesla", "Toyota", "Volkswagen", "Volvo", "Annis", "Benefactor", "Bravado", "Karin", "Dinka", "Ubermacht", "Vapid", "Obey", "Pegassi", "Grotti", "Truffade", "Pfister", "Progen", "Invetero", "Declasse", "Albany", "Dewbauchee", "Ocelot", "Maibatsu", "Shitzu", "Vulcar", "Coil", "Lampadati", "Enus", "Schyster", "Imponte", "Weeny", "Nagasaki", "Bordeaux", "Zircoflow", "Vulgar"]
HEAD = {"User-Agent": "FrotaLab-Catalog/1.0"}
if os.environ.get("GH_TOKEN"):
    HEAD["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]

def get(url, raw=False):
    last = None
    for attempt in range(4):
        try:
            headers = dict(HEAD)
            if "raw.githubusercontent.com" in url:
                headers.pop("Authorization", None)
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=75) as resp:
                value = resp.read()
            return value if raw else value.decode("utf-8-sig")
        except Exception as err:
            last = err
            time.sleep(1.7 * (attempt + 1))
    raise RuntimeError(str(last))

def get_repo_paths(repo):
    title, owner, name, ref, prefix = repo
    url = "https://api.github.com/repos/{}/{}/git/trees/{}?recursive=1".format(owner, name, urllib.parse.quote(ref, safe=""))
    response = json.loads(get(url))
    if response.get("truncated"):
        raise RuntimeError("Árvore truncada: " + title)
    paths = [f["path"] for f in response["tree"] if f["type"] == "blob" and f["path"].startswith(prefix) and f["path"].lower().endswith("/vehicles.meta")]
    print(title, "arquivos vehicles.meta:", len(paths), flush=True)
    return paths

def names_from_readme(repo):
    _, owner, name, ref, _ = repo
    if owner != "PLOKMJNB":
        return {}
    try:
        txt = get("https://raw.githubusercontent.com/{}/{}/{}/README.md".format(owner, name, ref))
        names = {}
        for ln in txt.splitlines():
            if not ln.startswith("|"):
                continue
            cells = [i.strip() for i in ln.strip("|").split("|")]
            if len(cells) < 3:
                continue
            spawn = cells[1].strip(" *").lower()
            human = re.sub("<[^>]*>", "", cells[0]).replace("*", "").strip()
            if re.fullmatch("[a-zA-Z0-9_]+", spawn) and human and spawn not in {"spawn", "code"}:
                names[spawn] = human
        return names
    except Exception as err:
        print("Falha README:", err, flush=True)
        return {}

def brand_of(path, make, human):
    for seg in path.split("/"):
        if seg.startswith("[") and seg.endswith("]"):
            return seg[1:-1].replace("_", " ").title()
    make = (make or "").strip()
    for brand in sorted(BRANDS, key=len, reverse=True):
        if make.lower() == brand.lower() or make.lower().startswith(brand.lower() + " "):
            return brand
    for brand in sorted(BRANDS, key=len, reverse=True):
        if human.lower().startswith(brand.lower() + " "):
            return brand
    if make.isupper() and 2 <= len(make) <= 24 and " " not in make and make.lower() != "null":
        return make.title()
    return "Não identificado"

def read_meta(args):
    repo, path, names = args
    title, owner, name, ref, _ = repo
    url = "https://raw.githubusercontent.com/{}/{}/{}/{}".format(owner, name, urllib.parse.quote(ref, safe=""), urllib.parse.quote(path, safe="/"))
    raw = get(url, raw=True)
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//InitDatas/Item"):
        spawn = (item.findtext("modelName") or "").strip()
        if not spawn or spawn.lower() == "null":
            continue
        game = (item.findtext("gameName") or "").strip()
        make = (item.findtext("vehicleMakeName") or "").strip()
        folder = path.split("/")[-2].replace("_", " ")
        readme_name = names.get(spawn.lower())
        if readme_name:
            human, status = readme_name, "README"
        elif folder.lower() != spawn.lower() and len(folder) > 3:
            human, status = folder, "Nome da pasta"
        elif make and not make.isupper() and make.lower() != spawn.lower() and len(make) > len(spawn):
            human, status = make, "vehicles.meta"
        else:
            human, status = (game if game and game.lower() != spawn.lower() else spawn), "Sem nome descritivo"
        brand = brand_of(path, make, human)
        model = human
        if brand != "Não identificado" and human.lower().startswith(brand.lower() + " "):
            model = human[len(brand):].strip(" -")
        rows.append({"Nome do veículo": human, "Nome de spawn": spawn, "Modelo": model or spawn, "Marca": brand, "Pacote de origem": title, "Caminho vehicles.meta": path, "gameName": game, "Fonte do nome": status})
    return rows

def sheet(wb, name, columns, rows):
    ws = wb.create_sheet(name)
    ws.append(columns)
    for r in rows:
        ws.append([r.get(k, "") for k in columns])
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = "A1:{}{}".format(get_column_letter(len(columns)), ws.max_row)
    ws.sheet_view.showGridLines = False
    width = {"ID":9, "Nome do veículo":39, "Nome de spawn":24, "Modelo":33, "Marca":24, "Pacote de origem":34, "Spawn repetido":20, "Caminho vehicles.meta":82, "gameName":24, "Fonte do nome":25, "Caminho":80, "Erro":100}
    for idx, col in enumerate(columns,1):
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = width.get(col, 24)
        cell = ws.cell(1,idx)
        cell.fill = PatternFill("solid", fgColor="133246")
        cell.font = Font(name="Aptos", color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True)
    ws.row_dimensions[1].height = 30
    for i in range(2, ws.max_row+1):
        if i % 2 == 0:
            for j in range(1,len(columns)+1):
                ws.cell(i,j).fill = PatternFill("solid", fgColor="EFF6F8")

def write_csv(filename, columns, rows):
    with (OUT / filename).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def main():
    results, failures = [], []
    for repo in REPOS:
        paths = get_repo_paths(repo)
        names = names_from_readme(repo)
        args = [(repo, p, names) for p in paths]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            tasks = {executor.submit(read_meta, arg):arg[1] for arg in args}
            for future in concurrent.futures.as_completed(tasks):
                path = tasks[future]
                try:
                    results.extend(future.result())
                except Exception as err:
                    failures.append({"Pacote de origem": repo[0], "Caminho": path, "Erro": str(err)})
        for failure in failures:
            print("ERRO_META:", json.dumps(failure, ensure_ascii=False), flush=True)
        print("Total", len(results), "erros", len(failures), flush=True)
    if not results:
        raise RuntimeError("Não foram encontrados veículos: abortando planilha vazia")
    results.sort(key=lambda x:(x["Marca"].lower(),x["Modelo"].lower(),x["Nome de spawn"].lower(),x["Pacote de origem"]))
    frequencies = Counter(r["Nome de spawn"].lower() for r in results)
    seen, unique = set(), []
    for i, r in enumerate(results, 1):
        r["ID"] = i
        n = frequencies[r["Nome de spawn"].lower()]
        r["Spawn repetido"] = "SIM ({} registros)".format(n) if n > 1 else "Não"
        if r["Nome de spawn"].lower() not in seen:
            unique.append(r)
            seen.add(r["Nome de spawn"].lower())
    repeated = [r for r in results if r["Spawn repetido"].startswith("SIM")]
    wb = Workbook()
    intro = wb.active
    intro.title = "Resumo"
    for row in [
        ["FROTALAB | CATÁLOGO DE VEÍCULOS", ""],
        ["Data da consulta UTC", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")],
        ["Repositórios consultados", len(REPOS)],
        ["Total de registros", len(results)],
        ["Spawns distintos", len(unique)],
        ["Registros com spawn repetido", len(repeated)],
        ["Arquivos META que falharam", len(failures)],
        ["Aviso", "Mesmo spawn não significa mesmo visual nem mesmo arquivo binário."],
        ["Aviso", "Aba de spawns únicos é catálogo e NÃO seleciona a versão mais otimizada."],
        ["Fonte", "Dados extraídos de vehicles.meta, caminhos de pastas e README."],
        ["Nota", "Marca ou modelo não identificados precisam de revisão; sem imagens/benchmark."],
    ]:
        intro.append(row)
    intro.merge_cells("A1:D1")
    intro["A1"].font = Font(size=20, bold=True, color="38BFA4")
    intro.column_dimensions["A"].width = 40
    intro.column_dimensions["B"].width = 100
    for idx in range(2,intro.max_row+1):
        intro.cell(idx,1).font = Font(bold=True, color="154C60")
    sheet(wb,"Todos os veículos",COLS,results)
    sheet(wb,"Spawns únicos",COLS,unique)
    sheet(wb,"Spawns repetidos",COLS,repeated)
    sheet(wb,"Falhas de leitura",["Pacote de origem","Caminho","Erro"],failures)
    wb.save(OUT / "FrotaLab_Catalogo_Veiculos.xlsx")
    write_csv("FrotaLab_Todos_Veiculos.csv",COLS,results)
    write_csv("FrotaLab_Spawns_Unicos.csv",COLS,unique)
    write_csv("FrotaLab_Falhas.csv",["Pacote de origem","Caminho","Erro"],failures)
    summary = {"registros":len(results),"spawns_unicos":len(unique),"registros_repetidos":len(repeated),"falhas_meta":len(failures)}
    (OUT/"RESUMO.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RESULTADO", summary, flush=True)

if __name__ == "__main__":
    main()
