"""
AGENTE DE TRADING ESPORTIVO - FLAVIO
=====================================
Monitoramento ao vivo de jogos de futebol com alertas via Telegram.
Estrategia: Lay do visitante nao favorito em jogos 0x0.
"""

import asyncio
import requests
from datetime import datetime
from telegram import Bot

# -----------------------------------------
# CONFIGURACOES - EDITE AQUI
# -----------------------------------------

TELEGRAM_TOKEN = "8617867734:AAFZvERCsxFMbE1KJEy0d29O4zrQFMUshmw"
TELEGRAM_CHAT_ID = 5243546997
FOOTBALL_DATA_API_KEY = "a514ab395fc34379a9aa0db48d64439a"  # cadastre em football-data.org (gratis)
INTERVALO_SEGUNDOS = 60

# -----------------------------------------
# LIGAS MONITORADAS
# -----------------------------------------

LIGAS = {
    "PL":  "Premier League (Inglaterra)",
    "PD":  "La Liga (Espanha)",
    "BL1": "Bundesliga (Alemanha)",
    "SA":  "Serie A (Italia)",
    "FL1": "Ligue 1 (Franca)",
    "PPL": "Primeira Liga (Portugal)",
    "BSA": "Brasileirao Serie A",
    "FAC": "FA Cup (Inglaterra)",
    "DFB": "DFB-Pokal (Alemanha)",
    "CDR": "Copa del Rey (Espanha)",
    "CIT": "Coppa Italia",
    "CDF": "Coupe de France",
    "TAP": "Taca de Portugal",
    "CB":  "Copa do Brasil",
}

# -----------------------------------------
# CRITERIOS DA ESTRATEGIA
# -----------------------------------------

MINUTO_MINIMO_ENTRADA = 5
MINUTO_MAXIMO_ENTRADA = 40
MINUTO_ENCERRAMENTO = 45
ODD_PRE_JOGO_MIN = 4.0
ODD_PRE_JOGO_MAX = 8.0
POSSE_VISITANTE_MAX = 50
XG_VISITANTE_SAIDA = 0.3

# -----------------------------------------
# ESTADO DO AGENTE
# -----------------------------------------

posicoes_abertas = {}
alertas_enviados = {}

# -----------------------------------------
# ALERTAS TELEGRAM
# -----------------------------------------

async def enviar_alerta(mensagem):
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=mensagem, parse_mode="HTML")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ALERTA ENVIADO")
    except Exception as e:
        print(f"Erro Telegram: {e}")


def msg_entrada(jogo, stats):
    posse = stats.get("posse_visitante", "N/D")
    xg = stats.get("xg_visitante", "N/D")
    chv = stats.get("chutes_visitante", "N/D")
    chm = stats.get("chutes_mandante", "N/D")
    return (
        f"ALERTA DE ENTRADA\n"
        f"-------------------\n"
        f"{jogo['mandante']} x {jogo['visitante']}\n"
        f"Liga: {jogo['liga']}\n"
        f"Minuto: {jogo['minuto']}'\n"
        f"Placar: {jogo['placar']}\n"
        f"-------------------\n"
        f"Posse visitante: {posse}%\n"
        f"xG visitante: {xg}\n"
        f"Chutes visitante: {chv}\n"
        f"Chutes mandante: {chm}\n"
        f"-------------------\n"
        f"Confirme escalacoes no CScore antes de entrar!"
    )


def msg_saida(jogo, motivo, urgencia="SAIDA"):
    return (
        f"{urgencia} - ALERTA DE SAIDA\n"
        f"-------------------\n"
        f"{jogo['mandante']} x {jogo['visitante']}\n"
        f"Minuto: {jogo['minuto']}'\n"
        f"Placar: {jogo['placar']}\n"
        f"-------------------\n"
        f"Motivo: {motivo}\n"
        f"Avalie sair da posicao agora!"
    )


def msg_intervalo(jogo):
    return (
        f"ENCERRAMENTO OBRIGATORIO - INTERVALO\n"
        f"-------------------\n"
        f"{jogo['mandante']} x {jogo['visitante']}\n"
        f"Placar 1o tempo: {jogo['placar']}\n"
        f"Encerre sua posicao agora conforme estrategia."
    )


# -----------------------------------------
# DADOS
# -----------------------------------------

def buscar_jogos_ao_vivo():
    jogos = []
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    for codigo, nome in LIGAS.items():
        try:
            url = f"https://api.football-data.org/v4/competitions/{codigo}/matches?status=LIVE"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                for m in r.json().get("matches", []):
                    minuto = m.get("minute") or 0
                    score = m.get("score", {}).get("fullTime", {})
                    home = score.get("home") or 0
                    away = score.get("away") or 0
                    jogos.append({
                        "id": m["id"],
                        "liga": nome,
                        "mandante": m["homeTeam"]["name"],
                        "visitante": m["awayTeam"]["name"],
                        "minuto": minuto,
                        "placar": f"{home}x{away}",
                        "gols_mandante": home,
                        "gols_visitante": away,
                    })
            elif r.status_code == 429:
                print(f"Rate limit: {nome}")
        except Exception as e:
            print(f"Erro {nome}: {e}")
    return jogos


def buscar_stats(match_id):
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    try:
        r = requests.get(
            f"https://api.football-data.org/v4/matches/{match_id}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            hs = data.get("homeTeam", {}).get("statistics", {})
            aws = data.get("awayTeam", {}).get("statistics", {})
            return {
                "posse_mandante": hs.get("ballPossession"),
                "posse_visitante": aws.get("ballPossession"),
                "xg_mandante": hs.get("expectedGoals"),
                "xg_visitante": aws.get("expectedGoals"),
                "chutes_mandante": hs.get("totalShots"),
                "chutes_visitante": aws.get("totalShots"),
                "chutes_gol_mandante": hs.get("shotsOnGoal"),
                "chutes_gol_visitante": aws.get("shotsOnGoal"),
            }
    except Exception as e:
        print(f"Erro stats {match_id}: {e}")
    return {}


# -----------------------------------------
# LOGICA
# -----------------------------------------

LIGAS_PRIORIDADE = {
    "Premier League (Inglaterra)": 1,
    "La Liga (Espanha)": 2,
    "Bundesliga (Alemanha)": 3,
    "Serie A (Italia)": 4,
    "Ligue 1 (Franca)": 5,
    "Primeira Liga (Portugal)": 6,
    "Brasileirao Serie A": 7,
}


def rankear(jogos):
    def score(j):
        p = LIGAS_PRIORIDADE.get(j["liga"], 10)
        return (p, -j.get("minuto", 0))
    return sorted(jogos, key=score)


def checar_entrada(jogo, stats):
    if jogo["gols_mandante"] != 0 or jogo["gols_visitante"] != 0:
        return False, "Placar nao e 0x0"
    m = jogo["minuto"]
    if m < MINUTO_MINIMO_ENTRADA or m > MINUTO_MAXIMO_ENTRADA:
        return False, f"Fora da janela ({m}')"
    pv = stats.get("posse_visitante")
    if pv and pv >= POSSE_VISITANTE_MAX:
        return False, f"Posse visitante alta ({pv}%)"
    xg = stats.get("xg_visitante")
    if xg and xg >= XG_VISITANTE_SAIDA:
        return False, f"xG visitante alto ({xg})"
    return True, "OK"


def checar_saida(jogo, stats, posicao):
    gatilhos = []
    gv = jogo["gols_visitante"]
    gm = jogo["gols_mandante"]
    m = jogo["minuto"]

    if gv > posicao.get("gols_visitante_entrada", 0):
        gatilhos.append(("GOL DO VISITANTE - Saida imediata!", "IMEDIATA"))
    if gm > posicao.get("gols_mandante_entrada", 0):
        gatilhos.append(("GOL DO MANDANTE - Feche com lucro!", "LUCRO"))
    if m >= MINUTO_ENCERRAMENTO:
        gatilhos.append(("Intervalo", "INTERVALO"))

    pv = stats.get("posse_visitante")
    if pv and pv >= POSSE_VISITANTE_MAX:
        gatilhos.append((f"Posse visitante: {pv}%", "PADRAO"))

    xg = stats.get("xg_visitante")
    if xg and xg >= XG_VISITANTE_SAIDA:
        gatilhos.append((f"xG visitante: {xg}", "PADRAO"))

    return gatilhos


# -----------------------------------------
# LOOP PRINCIPAL
# -----------------------------------------

async def processar():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Verificando jogos...")
    jogos = buscar_jogos_ao_vivo()

    if not jogos:
        print("Nenhum jogo ao vivo.")
        return

    print(f"{len(jogos)} jogo(s) encontrado(s).")

    candidatos = []
    for jogo in jogos:
        stats = buscar_stats(jogo["id"])
        jogo["stats"] = stats
        ok, motivo = checar_entrada(jogo, stats)
        if ok:
            candidatos.append(jogo)
        else:
            print(f"  Descartado: {jogo['mandante']} x {jogo['visitante']} - {motivo}")

    foco = rankear(candidatos)[:3]

    if foco:
        print(f"{len(foco)} oportunidade(s) no foco.")

    for jogo in foco:
        mid = jogo["id"]
        alertas_enviados.setdefault(mid, set())
        if "ENTRADA" not in alertas_enviados[mid]:
            await enviar_alerta(msg_entrada(jogo, jogo.get("stats", {})))
            alertas_enviados[mid].add("ENTRADA")
            posicoes_abertas[mid] = {
                "jogo": jogo,
                "gols_mandante_entrada": jogo["gols_mandante"],
                "gols_visitante_entrada": jogo["gols_visitante"],
            }

    for mid, posicao in list(posicoes_abertas.items()):
        jogo = next((j for j in jogos if j["id"] == mid), None)
        if not jogo:
            continue
        stats = buscar_stats(mid)
        for motivo, tipo in checar_saida(jogo, stats, posicao):
            chave = f"SAIDA_{tipo}_{motivo[:20]}"
            if chave not in alertas_enviados.get(mid, set()):
                if tipo == "INTERVALO":
                    await enviar_alerta(msg_intervalo(jogo))
                elif tipo == "LUCRO":
                    await enviar_alerta(msg_saida(jogo, motivo, "LUCRO"))
                elif tipo == "IMEDIATA":
                    await enviar_alerta(msg_saida(jogo, motivo, "URGENTE"))
                else:
                    await enviar_alerta(msg_saida(jogo, motivo, "ATENCAO"))
                alertas_enviados.setdefault(mid, set()).add(chave)
                if tipo in ("IMEDIATA", "LUCRO", "INTERVALO"):
                    posicoes_abertas.pop(mid, None)


async def main():
    print("=" * 50)
    print("  AGENTE DE TRADING ESPORTIVO - FLAVIO")
    print("=" * 50)
    await enviar_alerta(
        "Agente iniciado!\n"
        f"Monitorando {len(LIGAS)} ligas/copas\n"
        f"Janela: {MINUTO_MINIMO_ENTRADA}' a {MINUTO_MAXIMO_ENTRADA}' | Placar: 0x0\n"
        "Aguardando oportunidades..."
    )
    while True:
        try:
            await processar()
        except Exception as e:
            print(f"Erro: {e}")
        await asyncio.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    asyncio.run(main())
