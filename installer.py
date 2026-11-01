"""Instalação segura dos quatro pacotes de veículos na pasta resources do FiveM.

O usuário escolhe um destino por pack. Cada instalação cria uma categoria
[carros], [carros2], [carros3] ou [carros4] com recursos próprios.
Não instala diretamente no servidor enquanto os originais são modificados.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


GROUPS = {1: "[carros]", 2: "[carros2]", 3: "[carros3]", 4: "[carros4]"}


def destination_for(pack_number: int, selected_directory: Path) -> Path:
    """Retorna a pasta categoria sem criar duas vezes [carrosN]."""
    if pack_number not in GROUPS:
        raise ValueError("Pack desconhecido: escolha de 1 a 4.")
    chosen = Path(selected_directory).expanduser().resolve()
    group = GROUPS[pack_number]
    if chosen.name == group:
        return chosen
    if chosen.name.startswith("[") and chosen.name.endswith("]"):
        raise ValueError(
            f"Você selecionou a categoria {chosen.name}. "
            f"Para o Pack {pack_number}, escolha a pasta resources ou {group}.")
    return chosen / group


def _unique_resource(source: Path, folder_name: str) -> Path:
    candidates = [
        p.parent for p in source.rglob("fxmanifest.lua")
        if p.parent.name == folder_name
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"Não foi possível identificar o recurso {folder_name} "
            f"no pacote extraído ({len(candidates)} encontrado(s)).")
    return candidates[0]


def _copy_tree(source: Path, destination: Path, notify, status: list[int]):
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"Diretório de origem inválido: {source}")
    destination.mkdir(parents=True, exist_ok=False)
    for file in source.rglob("*"):
        if file.is_symlink():
            raise ValueError(f"Link simbólico proibido no pacote: {file}")
        relative = file.relative_to(source)
        out = destination / relative
        if file.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        elif file.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, out)
            if out.stat().st_size != file.stat().st_size:
                raise IOError(f"Cópia incompleta: {file}")
            status[0] += 1
            if status[0] % 250 == 0:
                notify(f"Copiados {status[0]:,} arquivos...")
        else:
            raise ValueError(f"Arquivo de origem não suportado: {file}")


def _write_pack1_by_brand(source: Path, target: Path, notify, status: list[int]):
    data_root, stream_root = source / "data", source / "stream"
    if not data_root.is_dir() or not stream_root.is_dir():
        raise ValueError("Pack 1 está sem data/ ou stream/.")
    data_groups = {p.name.upper(): p for p in data_root.iterdir() if p.is_dir()}
    stream_groups = {p.name.upper(): p for p in stream_root.iterdir() if p.is_dir()}
    if not data_groups or set(data_groups) != set(stream_groups):
        raise ValueError("Pastas data/stream do Pack 1 não correspondem por fabricante.")

    original_manifest = (source / "fxmanifest.lua").read_text(
        encoding="utf-8", errors="replace")
    # Este script consulta a versão original; não é necessário nos sub-recursos.
    manifest = re.sub(
        r"(?im)^\s*server_script\s+['\"]server\.lua['\"]\s*$", "",
        original_manifest)
    names_path = source / "vehicle_names.lua"
    names_text = names_path.read_text(encoding="utf-8", errors="replace") \
        if names_path.is_file() else ""
    entries = []
    for line in names_text.splitlines():
        match = re.search(r"AddTextEntry\(\s*['\"]([^'\"]+)['\"]\s*,", line)
        if match:
            entries.append((match.group(1).lower(), line.strip()))

    installed = []
    for index, group_name in enumerate(sorted(data_groups), start=1):
        if not re.fullmatch(r"\[[A-Z0-9_-]+\]", group_name):
            raise ValueError(f"Fabricante com nome inválido: {group_name}")
        brand = group_name[1:-1]
        name = f"CIV_{brand}"
        brand_root = target / name
        brand_root.mkdir()
        _copy_tree(data_groups[group_name], brand_root / "data" / group_name,
                   notify, status)
        _copy_tree(stream_groups[group_name], brand_root / "stream" / group_name,
                   notify, status)
        models = set()
        for meta_file in data_groups[group_name].rglob("vehicles*.meta"):
            try:
                xml = ET.parse(meta_file).getroot()
            except ET.ParseError as exc:
                raise ValueError(f"vehicles.meta inválido: {meta_file}: {exc}") from exc
            for item in xml.findall(".//InitDatas/Item"):
                for tag in ("modelName", "gameName"):
                    value = item.findtext(tag)
                    if value:
                        models.add(value.strip().lower())
        lines = [line for key, line in entries if key in models]
        script = "CreateThread(function()\n"
        if lines:
            script += "    " + "\n    ".join(lines) + "\n"
        script += "end)\n"
        (brand_root / "vehicle_names.lua").write_text(script, encoding="utf-8")
        (brand_root / "fxmanifest.lua").write_text(manifest, encoding="utf-8")
        installed.append(name)
        notify(f"Pack 1: {index}/{len(data_groups)} fabricantes preparados ({name}).")
    return installed


def _write_pack1_single(source: Path, target: Path, notify, status: list[int]):
    if not (source / "data").is_dir() or not (source / "stream").is_dir():
        raise ValueError("PLOKS_CARS sem as pastas data e stream.")
    _copy_tree(source, target / "PLOKS_CARS", notify, status)
    return ["PLOKS_CARS"]


def _write_pack2(source: Path, target: Path, notify, status: list[int]):
    cars = _unique_resource(source, "Lore_Friendly_Car_Pack")
    _copy_tree(cars, target / "Lore_Friendly_Car_Pack", notify, status)
    installed = ["Lore_Friendly_Car_Pack"]
    # A versão de origem refere-se a versioncheck.lua mas esse arquivo não
    # existe no recurso; remover apenas a diretiva inválida do destino.
    manifest = target / "Lore_Friendly_Car_Pack" / "fxmanifest.lua"
    text = manifest.read_text(encoding="utf-8", errors="replace")
    if not (cars / "versioncheck.lua").is_file():
        updated = re.sub(
            r"(?im)^\s*server_script\s+['\"]versioncheck\.lua['\"]\s*$", "",
            text)
        if updated != text:
            manifest.write_text(updated, encoding="utf-8")
    root = cars.parent / "Lore Friendly Rim Packs"
    if root.is_dir():
        wheels = sorted(
            p for p in root.iterdir()
            if p.is_dir() and (p / "fxmanifest.lua").is_file())
        for i, wheel in enumerate(wheels, start=1):
            name = f"LF_RIMS_{i:02d}"
            _copy_tree(wheel, target / name, notify, status)
            installed.append(name)
    return installed


def _write_pack3(source: Path, target: Path, notify, status: list[int]):
    cars = _unique_resource(source, "LNWK-CARS")
    if not (cars / "data").is_dir() or not (cars / "stream").is_dir():
        raise ValueError("LNWK-CARS sem pastas data e stream.")
    _copy_tree(cars, target / "LNWK-CARS", notify, status)
    # 'Diffirent Handling Types' são alternativas e gerariam conflitos;
    # permanecerão na pasta originais, intactos.
    return ["LNWK-CARS"]


def _write_pack4(source: Path, target: Path, notify, status: list[int]):
    candidates = [
        p.parent for p in source.rglob("fxmanifest.lua")
        if (p.parent / "data").is_dir() and (p.parent / "stream").is_dir()
    ]
    if len(candidates) != 1:
        raise ValueError("Não foi possível encontrar o recurso principal do Pack 4.")
    cars = candidates[0]
    main = target / "LIVID_LF_CARS"
    main.mkdir()
    for filename in ("fxmanifest.lua",):
        shutil.copy2(cars / filename, main / filename)
    for folder in ("data", "stream"):
        _copy_tree(cars / folder, main / folder, notify, status)
    installed = ["LIVID_LF_CARS"]
    sounds_root = cars / "[lf-cars-sounds]"
    if sounds_root.is_dir():
        for folder in sorted(sounds_root.iterdir()):
            if not folder.is_dir() or not (folder / "fxmanifest.lua").is_file():
                continue
            if not re.fullmatch(r"[A-Za-z0-9_-]+", folder.name):
                raise ValueError(f"Nome de recurso de áudio inválido: {folder.name}")
            name = "LIVID_" + folder.name
            _copy_tree(folder, target / name, notify, status)
            installed.append(name)
    return installed


def install_pack(input_dir: Path, pack_number: int, selected_directory: Path,
                 split_pack1: bool = True, notify=lambda _: None):
    """Instala cada pack em sua categoria, sem substituir recursos existentes.

    Retorna (diretório instalado, nomes de recursos instalados).
    Todos os arquivos são copiados para um staging na mesma unidade, depois
    a categoria inteira é promovida ao destino, evitando instalação parcial.
    """
    if pack_number not in GROUPS:
        raise ValueError("O Pack deve ser 1, 2, 3 ou 4.")
    source_root = (Path(input_dir) / f"pacote_{pack_number:02d}").resolve()
    if not source_root.is_dir():
        raise ValueError(f"Pack {pack_number} não foi baixado/extraído: {source_root}")
    selected = Path(selected_directory).expanduser()
    if not selected.is_dir():
        raise ValueError(f"Escolha uma pasta de destino existente: {selected}")
    target = destination_for(pack_number, selected)
    if target.parent.is_symlink():
        raise ValueError("Não é permitido instalar por links simbólicos.")
    if source_root.is_relative_to(target) or target.is_relative_to(source_root):
        raise ValueError("A pasta de destino não pode ficar dentro dos arquivos de origem.")
    if target.exists():
        if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
            raise FileExistsError(
                f"A pasta {target} já contém arquivos. "
                "Por segurança, não substituí nenhum recurso. "
                "Escolha outro destino ou faça backup e libere esta categoria.")
    # Estimativa conservadora de espaço para a cópia; falha antes de começar.
    total_bytes = sum(
        p.stat().st_size for p in source_root.rglob("*") if p.is_file())
    free_space = shutil.disk_usage(target.parent).free
    if free_space < total_bytes + 512 * 1024 * 1024:
        raise OSError(
            f"Espaço insuficiente no destino: livre {free_space / 2**30:.1f} GiB; "
            f"precisamos de cerca de {total_bytes / 2**30:.1f} GiB + margem.")
    temp_parent = Path(tempfile.mkdtemp(
        prefix=".frotalab-instalacao-", dir=str(target.parent)))
    staging = temp_parent / GROUPS[pack_number]
    staging.mkdir()
    copied = [0]
    try:
        notify(f"Preparando Pack {pack_number} para {target}")
        if pack_number == 1:
            source = _unique_resource(source_root, "PLOKS_CARS")
            if split_pack1:
                resources = _write_pack1_by_brand(source, staging, notify, copied)
            else:
                resources = _write_pack1_single(source, staging, notify, copied)
        elif pack_number == 2:
            resources = _write_pack2(source_root, staging, notify, copied)
        elif pack_number == 3:
            resources = _write_pack3(source_root, staging, notify, copied)
        else:
            resources = _write_pack4(source_root, staging, notify, copied)

        if not resources:
            raise ValueError("Nenhum recurso identificado para instalação.")
        for name in resources:
            if not (staging / name / "fxmanifest.lua").is_file():
                raise ValueError(f"Recurso sem fxmanifest.lua: {name}")
        description = (
            f"FrotaLab - Pack {pack_number}\n"
            f"Destino: {target}\n"
            f"Recursos: {', '.join(resources)}\n\n"
            "Não use ensure [carros] para iniciar tudo sem testar.\n"
            "Inicie cada recurso individualmente pelo console:\n"
            f"refresh\nensure {resources[0]}\n\n"
            "ATENÇÃO: existem nomes de spawn repetidos entre os quatro packs.\n"
            "Adicionar todos ao mesmo servidor sem revisão pode causar conflitos.\n"
            "O FrotaLab não alterou modelos, texturas ou arquivos originais.\n")
        (staging / "INSTRUCOES_FROTALAB.txt").write_text(
            description, encoding="utf-8")
        # Verifique novamente para não sobrescrever categoria criada enquanto copiava.
        if target.exists():
            if any(target.iterdir()):
                raise FileExistsError(f"Destino ocupado durante instalação: {target}")
            target.rmdir()
        staging.rename(target)
        notify(f"Pack {pack_number} instalado: {len(resources)} recursos, "
               f"{copied[0]:,} arquivos em {target}")
        return target, resources
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)
