"""Reparos XML pontuais para metadados de veículos, sem alterar os originais."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path


# Separadores ornamentais malformados como <!-------------------------->
# Não reescrever outros comentários, valores, tags ou encodings.
SEPARATOR_LINE = re.compile(rb"(?m)^([ \t]*)<!-{3,}>[ \t]*(?=\r?$)")


def parse_vehicle_meta(path: Path):
    """Retorna (raiz XML, bytes corrigidos ou None, total de separadores).

    Só altera separadores com hífens em linha isolada e só aceita o reparo
    se o arquivo completo se tornar XML válido. Nunca escreve no original.
    """
    raw = Path(path).read_bytes()
    try:
        return ET.fromstring(raw), None, 0
    except ET.ParseError as initial:
        corrected, count = SEPARATOR_LINE.subn(
            rb"\1<!-- separador -->", raw)
        if count == 0:
            raise ValueError(
                f"vehicles.meta inválido: {path}: {initial}. "
                "Não há correção automática segura para esse erro.") from initial
        try:
            tree = ET.fromstring(corrected)
        except ET.ParseError as after:
            raise ValueError(
                f"vehicles.meta inválido: {path}: {after}. "
                "Os separadores foram avaliados, mas existem outros erros; "
                "o arquivo original não foi modificado.") from after
        return tree, corrected, count
