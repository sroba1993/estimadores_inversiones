import yfinance as yf
import pandas as pd

# ==========================
# PARÁMETROS GLOBALES
# ==========================

# Tasas base (las puedes ajustar)
DISCOUNT_RATE_DEFAULT = 0.10       # r: tasa de retorno requerida (10%)
DIV_GROWTH_DEFAULT = 0.03          # g: crecimiento dividendo largo plazo (3%)
DCF_GROWTH_5Y_DEFAULT = 0.05       # crecimiento “alto” 5 años (5%)
DCF_TERMINAL_PE_DEFAULT = 12.0     # múltiplo P/E terminal

# Rango para acotar P/E justo
PE_MIN = 8.0
PE_MAX = 20.0

# Opcional: ajustar r y g según sector (si se quiere afinar)
SECTOR_CONFIG = {
    "Financial Services":     {"r": 0.12, "g_div": 0.03, "g_5y": 0.05, "pe_term": 10},
    "Banks":                  {"r": 0.12, "g_div": 0.03, "g_5y": 0.05, "pe_term": 9},
    "Utilities":              {"r": 0.09, "g_div": 0.02, "g_5y": 0.04, "pe_term": 12},
    "Industrials":            {"r": 0.10, "g_div": 0.03, "g_5y": 0.05, "pe_term": 12},
    "Consumer Defensive":     {"r": 0.09, "g_div": 0.03, "g_5y": 0.05, "pe_term": 15},
    "Consumer Cyclical":      {"r": 0.11, "g_div": 0.03, "g_5y": 0.06, "pe_term": 14},
    "Technology":             {"r": 0.11, "g_div": 0.02, "g_5y": 0.08, "pe_term": 18},
    # default si no se encuentra sector:
    "_default":               {"r": DISCOUNT_RATE_DEFAULT, "g_div": DIV_GROWTH_DEFAULT,
                               "g_5y": DCF_GROWTH_5Y_DEFAULT, "pe_term": DCF_TERMINAL_PE_DEFAULT},
}


# ==========================
# FUNCIONES AUXILIARES
# ==========================

def get_sector_params(sector: str):
    """
    Devuelve los parámetros (r, g_div, g_5y, pe_term) según el sector,
    o los valores por defecto si no hay mapeo explícito.
    """
    if sector in SECTOR_CONFIG:
        cfg = SECTOR_CONFIG[sector]
    else:
        cfg = SECTOR_CONFIG["_default"]
    return cfg["r"], cfg["g_div"], cfg["g_5y"], cfg["pe_term"]


def obtener_datos_basicos(ticker_str: str) -> dict:
    """
    Descarga info básica de la acción con yfinance.
    Retorna un dict con los datos necesarios.
    """
    t = yf.Ticker(ticker_str)
    info = t.get_info() if hasattr(t, "get_info") else t.info

    # Intentar obtener FCF y acciones en circulación
    try:
        cashflow = t.cashflow
        # La fila suele llamarse "Free Cash Flow"
        fcf_series = cashflow.loc["Free Cash Flow"]
        fcf_ultimo = fcf_series.iloc[0] if len(fcf_series) > 0 else None
    except Exception:
        fcf_ultimo = None

    shares_out = info.get("sharesOutstanding")

    datos = {
        "ticker": ticker_str,
        "short_name": info.get("shortName"),
        "sector": info.get("sector"),
        "price": info.get("currentPrice"),
        "eps_trailing": info.get("trailingEps"),
        "eps_forward": info.get("forwardEps"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "dividend_rate": info.get("dividendRate"),      # dividendo anual por acción
        "dividend_yield": info.get("dividendYield"),    # en decimal
        "book_value": info.get("bookValue"),            # valor en libros por acción
        "shares_outstanding": shares_out,
        "free_cash_flow": fcf_ultimo,                   # FCF total último año
    }

    # FCF por acción aproximado
    if fcf_ultimo is not None and shares_out:
        datos["fcf_per_share"] = fcf_ultimo / shares_out
    else:
        datos["fcf_per_share"] = None

    return datos


def estimar_pe_justo(pe_trailing, pe_forward, pe_min=PE_MIN, pe_max=PE_MAX):
    """
    Estima un P/E “justo” a partir del trailing y forward.
    Acota a [pe_min, pe_max].
    """
    if pe_trailing and pe_forward:
        pe_base = (pe_trailing + pe_forward) / 2
    elif pe_trailing:
        pe_base = pe_trailing
    elif pe_forward:
        pe_base = pe_forward
    else:
        pe_base = 15.0  # por defecto

    return max(pe_min, min(pe_base, pe_max))


def valor_justo_por_pe(eps, pe_justo):
    """
    Valor justo simple por múltiplo P/E: Fair Value = EPS * P/E justo.
    """
    if eps is None or pe_justo is None:
        return None
    return eps * pe_justo


def valor_justo_dividendos(dividendo_anual, r, g):
    """
    Modelo de Gordon (Dividend Discount Model):
      FV = D1 / (r - g) = D0*(1+g)/(r-g)
    """
    if not dividendo_anual or r <= g:
        return None
    return dividendo_anual * (1 + g) / (r - g)


def valor_justo_dcf_simplificado(base_cash_per_share, r, g_5y, pe_terminal, years=5):
    """
    DCF simplificado usando cash flow por acción (idealmente FCF por acción,
    si no EPS como aproximación).

    Supuestos:
      - Crecimiento g_5y constante durante 'years' años.
      - Valor terminal = CF_5 * pe_terminal.
      - Se descuenta todo a r.

    Retorna el valor justo por acción.
    """
    if base_cash_per_share is None or r is None:
        return None

    cf = base_cash_per_share
    pv_sum = 0.0

    for t in range(1, years + 1):
        cf = cf * (1 + g_5y)  # crecimiento año a año
        pv_sum += cf / ((1 + r) ** t)

    # Valor terminal
    terminal_val = cf * pe_terminal
    pv_terminal = terminal_val / ((1 + r) ** years)

    return pv_sum + pv_terminal


def calcular_valor_justo_para_ticker(ticker_str: str) -> dict:
    """
    Calcula todos los métodos de fair value para un ticker y
    devuelve un dict con los resultados.
    """
    datos = obtener_datos_basicos(ticker_str)
    price = datos["price"]
    sector = datos["sector"]

    # Parámetros según sector
    r, g_div, g_5y, pe_terminal = get_sector_params(sector if sector else "_default")

    # 1) Valor por P/E
    pe_justo = estimar_pe_justo(datos["pe_trailing"], datos["pe_forward"])
    eps_usado = datos["eps_forward"] or datos["eps_trailing"]
    fv_pe = valor_justo_por_pe(eps_usado, pe_justo)

    # 2) Valor por dividendos (Gordon)
    fv_div = valor_justo_dividendos(datos["dividend_rate"], r, g_div)

    # 3) Valor por DCF simplificado (FCF por acción si hay, si no EPS)
    base_cash_per_share = datos["fcf_per_share"] or datos["eps_trailing"]
    fv_dcf = valor_justo_dcf_simplificado(base_cash_per_share, r, g_5y, pe_terminal)

    # Promedio de métodos disponibles
    fair_values = [v for v in [fv_pe, fv_div, fv_dcf] if v is not None]
    fv_avg = sum(fair_values) / len(fair_values) if fair_values else None

    # Upside vs precio actual
    upside = None
    if fv_avg and price:
        upside = (fv_avg / price - 1) * 100.0

    resultado = {
        "Ticker": datos["ticker"],
        "Nombre": datos["short_name"],
        "Sector": sector,
        "Precio_actual": price,
        "r_usado": r,
        "P/E_justo": pe_justo,
        "FV_PE": fv_pe,
        "FV_Dividendos": fv_div,
        "FV_DCF": fv_dcf,
        "FV_Promedio": fv_avg,
        "Upside_%": upside,
    }
    return resultado


# ==========================
# MAIN
# ==========================

def main():
    print("=== Estimador de valor justo por acción (multi-ticker) ===")
    tickers_str = input("Ingresa tickers separados por coma (ej: AAPL, MSFT, NKE):\n> ")
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]

    resultados = []

    for tk in tickers:
        try:
            print(f"\nProcesando {tk} ...")
            res = calcular_valor_justo_para_ticker(tk)
            resultados.append(res)
        except Exception as e:
            print(f"Error procesando {tk}: {e}")

    if not resultados:
        print("No se pudo calcular ningún ticker.")
        return

    df = pd.DataFrame(resultados)

    # Ordenar por mayor upside
    df = df.sort_values(by="Upside_%", ascending=False)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)

    print("\n===== TABLA DE FAIR VALUES (ORDENADA POR UPSIDE) =====\n")
    print(df.to_string(index=False))
    print("\n=======================================================")


if __name__ == "__main__":
    main()
