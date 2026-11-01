"""Gerador seguro de inicialização escalonada para os veículos do Pack 1.

Gera um recurso FiveM em resources/frotalab_loader sem editar server.cfg,
sem reiniciar o FXServer e sem modificar os veículos instalados.
"""
from __future__ import annotations

import re
from pathlib import Path

LOADER_NAME = "frotalab_loader"
CAR_RESOURCE_PATTERN = re.compile(r"^CIV_[A-Z0-9_-]+$")

FXMANIFEST = """fx_version 'cerulean'
game 'gta5'

author 'FrotaLab'
description 'Iniciador escalonado e opcional dos fabricantes do Pack 1'
server_scripts {
    'config.lua',
    'server.lua'
}
"""

SERVER_LUA = r"""local prefix = "[FrotaLab Loader] "

local function say(message)
    print(prefix .. message)
end

local function pause(milliseconds)
    Wait(math.max(0, math.floor(tonumber(milliseconds) or 0)))
end

local function waitForResource(name, maxTime)
    local elapsed = 0
    while elapsed < maxTime do
        local state = GetResourceState(name)
        if state == "started" then
            return true, state
        end
        if state == "missing" or state == "unknown" then
            return false, state
        end
        pause(500)
        elapsed = elapsed + 500
    end
    return GetResourceState(name) == "started", GetResourceState(name)
end

CreateThread(function()
    local items = Config.StartAll and Config.Resources or Config.InitialResources
    if not items or #items == 0 then
        say("Nenhum fabricante habilitado.")
        return
    end
    say(("Modo %s, %d recurso(s), intervalo %d ms."):format(
        Config.StartAll and "todos" or "teste", #items, Config.IntervalMs))
    pause(Config.InitialDelayMs)
    local started, skipped, errors = 0, 0, 0
    for i, name in ipairs(items) do
        if type(name) ~= "string" or not name:match("^CIV_[A-Z0-9_%-]+$") then
            say("Nome invalido ignorado na posicao " .. tostring(i))
            errors = errors + 1
        else
            local state = GetResourceState(name)
            if state == "started" then
                say(("%d/%d: %s ja iniciado, sem reiniciar."):format(i, #items, name))
                skipped = skipped + 1
            elseif state == "missing" or state == "unknown" then
                say(("%d/%d: %s nao encontrado, ignorando."):format(i, #items, name))
                errors = errors + 1
            else
                if state == "starting" or state == "stopping" then
                    say(name .. " ainda em transicao: aguardando.")
                    local ok = waitForResource(name, Config.MaxWaitMs)
                    if ok then
                        skipped = skipped + 1
                    else
                        say(name .. " nao ficou pronto; sem reiniciar automaticamente.")
                        errors = errors + 1
                    end
                elseif state == "stopped" or state == "uninitialized" then
                    say(("%d/%d: iniciando %s..."):format(i, #items, name))
                    local ok = StartResource(name)
                    if ok then
                        local ready, newState = waitForResource(name, Config.MaxWaitMs)
                        if ready then
                            started = started + 1
                            say(name .. " iniciado.")
                        else
                            say(name .. " nao confirmou inicio (" .. tostring(newState) .. ").")
                            errors = errors + 1
                        end
                    else
                        say("Falha ao iniciar " .. name)
                        errors = errors + 1
                    end
                else
                    say(name .. " estado inesperado: " .. tostring(state))
                    errors = errors + 1
                end
            end
        end
        -- Nunca inicie dezenas de fabricantes em um unico frame.
        if i < #items then
            pause(Config.IntervalMs)
        end
    end
    say(("Concluido: iniciados=%d, ja ativos=%d, falhas=%d."):format(
        started, skipped, errors))
end)
"""


def discover_brands(selected_dir: Path):
    """Procura os recursos CIV_* do Pack 1 na categoria resources/[carros]."""
    chosen = Path(selected_dir).expanduser()
    if not chosen.exists() or not chosen.is_dir():
        raise ValueError(f"Pasta de destino inexistente: {chosen}")
    chosen = chosen.resolve()
    if chosen.name == "[carros]":
        resources_root = chosen.parent
    elif chosen.name.lower() == "resources" or (chosen / "[carros]").is_dir():
        resources_root = chosen
    else:
        raise ValueError("Escolha a pasta resources ou a categoria resources/[carros].")
    category = resources_root / "[carros]"
    if not category.is_dir():
        raise ValueError("A categoria [carros] não existe no destino selecionado.")
    items = []
    for entry in category.iterdir():
        if not entry.is_dir() or not CAR_RESOURCE_PATTERN.fullmatch(entry.name):
            continue
        if entry.is_symlink():
            raise ValueError(f"Recurso com link simbólico: {entry}")
        if not (entry / "fxmanifest.lua").is_file():
            raise ValueError(f"Recurso sem fxmanifest.lua: {entry}")
        items.append(entry.name)
    items.sort()
    if not items:
        raise ValueError(
            "Nenhuma pasta CIV_* encontrada em [carros]. "
            "Instale o Pack 1 com divisão por fabricantes primeiro.")
    return resources_root, items


def _lua_string(value: str):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def make_config(resources: list[str], start_all: bool = False, interval_seconds: int = 15):
    if not resources or len(resources) != len(set(resources)):
        raise ValueError("Lista de recursos vazia ou com duplicados.")
    if any(not CAR_RESOURCE_PATTERN.fullmatch(x) for x in resources):
        raise ValueError("Nome de recurso inválido.")
    if not isinstance(interval_seconds, int) or not 5 <= interval_seconds <= 60:
        raise ValueError("Intervalo deve estar entre 5 e 60 segundos.")
    safe = sorted(resources)
    # O teste inicial inclui no máximo dois fabricantes conhecidos.
    initial = [r for r in ("CIV_ACURA", "CIV_ASTONMARTIN") if r in safe]
    if not initial:
        initial = safe[:1]
    return (
        "-- Gerado pelo FrotaLab. Edite StartAll apenas apos testar o servidor.\n"
        "Config = {}\n"
        f"Config.StartAll = {'true' if start_all else 'false'}\n"
        "Config.InitialDelayMs = 20000  -- 20s apos iniciar o loader\n"
        f"Config.IntervalMs = {interval_seconds * 1000}  -- entre marcas\n"
        "Config.MaxWaitMs = 30000  -- espera maxima por inicio individual\n"
        "Config.InitialResources = {\n"
        + "".join(f"    {_lua_string(n)},\n" for n in initial) +
        "}\n"
        "Config.Resources = {\n"
        + "".join(f"    {_lua_string(n)},\n" for n in safe) +
        "}\n"
    )


def create_loader(selected_dir: Path, start_all: bool = False,
                  interval_seconds: int = 15, notify=lambda _: None):
    """Cria resources/frotalab_loader, nunca sobrescreve uma instalação.

    Sem efeitos no server.cfg ou recursos CIV_*; retornar diretório, marcas.
    """
    root, names = discover_brands(selected_dir)
    folder = root / LOADER_NAME
    if folder.exists() or folder.is_symlink():
        raise FileExistsError(
            f"Já existe {folder}. Não sobrescrevi. Faça backup antes de recriar.")
    config = make_config(names, start_all, interval_seconds)
    notify(f"Encontrei {len(names)} fabricantes. Criando {folder}")
    try:
        folder.mkdir()
        (folder / "fxmanifest.lua").write_text(FXMANIFEST, encoding="utf-8")
        (folder / "config.lua").write_text(config, encoding="utf-8")
        (folder / "server.lua").write_text(SERVER_LUA, encoding="utf-8")
        (folder / "LEIA-ME.txt").write_text(
            "FROTALAB LOADER - INICIALIZACAO ESCALONADA\n\n"
            "1. O novo recurso esta em resources/frotalab_loader.\n"
            "2. Mantenha desativados ensure [carros] e ensure PLOKS_CARS.\n"
            "3. Na configuracao server.cfg, DEPOIS do qb-core e dependencias,\n"
            "   inclua somente: ensure frotalab_loader\n"
            "4. Ou teste no console: refresh, depois ensure frotalab_loader.\n"
            "5. Por padrao apenas CIV_ACURA e CIV_ASTONMARTIN serao iniciados.\n"
            "6. Para permitir todos os fabricantes, edite config.lua:\n"
            "   Config.StartAll = true; recomendo intervalo de 15 segundos.\n"
            "7. Nunca execute ensure [carros] durante os testes.\n"
            "8. Loader evita reiniciar quem ja esta ativo.\n"
            "9. Isso nao otimiza texturas nem garante ausencia de travamentos.\n",
            encoding="utf-8"
        )
    except BaseException:
        # Não remover recursos criados por outra aplicação se já existirem.
        import shutil
        if folder.exists():
            shutil.rmtree(folder)
        raise
    notify(f"Loader criado. Modo: {'TODOS' if start_all else 'TESTE'}; "
           f"{len(names)} fabricantes encontrados.")
    return folder, names
