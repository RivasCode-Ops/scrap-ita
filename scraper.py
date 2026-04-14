"""
scraper.py — Logica de scraping de passagens aereas.

Implementa a busca em 2 fases:
  Fase 1: Varre todos os aeroportos destino para cada sessao ativa em paralelo.
  Fase 2: Confirma os melhores destinos com busca detalhada.

Adapte os seletores e logica de extracao conforme o consolidador alvo.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sessoes import obter_pagina, listar_sessoes


# ---------------------------------------------------------------------------
# Estado global das buscas em andamento
# ---------------------------------------------------------------------------

_buscas_ativas: dict[str, dict] = {}  # busca_id -> estado completo


def obter_estado_busca(busca_id: str) -> Optional[dict]:
    return _buscas_ativas.get(busca_id)


def parar_busca(busca_id: str) -> bool:
    if busca_id in _buscas_ativas:
        _buscas_ativas[busca_id]["parar"] = True
        return True
    return False


# ---------------------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------------------

def _data_com_offset(data_base: str, offset_dias: int) -> str:
    """Retorna data no formato YYYY-MM-DD somando offset_dias."""
    base = datetime.strptime(data_base, "%Y-%m-%d")
    return (base + timedelta(days=offset_dias)).strftime("%Y-%m-%d")


def _log(estado: dict, msg: str):
    """Adiciona mensagem de log ao estado da busca."""
    estado["progresso"].append({"msg": msg, "ts": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Fase 1: Varredura de aeroportos
# ---------------------------------------------------------------------------

async def _buscar_voo_infotera(
    page,
    origem: str,
    destino_dummy: str,
    destino_final: str,
    data_t1: str,
    offset: int,
    fonte_nome: str,
) -> Optional[dict]:
    """
    Executa uma busca de voo no Infotera via Playwright.
    
    Adapte os seletores conforme o HTML real do Infotera.
    Retorna um dict com os dados do voo encontrado ou None.
    """
    try:
        data_t2 = _data_com_offset(data_t1, offset)
        
        # ---------------------------------------------------------------
        # ADAPTE AQUI: Navegacao e preenchimento do formulario do Infotera
        # ---------------------------------------------------------------
        # Exemplo generico — substitua pelos seletores reais:
        
        # await page.goto("https://www.infotera.com.br/busca-voos")
        # await page.fill("#origem", origem)
        # await page.fill("#destino-escala", destino_dummy)
        # await page.fill("#destino-final", destino_final)
        # await page.fill("#data-ida", data_t1)
        # await page.fill("#data-volta", data_t2)
        # await page.click("#btn-buscar")
        # await page.wait_for_selector(".resultado-voo", timeout=10000)
        
        # Extrai resultados
        # resultados = await page.query_selector_all(".resultado-voo")
        # if not resultados:
        #     return None
        
        # preco_el = await resultados[0].query_selector(".preco")
        # preco_texto = await preco_el.inner_text()
        # preco = float(preco_texto.replace("R$", "").replace(".", "").replace(",", ".").strip())
        
        # companhia_el = await resultados[0].query_selector(".companhia")
        # companhia = await companhia_el.inner_text()
        
        # return {
        #     "destino": destino_dummy,
        #     "offset": offset,
        #     "data_t2": data_t2,
        #     "preco": preco,
        #     "companhia": companhia,
        #     "fonte_nome": fonte_nome,
        # }
        
        # --- Stub para demonstracao (remova ao implementar de verdade) ---
        await asyncio.sleep(0.5)  # simula latencia de rede
        return None
        # ------------------------------------------------------------------
        
    except Exception as e:
        return None


async def _buscar_voo_viajanet(
    origem: str,
    destino_dummy: str,
    destino_final: str,
    data_t1: str,
    offset: int,
    fonte_nome: str,
) -> Optional[dict]:
    """
    Busca via ViajaNet (sem sessao autenticada — usa API publica ou scraping anonimo).
    Adapte conforme necessario.
    """
    try:
        data_t2 = _data_com_offset(data_t1, offset)
        
        # ---------------------------------------------------------------
        # ADAPTE AQUI: Chamada API ou scraping do ViajaNet
        # ---------------------------------------------------------------
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(
        #         "https://api.viajanet.com.br/voos",
        #         params={
        #             "origem": origem,
        #             "destino": destino_dummy,
        #             "destino_final": destino_final,
        #             "data_ida": data_t1,
        #             "data_volta": data_t2,
        #         },
        #         timeout=10.0
        #     )
        #     data = resp.json()
        #     if data.get("voos"):
        #         voo = data["voos"][0]
        #         return {
        #             "destino": destino_dummy,
        #             "offset": offset,
        #             "data_t2": data_t2,
        #             "preco": voo["preco_total"],
        #             "companhia": voo["companhia"],
        #             "fonte_nome": fonte_nome,
        #         }
        
        await asyncio.sleep(0.3)
        return None
        
    except Exception:
        return None


async def _varrer_aeroportos_sessao(
    sessao: dict,
    aeroportos: list[str],
    estado: dict,
    params: dict,
):
    """
    Varre todos os aeroportos destino para uma sessao especifica.
    Atualiza o estado compartilhado com resultados parciais.
    """
    sessao_id = sessao["id"]
    fonte_nome = sessao["nome"]
    consolidador = sessao["consolidador"]
    page = obter_pagina(sessao_id)
    
    if not page and consolidador != "viajanet":
        _log(estado, f"[ERRO] Sessao {fonte_nome} sem pagina ativa")
        return
    
    origem = params["origem"]
    destino = params["destino"]
    data_t1 = params["data_t1"]
    top_n = params.get("top_n", 10)
    
    # Offsets de data para busca multi-city (1 a 7 dias apos trecho 1)
    offsets = list(range(1, 8))
    total = len(aeroportos) * len(offsets)
    contador = 0
    
    for idx, aeroporto in enumerate(aeroportos):
        if estado.get("parar"):
            break
        
        for offset in offsets:
            if estado.get("parar"):
                break
            
            contador += 1
            estado["fontes_status"][sessao_id] = {
                "status": "ativa",
                "progresso": contador,
                "total": total,
            }
            
            if consolidador == "viajanet":
                resultado = await _buscar_voo_viajanet(
                    origem, aeroporto, destino, data_t1, offset, fonte_nome
                )
            else:
                resultado = await _buscar_voo_infotera(
                    page, origem, aeroporto, destino, data_t1, offset, fonte_nome
                )
            
            prefixo = f"→ Com resultados [{fonte_nome}]" if resultado else f"→ Sem resultados [{fonte_nome}]"
            msg = f"{prefixo} {contador}/{total}: {origem}→{aeroporto} +{offset}d"
            _log(estado, msg)
            
            if resultado:
                estado["resultados_parciais"].append(resultado)
                # Mantém lista ordenada por preço
                estado["resultados_parciais"].sort(key=lambda x: x["preco"])
    
    estado["fontes_status"][sessao_id]["status"] = "concluida"


# ---------------------------------------------------------------------------
# Fase 2: Confirmacao dos melhores destinos
# ---------------------------------------------------------------------------

async def _confirmar_melhor_preco(
    sessao: dict,
    destino: str,
    params: dict,
    offset: int,
) -> Optional[dict]:
    """
    Re-busca um destino especifico para confirmar preco e obter dados completos.
    Implementacao depende do consolidador — adapte conforme necessario.
    """
    await asyncio.sleep(0.2)  # stub
    return None


# ---------------------------------------------------------------------------
# Funcao principal: iniciar_busca
# ---------------------------------------------------------------------------

async def iniciar_busca(params: dict, aeroportos_lista: list[str]) -> str:
    """
    Inicia uma busca completa em 2 fases.
    
    Args:
        params: dict com origem, destino, data_t1, top_n, excluir, priorizar
        aeroportos_lista: lista completa de aeroportos IATA destino
        
    Returns:
        busca_id: UUID da busca iniciada
    """
    busca_id = str(uuid.uuid4())
    
    # Prepara lista de aeroportos (priorizar + remover excluidos)
    excluir = set(params.get("excluir", []))
    priorizar = params.get("priorizar", [])
    
    aeroportos_filtrados = [a for a in aeroportos_lista if a not in excluir]
    
    # Coloca aeroportos priorizados no inicio
    aeroportos_priorizados = [a for a in priorizar if a in aeroportos_filtrados]
    aeroportos_restantes = [a for a in aeroportos_filtrados if a not in set(priorizar)]
    aeroportos_ordenados = aeroportos_priorizados + aeroportos_restantes
    
    # Estado inicial da busca
    sessoes = listar_sessoes()
    estado = {
        "busca_id": busca_id,
        "busca_ativa": True,
        "fase_atual": 1,
        "parar": False,
        "progresso": [],
        "stats": {
            "fase1_resultados": 0,
            "fase1_tempo": None,
            "fontes_status": {s["id"]: {"status": "aguardando"} for s in sessoes},
        },
        "resultados_parciais": [],
        "resultados_fase2": [],
        "melhor": None,
        "params": params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    _buscas_ativas[busca_id] = estado
    
    # Inicia em background
    asyncio.create_task(_executar_busca(busca_id, sessoes, aeroportos_ordenados, params))
    
    return busca_id


async def _executar_busca(
    busca_id: str,
    sessoes: list[dict],
    aeroportos: list[str],
    params: dict,
):
    """Executa a busca completa em background (2 fases)."""
    estado = _buscas_ativas.get(busca_id)
    if not estado:
        return
    
    inicio = datetime.now()
    _log(estado, f"[INICIO] Busca iniciada: {params['origem']} → {params['destino']} | {len(aeroportos)} aeroportos | {len(sessoes)} fontes")
    
    try:
        # ===== FASE 1 =====
        estado["fase_atual"] = 1
        _log(estado, "[FASE 1] Iniciando varredura de aeroportos...")
        
        # Adiciona ViajaNet como fonte extra (sem sessao autenticada)
        fontes = list(sessoes)
        fontes.append({
            "id": "viajanet_anonimo",
            "nome": "ViajaNet",
            "consolidador": "viajanet",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        estado["stats"]["fontes_status"]["viajanet_anonimo"] = {"status": "aguardando"}
        
        # Distribui aeroportos entre as fontes e executa em paralelo
        tarefas = []
        chunk_size = max(1, len(aeroportos) // max(1, len(fontes)))
        
        for i, sessao in enumerate(fontes):
            inicio_chunk = i * chunk_size
            fim_chunk = inicio_chunk + chunk_size if i < len(fontes) - 1 else len(aeroportos)
            chunk = aeroportos[inicio_chunk:fim_chunk]
            if chunk:
                tarefas.append(
                    _varrer_aeroportos_sessao(sessao, chunk, estado, params)
                )
        
        await asyncio.gather(*tarefas)
        
        tempo_fase1 = (datetime.now() - inicio).total_seconds()
        estado["stats"]["fase1_resultados"] = len(estado["resultados_parciais"])
        estado["stats"]["fase1_tempo"] = round(tempo_fase1, 1)
        
        if estado.get("parar"):
            _log(estado, "[PARADO] Busca interrompida pelo usuario")
            estado["busca_ativa"] = False
            return
        
        _log(estado, f"[FASE 1 CONCLUIDA] {len(estado['resultados_parciais'])} resultados em {tempo_fase1:.1f}s")
        
        # ===== FASE 2 =====
        estado["fase_atual"] = 2
        top_n = params.get("top_n", 10)
        
        if not estado["resultados_parciais"]:
            _log(estado, "[FASE 2] Nenhum resultado na Fase 1 para confirmar")
            estado["busca_ativa"] = False
            return
        
        _log(estado, f"[FASE 2] Confirmando top {top_n} destinos...")
        
        # Agrupa por destino e pega o melhor de cada
        por_destino: dict[str, list] = {}
        for r in estado["resultados_parciais"]:
            dest = r["destino"]
            if dest not in por_destino:
                por_destino[dest] = []
            por_destino[dest].append(r)
        
        # Ordena destinos pelo melhor preco
        destinos_ordenados = sorted(
            por_destino.keys(),
            key=lambda d: min(r["preco"] for r in por_destino[d])
        )
        
        top_destinos = destinos_ordenados[:top_n]
        ranking = []
        
        for dest in top_destinos:
            if estado.get("parar"):
                break
            
            ofertas = sorted(por_destino[dest], key=lambda x: x["preco"])
            melhor = ofertas[0]
            ranking.append({
                "melhor": melhor,
                "ofertas": ofertas,
            })
            _log(estado, f"[FASE 2] {dest}: R$ {melhor['preco']:.2f} ({melhor['companhia']}) via {melhor['fonte_nome']}")
        
        estado["resultados_fase2"] = ranking
        
        if ranking:
            estado["melhor"] = ranking[0]["melhor"]
            _log(estado, f"[MELHOR OPCAO] {estado['melhor']['destino']}: R$ {estado['melhor']['preco']:.2f}")
        
        _log(estado, "[CONCLUIDO] Busca finalizada com sucesso!")
        
    except Exception as e:
        _log(estado, f"[ERRO] {str(e)}")
    finally:
        estado["busca_ativa"] = False
