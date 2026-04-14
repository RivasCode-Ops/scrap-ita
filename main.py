"""
main.py — FastAPI server para o Scrap Ita.

Rotas:
  GET  /                       -> Pagina principal (SPA)
  GET  /contas                 -> Gerenciamento de contas (redirect para /)
  GET  /api/sessoes            -> Lista sessoes ativas
  POST /api/login              -> Inicia login em consolidador
  POST /api/renomear           -> Renomeia uma sessao
  POST /api/buscar             -> Inicia nova busca
  POST /api/parar              -> Para busca em andamento
  GET  /api/status             -> Status e progresso da busca
  GET  /api/historico          -> Historico de buscas
  GET  /api/aeroportos         -> Lista aeroportos destino
  POST /api/aeroportos         -> Salva lista de aeroportos
  POST /api/aeroportos/reset   -> Restaura lista padrao
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import sessoes as sessoes_mod
import scraper as scraper_mod


# ---------------------------------------------------------------------------
# Configuracao do app
# ---------------------------------------------------------------------------

app = FastAPI(title="Scrap Ita", version="1.0.0")
templates = Jinja2Templates(directory="templates")

BASE_DIR = Path(__file__).parent
HISTORICO_PATH = BASE_DIR / "historico.json"
AEROPORTOS_PATH = BASE_DIR / "aeroportos.json"

AEROPORTOS_PADRAO = [
    "GRU","GIG","BSB","CNF","SSA","FOR","REC","POA","CWB","BEL",
    "MAO","CGH","SDU","VCP","NAT","MCZ","AJU","CGB","THE","PMW",
    "MCP","STM","IMP","BVB","CZS","PVH","RBR","MGF","LDB","JOI",
    "FLN","IOS","ILH","UDI","UBA","CAC","FEN","JPA","SLZ","PPB",
    "SJP","ROO","PNZ","CPV","VDC","CHC","BAT","JDO","MNX",
    "CAF","OPS","APQ","MII","AUX","BPS","SSZ","URG","CXJ","BGX",
    "PET","RVD","CLN","ALT",
]


# ---------------------------------------------------------------------------
# Utilitarios de persistencia
# ---------------------------------------------------------------------------

def _ler_historico() -> list:
    if HISTORICO_PATH.exists():
        try:
            return json.loads(HISTORICO_PATH.read_text(encoding="utf-8")).get("buscas", [])
        except Exception:
            return []
    return []


def _salvar_historico(buscas: list):
    HISTORICO_PATH.write_text(
        json.dumps({"buscas": buscas}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _ler_aeroportos() -> list:
    if AEROPORTOS_PATH.exists():
        try:
            return json.loads(AEROPORTOS_PATH.read_text(encoding="utf-8")).get("aeroportos", AEROPORTOS_PADRAO)
        except Exception:
            return AEROPORTOS_PADRAO
    return AEROPORTOS_PADRAO


def _salvar_aeroportos(lista: list):
    AEROPORTOS_PATH.write_text(
        json.dumps({"aeroportos": lista}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    consolidador_tipo: str
    label: str


class RenomearRequest(BaseModel):
    id: str
    nome: str


class BuscarRequest(BaseModel):
    origem: str
    destino: str
    data_t1: str
    top_n: int = 10
    excluir: list[str] = []
    priorizar: list[str] = []


class PararRequest(BaseModel):
    busca_id: str


class AeroportosRequest(BaseModel):
    aeroportos: list[str]


# ---------------------------------------------------------------------------
# Rotas Frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def pagina_principal(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/contas", response_class=HTMLResponse)
async def pagina_contas(request: Request):
    # Redireciona para a SPA que gerencia contas via aba
    return templates.TemplateResponse("index.html", {"request": request, "aba_inicial": "contas"})


# ---------------------------------------------------------------------------
# API: Sessoes
# ---------------------------------------------------------------------------

@app.get("/api/sessoes")
async def api_sessoes():
    return {"sessoes": sessoes_mod.listar_sessoes()}


@app.post("/api/login")
async def api_login(req: LoginRequest):
    resultado = await sessoes_mod.fazer_login(req.consolidador_tipo, req.label)
    if not resultado.get("ok"):
        raise HTTPException(status_code=400, detail=resultado.get("erro", "Erro ao fazer login"))
    return resultado


@app.post("/api/renomear")
async def api_renomear(req: RenomearRequest):
    ok = sessoes_mod.renomear_sessao(req.id, req.nome)
    if not ok:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API: Busca
# ---------------------------------------------------------------------------

@app.post("/api/buscar")
async def api_buscar(req: BuscarRequest):
    aeroportos = _ler_aeroportos()
    busca_id = await scraper_mod.iniciar_busca(req.dict(), aeroportos)
    return {"busca_id": busca_id}


@app.post("/api/parar")
async def api_parar(req: PararRequest):
    ok = scraper_mod.parar_busca(req.busca_id)
    return {"ok": ok}


@app.get("/api/status")
async def api_status(busca_id: str):
    estado = scraper_mod.obter_estado_busca(busca_id)
    if not estado:
        raise HTTPException(status_code=404, detail="Busca nao encontrada")
    
    # Se a busca finalizou, salva no historico
    if not estado.get("busca_ativa") and estado.get("melhor") and not estado.get("_salvo"):
        estado["_salvo"] = True
        buscas = _ler_historico()
        buscas.insert(0, {
            "id": busca_id,
            "origem": estado["params"]["origem"],
            "destino": estado["params"]["destino"],
            "data_t1": estado["params"]["data_t1"],
            "excluir": estado["params"].get("excluir", []),
            "priorizar": estado["params"].get("priorizar", []),
            "timestamp": estado.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "melhor": estado.get("melhor"),
            "ranking": estado.get("resultados_fase2", []),
        })
        _salvar_historico(buscas)
    
    return {
        "busca_ativa": estado.get("busca_ativa", False),
        "fase_atual": estado.get("fase_atual", 0),
        "progresso": estado.get("progresso", []),
        "stats": estado.get("stats", {}),
        "resultados_parciais": estado.get("resultados_parciais", [])[:15],
        "resultados_fase2": estado.get("resultados_fase2", []),
        "melhor": estado.get("melhor"),
    }


# ---------------------------------------------------------------------------
# API: Historico
# ---------------------------------------------------------------------------

@app.get("/api/historico")
async def api_historico():
    return {"buscas": _ler_historico()}


# ---------------------------------------------------------------------------
# API: Aeroportos
# ---------------------------------------------------------------------------

@app.get("/api/aeroportos")
async def api_aeroportos_get():
    return {"aeroportos": _ler_aeroportos()}


@app.post("/api/aeroportos")
async def api_aeroportos_post(req: AeroportosRequest):
    lista = [a.strip().upper() for a in req.aeroportos if a.strip()]
    _salvar_aeroportos(lista)
    return {"ok": True, "total": len(lista)}


@app.post("/api/aeroportos/reset")
async def api_aeroportos_reset():
    _salvar_aeroportos(AEROPORTOS_PADRAO)
    return {"ok": True, "total": len(AEROPORTOS_PADRAO), "aeroportos": AEROPORTOS_PADRAO}


# ---------------------------------------------------------------------------
# Inicializacao
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info",
    )
