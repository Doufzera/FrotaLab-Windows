"""FrotaFusion: consolida quatro packs FiveM por nome real de spawn.

Executa no PC do usuário, usando ZIPs ou diretórios originais. Nunca altera
nem remove a origem. Escolhe uma variante por modelName, preservando o bundle
completo (metadados, tuning e stream), áudios e recursos auxiliares.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SOURCES = (
    ("PLOKMJNB", "https://codeload.github.com/PLOKMJNB/FiveM-Civ-Car-Pack/zip/refs/heads/master"),
    ("SpiritsCreations", "https://codeload.github.com/SpiritsCreations/FiveM-Lore-Friendly-Pack/zip/refs/heads/main"),
    ("Aweetumn-LLC", "https://codeload.github.com/Aweetumn-LLC/FiveM-Lorefriendly-Vehicles/zip/refs/heads/main"),
    ("LividDS", "https://codeload.github.com/LividDS/Lorefriendly-Cars/zip/refs/tags/pack.0.5"),
)
RESOURCE_NAMES = ("PLOKS_CARS", "Lore_Friendly_Car_Pack", "LNWK-CARS", "LIVID_LF_CARS")
MAX_ARCHIVE_EXPANDED = 30 * 1024 ** 3
SEPARATOR_LINE = re.compile(rb"(?m)^([ \t]*)<!-{3,}>[ \t]*(?=\r?$)")
RE_WS = re.compile(r"[^a-z0-9]+")


def _normal(value):
    return RE_WS.sub("", value.lower())


def _parse_xml(path: Path):
    raw = path.read_bytes()
    try:
        return ET.fromstring(raw), None
    except ET.ParseError as exc:
        repaired, count = SEPARATOR_LINE.subn(rb"\1<!-- separador -->", raw)
        if not count:
            raise ValueError(f"XML inválido: {path}: {exc}") from exc
        try:
            return ET.fromstring(repaired), repaired
        except ET.ParseError as more:
            raise ValueError(f"XML inválido após reparo pontual: {path}: {more}") from more


def _relative_safe(raw: str):
    name = raw.replace("\\", "/")
    parts = name.split("/")
    if name.startswith("/") or any(p in ("", ".", "..") for p in parts if p != parts[-1]) or ".." in parts:
        raise ValueError(f"Caminho inseguro no ZIP: {raw}")
    if parts and (":" in parts[0] or parts[0].startswith("~")):
        raise ValueError(f"Caminho inseguro no ZIP: {raw}")
    return parts


def unpack_zip(archive: Path, dest: Path, notify=lambda _: None):
    """Extrai com proteção básica de traversal, links e ZIP bombs."""
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        total = 0
        for info in entries:
            _relative_safe(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"Link simbólico proibido: {info.filename}")
            if info.flag_bits & 1:
                raise ValueError(f"ZIP criptografado: {info.filename}")
            if info.file_size > 4 * 1024 ** 3:
                raise ValueError(f"Arquivo individual grande demais: {info.filename}")
            total += info.file_size
            if total > MAX_ARCHIVE_EXPANDED:
                raise ValueError(f"ZIP ultrapassou limite de tamanho: {archive}")
        for index, info in enumerate(entries):
            if info.is_dir():
                continue
            out = dest.joinpath(*_relative_safe(info.filename))
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as inp, out.open("wb") as dst:
                shutil.copyfileobj(inp, dst, length=1024 * 1024)
            if info.file_size != out.stat().st_size:
                raise IOError(f"Extração incompleta: {info.filename}")
            if (index + 1) % 1000 == 0:
                notify(f"{archive.name}: {index + 1:,} entradas processadas")


def download_archives(directory: Path, notify=lambda _: None):
    """Baixa os quatro arquivos completos. Reaproveita ZIP íntegro existente."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for idx, (_, url) in enumerate(SOURCES, 1):
        path = directory / f"pack_{idx:02d}.zip"
        if path.is_file():
            try:
                with zipfile.ZipFile(path) as z:
                    if z.testzip() is None:
                        paths.append(path)
                        notify(f"Pacote {idx}: ZIP local íntegro reaproveitado.")
                        continue
            except (OSError, zipfile.BadZipFile):
                pass
            raise ValueError(f"ZIP local existente e inválido: {path}. Faça backup e remova-o.")
        temp = path.with_suffix(".partial")
        notify(f"Baixando Pack {idx}/4...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FrotaFusion/1.0"})
            with urllib.request.urlopen(req, timeout=120) as response, temp.open("wb") as out:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
            with zipfile.ZipFile(temp) as z:
                bad = z.testzip()
                if bad is not None:
                    raise ValueError(f"CRC inválido em {bad}")
            temp.replace(path)
            paths.append(path)
        finally:
            temp.unlink(missing_ok=True)
    return paths


def _find_main(source: Path, idx: int):
    source = Path(source).resolve()
    if not source.is_dir():
        raise ValueError(f"Origem {idx} não existe: {source}")
    if idx < 4:
        names = RESOURCE_NAMES[:3]
        matches = [p for p in source.rglob(names[idx - 1])
                   if p.is_dir() and (p / "fxmanifest.lua").is_file()
                   and (p / "data").is_dir() and (p / "stream").is_dir()]
    else:
        matches = [p for p in (source, *source.glob("*"), *source.glob("*/*"))
                   if p.is_dir() and (p / "fxmanifest.lua").is_file()
                   and (p / "data").is_dir() and (p / "stream").is_dir()]
    if len(matches) != 1:
        raise ValueError(f"Pack {idx}: esperado um recurso principal, encontrados {len(matches)} em {source}")
    return matches[0]


@dataclass(eq=False)
class Bundle:
    pack: int
    data_dir: Path
    stream_dir: Path | None
    rel_data: Path
    rel_stream: Path | None
    spawns: tuple[str, ...]
    meta_corrections: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    bytes_total: int = 0
    texture_max: int = 0
    model_ok: bool = False
    texture_ok: bool = False
    extra_meta: int = 0

    def describe(self):
        return f"P{self.pack}:{self.rel_data.as_posix()}"

    def ranking(self):
        # Requisito mais importante: modelo válido e conjunto de textura.
        # Menor custo estimado só desempata conjuntos completos.
        # Limite de 48 MiB por textura favorecido: não é garantia de runtime.
        return (
            0 if self.model_ok else 1,
            0 if self.texture_ok else 1,
            0 if self.extra_meta >= 2 else 1,
            0 if self.texture_max <= 48 * 1024 * 1024 else 1,
            self.texture_max,
            self.bytes_total,
            self.pack,
            str(self.rel_data).lower(),
        )


def _matching_stream(data_rel: Path, stream_root: Path, spawns: tuple[str, ...],
                     folders: list[Path]):
    preferred = stream_root / data_rel
    if preferred.is_dir():
        return preferred
    key = _normal(data_rel.as_posix())
    matches = [f for f in folders if _normal(f.relative_to(stream_root).as_posix()) == key]
    if len(matches) == 1:
        return matches[0]
    matches = []
    spawn_set = set(spawns)
    for f in folders:
        existing = {p.stem.lower() for p in f.rglob("*.yft")
                    if not p.stem.lower().endswith("_hi")}
        if spawn_set & existing:
            matches.append((len(spawn_set & existing), f))
    if matches:
        matches.sort(key=lambda v: (-v[0], len(v[1].parts), str(v[1]).lower()))
        if len(matches) == 1 or matches[0][0] > matches[1][0]:
            return matches[0][1]
    return None


def scan_pack(source_root: Path, pack_id: int, notify=lambda _: None):
    main = _find_main(source_root, pack_id)
    data_root, stream_root = main / "data", main / "stream"
    stream_folders = sorted({p.parent for p in stream_root.rglob("*.yft")})
    groups = sorted({p.parent for p in data_root.rglob("vehicles*.meta")})
    bundles, errors = [], []
    for i, directory in enumerate(groups, 1):
        metas = list(directory.glob("vehicles*.meta"))
        spawns = set()
        corrections = {}
        for meta in metas:
            try:
                xml, patched = _parse_xml(meta)
                if patched is not None:
                    corrections[meta.name] = patched
                for it in xml.findall(".//InitDatas/Item"):
                    v = it.findtext("modelName")
                    if v and re.fullmatch(r"[A-Za-z0-9_-]+", v.strip()):
                        spawns.add(v.strip().lower())
            except ValueError as exc:
                errors.append(str(exc))
        if not spawns:
            errors.append(f"Sem spawn reconhecido: P{pack_id}:{directory.relative_to(data_root)}")
            continue
        spawn_t = tuple(sorted(spawns))
        data_rel = directory.relative_to(data_root)
        st = _matching_stream(data_rel, stream_root, spawn_t, stream_folders)
        if st is None:
            errors.append(f"Sem stream correspondente: P{pack_id}:{data_rel} (spawns={','.join(spawn_t)})")
        streams = [p for p in st.rglob("*") if p.is_file()] if st else []
        textures = [p.stat().st_size for p in streams if p.suffix.lower() == ".ytd"]
        base_yfts = {p.stem.lower() for p in streams if p.suffix.lower() == ".yft"}
        model_ok = any(n in base_yfts for n in spawn_t)
        if not model_ok:
            errors.append(f"Modelo YFT base não confirmado: P{pack_id}:{data_rel}")
        dat_files = [p for p in directory.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in streams + dat_files)
        other_meta = len([p for p in dat_files if p.suffix.lower() == ".meta"])
        bundles.append(Bundle(
            pack_id, directory, st, data_rel,
            st.relative_to(stream_root) if st else None,
            spawn_t, corrections, [],
            total, max(textures, default=0), model_ok, bool(textures), other_meta,
        ))
        if i % 50 == 0:
            notify(f"Pack {pack_id}: {i}/{len(groups)} grupos examinados")
    notify(f"Pack {pack_id}: {len(bundles)} veículos/grupos, {len(errors)} alertas")
    return main, bundles, errors


def select_bundles(bundles: list[Bundle]):
    """Resolve conflitos por spawn sem dividir metadados ou tuning do veículo."""
    by_spawn = defaultdict(list)
    viable = defaultdict(list)
    for bundle in bundles:
        for spawn in bundle.spawns:
            by_spawn[spawn].append(bundle)
            # Não declare como instalável um carro sem arquivo YFT base.
            if bundle.stream_dir is not None and bundle.model_ok:
                viable[spawn].append(bundle)
    # Priorizar grupos com modelos únicos, para não descartar um carro exclusivo
    # ao escolher uma alternativa que tem o mesmo spawn de outro pacote.
    uniques = {b for spawn, group in viable.items() if len(group) == 1 for b in group}
    selected, claimed = [], set()
    for b in sorted(uniques, key=lambda x: x.ranking()):
        if any(s in claimed for s in b.spawns):
            continue
        selected.append(b)
        claimed.update(b.spawns)
    # Entre as opções restantes, escolher completude e menor peso estimado.
    for spawn in sorted(by_spawn):
        if spawn in claimed:
            continue
        candidates = [b for b in viable[spawn] if not set(b.spawns) & claimed]
        if not candidates:
            continue
        b = min(candidates, key=lambda x: x.ranking())
        selected.append(b)
        claimed.update(b.spawns)
    missing = sorted(set(by_spawn) - claimed)
    choices = {spawn: next((b for b in selected if spawn in b.spawns), None)
               for spawn in by_spawn}
    duplicates = []
    for spawn, items in sorted(by_spawn.items()):
        if len(items) > 1:
            best = choices[spawn]
            duplicates.append({
                "spawn": spawn,
                "mantido": best.describe() if best else None,
                "removidos_da_saida": [b.describe() for b in items if b is not best],
                "alternativas": [
                    {"origem": b.describe(), "bytes_estimados": b.bytes_total,
                     "maior_ytd_bytes": b.texture_max, "modelo_yft": b.model_ok,
                     "tem_textura": b.texture_ok, "metas": b.extra_meta}
                    for b in sorted(items, key=lambda x: x.ranking())
                ],
            })
    return selected, missing, duplicates


def _copytree(src: Path, dst: Path, repairs=None):
    repairs = repairs or {}
    if src.is_symlink():
        raise ValueError(f"Link simbólico na origem: {src}")
    for p in src.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"Link simbólico na origem: {p}")
        if p.is_dir():
            continue
        relative = p.relative_to(src)
        out = dst / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() in repairs:
            out.write_bytes(repairs[relative.as_posix()])
        else:
            if out.exists():
                if out.stat().st_size != p.stat().st_size:
                    raise ValueError(f"Colisão de arquivos na saída: {out}")
                continue
            shutil.copy2(p, out)


def build_fusion(inputs: list[Path], resources_dir: Path,
                 notify=lambda _: None):
    """Cria resources/[carros], sem alterar originais ou sobrescrever categoria.

    Inputs: 4 diretórios originais ou ZIPs dos downloads públicos.
    Retorna (pasta, relatório). Executar com servidor FiveM parado.
    """
    if len(inputs) != 4:
        raise ValueError("Informe os quatro packs originais na ordem 1, 2, 3, 4.")
    resource_root = Path(resources_dir).expanduser().resolve()
    if not resource_root.is_dir():
        raise ValueError(f"Não existe a pasta resources: {resources_dir}")
    if resource_root.name == "[carros]":
        resource_root = resource_root.parent
    target = resource_root / "[carros]"
    if target.exists() and (target.is_symlink() or any(target.iterdir())):
        raise FileExistsError(
            f"Categoria {target} já possui conteúdo. Faça backup e mova-a PARA FORA "
            "da pasta resources antes de criar uma nova fusão.")
    tmp = Path(tempfile.mkdtemp(prefix=".frotafusion-", dir=resource_root))
    staging = tmp / "[carros]"
    staging.mkdir()
    roots = []
    try:
        for index, inp in enumerate(inputs, 1):
            inp = Path(inp).expanduser().resolve()
            if not inp.exists():
                raise FileNotFoundError(f"Pack {index}: origem não encontrada: {inp}")
            if inp.is_file():
                if inp.suffix.lower() != ".zip":
                    raise ValueError(f"Pack {index}: informe uma pasta ou um ZIP.")
                unpack_to = tmp / f"unpack_{index}"
                unpack_to.mkdir()
                notify(f"Descompactando Pack {index}...")
                unpack_zip(inp, unpack_to, notify)
                roots.append(unpack_to)
            else:
                roots.append(inp)
        mains, bundles, issues = [], [], []
        for i, p in enumerate(roots, 1):
            notify(f"Analisando Pack {i}...")
            main, found, warnings = scan_pack(p, i, notify)
            mains.append(main)
            bundles.extend(found)
            issues.extend(warnings)
        if not bundles:
            raise ValueError("Nenhum veículo com modelName válido foi encontrado.")
        chosen, missed, duplicates = select_bundles(bundles)
        if missed:
            issues.append(f"Spawns sem conjunto YFT válido/sem grupo selecionável: {', '.join(missed)}")
        by_pack = defaultdict(list)
        for b in chosen:
            by_pack[b.pack].append(b)
        for idx, main in enumerate(mains, 1):
            dest = staging / RESOURCE_NAMES[idx - 1]
            dest.mkdir()
            # Mantém os manifestos/scripts originais relativos aos arquivos de
            # cada pack. Nunca copia as pastas data/stream originais inteiras.
            for item in main.iterdir():
                if item.name in ("data", "stream", "[lf-cars-sounds]"):
                    continue
                if item.is_file():
                    shutil.copy2(item, dest / item.name)
                elif item.is_dir():
                    _copytree(item, dest / item.name)
            if idx == 2:
                # Sons referenciados por fxmanifest podem servir veículos de
                # outros packs, por isso são conservados intactos.
                pass
            for number, bundle in enumerate(by_pack[idx], 1):
                rel = bundle.rel_data
                patches = {
                    n: data for n, data in bundle.meta_corrections.items()
                }
                _copytree(bundle.data_dir, dest / "data" / rel, patches)
                if bundle.stream_dir is not None:
                    _copytree(bundle.stream_dir, dest / "stream" / bundle.rel_stream)
                if number % 25 == 0:
                    notify(f"Pack {idx}: {number}/{len(by_pack[idx])} conjuntos copiados")
            if not (dest / "fxmanifest.lua").is_file():
                raise ValueError(f"Pack {idx} sem fxmanifest.lua.")
        # Packs auxiliares: rodas e sons, preservados com seus manifestos.
        wheel_root = mains[1].parent / "Lore Friendly Rim Packs"
        if wheel_root.is_dir():
            for count, wheel in enumerate(sorted(wheel_root.iterdir()), 1):
                if wheel.is_dir() and (wheel / "fxmanifest.lua").is_file():
                    _copytree(wheel, staging / f"FROTA_RODAS_{count:02d}")
        sound_root = mains[3] / "[lf-cars-sounds]"
        if sound_root.is_dir():
            for sound in sorted(sound_root.iterdir()):
                if not sound.is_dir() or not (sound / "fxmanifest.lua").is_file():
                    continue
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", sound.name):
                    raise ValueError(f"Nome de som inválido: {sound.name}")
                _copytree(sound, staging / ("FROTA_SOM_" + sound.name))
        children = [p for p in staging.iterdir() if p.is_dir()]
        for child in children:
            if not (child / "fxmanifest.lua").is_file():
                raise ValueError(f"Recurso inválido: {child}")
        # Colisões de nomes .yft/.ytd entre carros mantidos: não remover
        # por nome de arquivo, pois peças de tuning podem ser compartilhadas.
        assets = defaultdict(set)
        for b in chosen:
            if b.stream_dir is None:
                continue
            for p in b.stream_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".yft", ".ytd", ".ydr"):
                    assets[p.name.lower()].add(b.describe())
        asset_collisions = [
            {"arquivo": name, "recursos": sorted(groups)}
            for name, groups in sorted(assets.items()) if len(groups) > 1
        ]
        report = {
            "resumo": {
                "candidatos": len(bundles),
                "grupos_mantidos": len(chosen),
                "spawns_distintos_identificados": len({s for b in bundles for s in b.spawns}),
                "spawns_incluidos": len({s for b in chosen for s in b.spawns}),
                "spawns_sem_selecao": missed,
                "arquivos_stream_nome_repetido": len(asset_collisions),
                "recursos_na_categoria": len(children),
                "metodo": "completude + tamanho estimado dos arquivos (sem medição de runtime)",
            },
            "conflitos_de_spawn": duplicates,
            "conflitos_de_arquivos_stream": asset_collisions,
            "alertas": issues,
            "selecionados": [
                {"origem": b.describe(), "spawns": list(b.spawns),
                 "custo_bytes": b.bytes_total, "maior_ytd_bytes": b.texture_max,
                 "modelo_yft": b.model_ok, "tem_textura": b.texture_ok}
                for b in chosen
            ],
        }
        (staging / "RELATORIO_FROTAFUSION.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (staging / "LEIA-ME-FROTAFUSION.txt").write_text(
            "FROTafusion - 4 packs em uma categoria FiveM\n\n"
            "1. Pare o FXServer antes de copiar/instalar recursos.\n"
            "2. Faça backup de categorias antigas, sem deixá-las em resources.\n"
            "3. No server.cfg, use somente uma linha: ensure [carros]\n"
            "4. Remova entradas antigas de PLOKS_CARS, LNWK-CARS etc.\n"
            "5. O comando ensure em recursos já iniciados pode reiniciá-los.\n"
            "6. Se ocorrer svMain hung, não insista na inicialização massiva.\n"
            "7. Confira RELATORIO_FROTAFUSION.json e os alertas de spawns.\n"
            "8. Comparação por peso é estimativa, não garante FPS nem qualidade.\n"
            "9. Os originais nunca foram deletados ou alterados.\n",
            encoding="utf-8")
        # A pasta category permanece intacta se qualquer etapa anterior falhar.
        if target.exists():
            if any(target.iterdir()):
                raise FileExistsError(f"Categoria ocupada durante operação: {target}")
            target.rmdir()
        staging.rename(target)
        notify(f"Concluído: {len(chosen)} grupos, {len(duplicates)} spawns repetidos, "
               f"{len(children)} recursos; alertas={len(issues)}.")
        return target, report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
