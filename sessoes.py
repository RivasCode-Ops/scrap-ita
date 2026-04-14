"""
sessoes.py — Gerenciamento de sessoes e autenticacao nos consolidadores.
Consolidadores suportados: infotera, viajanet
"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


# ---------------------------------------------------------------------------
# Configuracoes dos consolidadores
# ---------------------------------------------------------------------------

CONSOLIDADORES = {
    "infotera": {
        "login_url": "https://www.infotera.com.br/login",
        "username_selector": "#username",
        "password_selector": "#password",
        "submit_selector": "button[type='submit']",
        "success_selector": ".dashboard, .home-container",
        # Configure as credenciais via variaveis de ambiente ou config.json
        "credenciais": [
            {"usuario": "SEU_USUARIO_1", "senha": "SUA_SENHA_1", "label": "Conta 1 - Infotera"},
            # Adicione mais contas conforme necessario
        ],
    },
    "viajanet": {
        "login_url": "https://www.viajanet.com.br/login",
        "username_selector": "#email",
        "password_selector": "#password",
        "submit_selector": "button[type='submit']",
        "success_selector": ".user-menu, .profile-icon",
        "credenciais": [
            {"usuario": "SEU_EMAIL@exemplo.com", "senha": "SUA_SENHA", "label": "Conta ViajaNet"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Armazenamento em memoria das sessoes ativas
# ---------------------------------------------------------------------------

_sessoes: dict[str, dict] = {}  # id -> dados da sessao
_playwright_instances: dict[str, object] = {}  # id -> playwright context


def listar_sessoes() -> list[dict]:
    """Retorna todas as sessoes ativas com metadados."""
    resultado = []
    for sid, dados in _sessoes.items():
        resultado.append({
            "id": sid,
            "nome": dados.get("nome", "Sem nome"),
            "consolidador": dados.get("consolidador", ""),
            "timestamp": dados.get("timestamp", ""),
            "status": dados.get("status", "ativa"),
        })
    return resultado


def renomear_sessao(sessao_id: str, novo_nome: str) -> bool:
    """Renomeia uma sessao existente."""
    if sessao_id in _sessoes:
        _sessoes[sessao_id]["nome"] = novo_nome
        return True
    return False


def obter_sessao(sessao_id: str) -> Optional[dict]:
    """Obtem os dados de uma sessao pelo ID."""
    return _sessoes.get(sessao_id)


def obter_pagina(sessao_id: str) -> Optional[Page]:
    """Retorna o objeto Page do Playwright para uma sessao."""
    return _playwright_instances.get(sessao_id)


async def fazer_login(consolidador_tipo: str, label: str) -> dict:
    """
    Inicia o processo de login automatico em um consolidador.
    Cria uma nova sessao de browser e autentica.
    
    Args:
        consolidador_tipo: 'infotera' ou 'viajanet'
        label: Nome/label para identificar a sessao
        
    Returns:
        dict com ok=True e sessao_id, ou ok=False e mensagem de erro
    """
    if consolidador_tipo not in CONSOLIDADORES:
        return {"ok": False, "erro": f"Consolidador '{consolidador_tipo}' nao suportado"}
    
    config = CONSOLIDADORES[consolidador_tipo]
    
    # Busca credenciais pelo label
    credencial = None
    for cred in config["credenciais"]:
        if cred.get("label") == label or label in cred.get("label", ""):
            credencial = cred
            break
    
    if not credencial:
        # Usa a primeira credencial disponivel se nao encontrar pelo label
        if config["credenciais"]:
            credencial = config["credenciais"][0]
        else:
            return {"ok": False, "erro": "Nenhuma credencial configurada para este consolidador"}
    
    sessao_id = str(uuid.uuid4())
    
    try:
        pw = await async_playwright().start()
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page: Page = await context.new_page()
        
        # Navega para pagina de login
        await page.goto(config["login_url"], wait_until="networkidle", timeout=30000)
        
        # Preenche credenciais
        await page.fill(config["username_selector"], credencial["usuario"])
        await page.fill(config["password_selector"], credencial["senha"])
        await page.click(config["submit_selector"])
        
        # Aguarda redirecionamento/sucesso
        await page.wait_for_selector(config["success_selector"], timeout=15000)
        
        # Registra sessao
        _sessoes[sessao_id] = {
            "nome": label or credencial.get("label", f"{consolidador_tipo} - {sessao_id[:8]}"),
            "consolidador": consolidador_tipo,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ativa",
            "credencial_label": credencial.get("label", ""),
        }
        _playwright_instances[sessao_id] = {
            "playwright": pw,
            "browser": browser,
            "context": context,
            "page": page,
        }
        
        return {"ok": True, "sessao_id": sessao_id, "nome": _sessoes[sessao_id]["nome"]}
        
    except Exception as e:
        # Limpa recursos em caso de erro
        try:
            if sessao_id in _playwright_instances:
                inst = _playwright_instances.pop(sessao_id)
                await inst["browser"].close()
                await inst["playwright"].stop()
        except Exception:
            pass
        return {"ok": False, "erro": str(e)}


async def encerrar_sessao(sessao_id: str) -> bool:
    """Encerra uma sessao e libera recursos do browser."""
    if sessao_id not in _sessoes:
        return False
    
    try:
        if sessao_id in _playwright_instances:
            inst = _playwright_instances.pop(sessao_id)
            await inst["browser"].close()
            await inst["playwright"].stop()
    except Exception:
        pass
    
    _sessoes.pop(sessao_id, None)
    return True


async def verificar_sessoes_ativas() -> list[str]:
    """Verifica quais sessoes ainda estao ativas e remove as expiradas."""
    expiradas = []
    for sid, dados in list(_sessoes.items()):
        inst = _playwright_instances.get(sid)
        if not inst:
            expiradas.append(sid)
            continue
        try:
            # Verifica se a pagina ainda esta responsiva
            page: Page = inst["page"]
            await page.evaluate("() => document.title")
        except Exception:
            expiradas.append(sid)
    
    for sid in expiradas:
        await encerrar_sessao(sid)
    
    return expiradas
