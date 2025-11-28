import dash
from dash import callback_context, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

TIMEFRAME_OPTIONS = {
    "1m": {"label": "1m", "period": "7d", "interval": "1m"},
    "5m": {"label": "5m", "period": "30d", "interval": "5m"},
    "15m": {"label": "15m", "period": "60d", "interval": "15m"},
    "1h": {"label": "1h", "period": "90d", "interval": "60m"},
    "1d": {"label": "1d", "period": "1y", "interval": "1d"},
}

TIMEFRAME_KEYS = list(TIMEFRAME_OPTIONS.keys())
TIMEFRAME_BUTTON_IDS = [f"btn-timeframe-{key}" for key in TIMEFRAME_KEYS]
CHART_TYPES = ["candlestick", "line"]
CHART_BUTTON_IDS = [f"btn-chart-{chart}" for chart in CHART_TYPES]


def obtener_datos(ticker_str: str):
    ticker = yf.Ticker(ticker_str)
    info = ticker.get_info() if hasattr(ticker, "get_info") else ticker.info
    return {
        "ticker": ticker_str,
        "precio_actual": info.get("currentPrice"),
        "trailing_eps": info.get("trailingEps"),
        "forward_eps": info.get("forwardEps"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividendo_anual": info.get("dividendRate"),
        "dividend_yield": info.get("dividendYield"),
        "five_year_avg_div_yield": info.get("fiveYearAvgDividendYield"),
        "book_value": info.get("bookValue"),
        "sector": info.get("sector"),
        "short_name": info.get("shortName"),
    }


def valor_justo_por_pe(eps, pe_justo):
    if eps is None or pe_justo is None:
        return None
    return eps * pe_justo


def valor_justo_dividendos(dividendo_anual, tasa_descuento, tasa_crecimiento):
    if not dividendo_anual or tasa_descuento <= tasa_crecimiento:
        return None
    return dividendo_anual * (1 + tasa_crecimiento) / (tasa_descuento - tasa_crecimiento)


def estimar_pe_justo(datos, pe_min=8, pe_max=20):
    trailing = datos.get("trailing_pe")
    forward = datos.get("forward_pe")
    if trailing and forward:
        pe_base = (trailing + forward) / 2
    elif trailing:
        pe_base = trailing
    elif forward:
        pe_base = forward
    else:
        pe_base = 15.0
    return max(pe_min, min(pe_base, pe_max))


def graficar_ratios_historicos(ticker_str: str, return_data=False):
    ticker = yf.Ticker(ticker_str)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5 * 365)
    hist = ticker.history(start=start_date, end=end_date)
    try:
        quarterly_financials = ticker.quarterly_financials
        quarterly_balance = ticker.quarterly_balance_sheet
        quarterly_cashflow = ticker.quarterly_cashflow
        info = ticker.info
    except Exception:
        return None
    if quarterly_financials is None or quarterly_financials.empty:
        return None

    todas_fechas = list(quarterly_financials.columns)
    fechas_datetime = []
    for fecha in todas_fechas:
        try:
            if isinstance(fecha, pd.Timestamp):
                fecha_dt = fecha.to_pydatetime()
            elif hasattr(fecha, "year"):
                fecha_dt = fecha
            else:
                fecha_dt = pd.to_datetime(fecha).to_pydatetime()
            fechas_datetime.append((fecha, fecha_dt))
        except Exception:
            continue

    fechas_datetime.sort(key=lambda x: x[1], reverse=True)
    fechas_trimestrales = [fecha_orig for fecha_orig, _ in fechas_datetime[:20]]
    if not fechas_trimestrales:
        return None

    def buscar_valor(df, posibles_nombres, fecha_col):
        if df is None or df.empty:
            return None
        for nombre in posibles_nombres:
            if nombre in df.index:
                try:
                    valor = df.loc[nombre, fecha_col]
                    if pd.notna(valor) and valor != 0:
                        return float(valor)
                except Exception:
                    continue
        return None

    def obtener_trimestre_label(fecha):
        if hasattr(fecha, "year") and hasattr(fecha, "month"):
            año = fecha.year
            trimestre = (fecha.month - 1) // 3 + 1
            return f"{año}-Q{trimestre}"
        elif hasattr(fecha, "strftime"):
            año = int(fecha.strftime("%Y"))
            mes = int(fecha.strftime("%m"))
            trimestre = (mes - 1) // 3 + 1
            return f"{año}-Q{trimestre}"
        else:
            fecha_str = str(fecha)
            if len(fecha_str) >= 7:
                año = int(fecha_str[:4])
                mes = int(fecha_str[5:7])
                trimestre = (mes - 1) // 3 + 1
                return f"{año}-Q{trimestre}"
        return str(fecha)

    ratios_data = {}
    for fecha in fechas_trimestrales:
        try:
            revenue = buscar_valor(
                quarterly_financials, ["Total Revenue", "Revenue", "Revenues"], fecha
            )
            net_income = buscar_valor(
                quarterly_financials, ["Net Income", "Net Income Common Stockholders"], fecha
            )
            total_assets = buscar_valor(
                quarterly_balance, ["Total Assets", "Assets"], fecha
            )
            total_liab = buscar_valor(
                quarterly_balance, ["Total Liab", "Total Liabilities", "Liabilities"], fecha
            )
            book_value = total_assets - total_liab if (total_assets and total_liab) else None
            operating_cf = buscar_valor(
                quarterly_cashflow,
                ["Total Cash From Operating Activities", "Operating Cash Flow", "Cash From Operating Activities"],
                fecha,
            )

            year, month = None, None
            if hasattr(fecha, "year") and hasattr(fecha, "month"):
                year = fecha.year
                month = fecha.month
            elif hasattr(fecha, "strftime"):
                year = int(fecha.strftime("%Y"))
                month = int(fecha.strftime("%m"))
            else:
                fecha_str = str(fecha)
                if len(fecha_str) >= 7:
                    year = int(fecha_str[:4])
                    month = int(fecha_str[5:7])
                else:
                    continue

            mes_inicio = ((month - 1) // 3) * 3 + 1
            mes_fin = mes_inicio + 2
            precios_trimestre = hist[
                (hist.index.year == year)
                & (hist.index.month >= mes_inicio)
                & (hist.index.month <= mes_fin)
            ]
            precio_promedio = precios_trimestre["Close"].mean() if not precios_trimestre.empty else None

            shares_outstanding = None
            if quarterly_balance is not None:
                posibles_shares = [
                    "Share Issued",
                    "Shares Outstanding",
                    "Common Stock Shares Outstanding",
                ]
                for nombre in posibles_shares:
                    if nombre in quarterly_balance.index:
                        try:
                            shares_val = quarterly_balance.loc[nombre, fecha]
                            if pd.notna(shares_val) and shares_val > 0:
                                shares_outstanding = float(shares_val)
                                break
                        except Exception:
                            continue
            if not shares_outstanding:
                shares_outstanding = info.get("sharesOutstanding") if info else None
                if shares_outstanding:
                    shares_outstanding = float(shares_outstanding)
            if not shares_outstanding and precio_promedio:
                try:
                    market_cap = info.get("marketCap", 0)
                    if market_cap and precio_promedio:
                        shares_outstanding = market_cap / precio_promedio
                except Exception:
                    pass

            if not shares_outstanding or shares_outstanding <= 0:
                continue

            ratios = {}
            ratios["Net Margin"] = (
                (net_income / revenue) * 100 if net_income and revenue and revenue != 0 else None
            )

            if precio_promedio and revenue and shares_outstanding:
                market_cap = precio_promedio * shares_outstanding
                ratios["PS"] = market_cap / revenue if revenue != 0 else None
            else:
                ratios["PS"] = None

            if net_income and shares_outstanding and shares_outstanding != 0:
                eps = net_income / shares_outstanding
                ratios["PER"] = precio_promedio / eps if eps != 0 and precio_promedio else None
            else:
                ratios["PER"] = None

            if (
                precio_promedio
                and operating_cf
                and shares_outstanding
                and shares_outstanding != 0
            ):
                cf_per_share = operating_cf / shares_outstanding
                ratios["PCF"] = precio_promedio / cf_per_share if cf_per_share != 0 else None
            else:
                ratios["PCF"] = None

            if (
                precio_promedio
                and book_value
                and shares_outstanding
                and shares_outstanding != 0
            ):
                bv_per_share = book_value / shares_outstanding
                ratios["PBV"] = precio_promedio / bv_per_share if bv_per_share != 0 else None
            else:
                ratios["PBV"] = None

            trimestre_label = obtener_trimestre_label(fecha)
            ratios_data[trimestre_label] = ratios
        except Exception:
            continue

    if not ratios_data:
        return None

    ratios_nombres = {
        "Net Margin": "Net Margin (%)",
        "PS": "PS (Price to Sales)",
        "PER": "PER (P/E)",
        "PCF": "PCF (P/CF)",
        "PBV": "PBV (P/B)",
    }

    def ordenar_trimestres(trimestre_str):
        try:
            año, q = trimestre_str.split("-Q")
            return (int(año), int(q))
        except Exception:
            return (0, 0)

    trimestres_ordenados = sorted(ratios_data.keys(), key=ordenar_trimestres)

    figuras_ratios = {}
    for ratio_key, ratio_nombre in ratios_nombres.items():
        valores = [ratios_data[trimestre].get(ratio_key) for trimestre in trimestres_ordenados]
        trimestres_validos = [
            trimestre for trimestre, val in zip(trimestres_ordenados, valores) if val is not None
        ]
        valores_validos = [val for val in valores if val is not None]
        if not valores_validos:
            continue
        figuras_ratios[ratio_key] = {
            "trimestres": trimestres_validos,
            "valores": valores_validos,
            "nombre": ratio_nombre,
        }

    if return_data:
        return figuras_ratios, ratios_data
    return None

def formatear_valor_millions(valor):
    if pd.isna(valor) or valor is None:
        return "-"
    try:
        val = float(valor)
        if abs(val) >= 1e12:
            return f"{val/1e12:.2f}T"
        elif abs(val) >= 1e9:
            return f"${val/1e9:.2f}B"
        elif abs(val) >= 1e6:
            return f"${val/1e6:.2f}M"
        elif abs(val) >= 1e3:
            return f"${val/1e3:.2f}K"
        return f"${val:,.2f}"
    except:
        return str(valor)


def generar_tabla_financiera(df):
    if df is None or df.empty:
        return dbc.Alert("No hay datos disponibles", color="warning")
    
    # Limpiar filas vacías
    df_clean = df.dropna(how='all').fillna(0)
    df_clean = df_clean.loc[(df_clean != 0).any(axis=1)]
    
    # Ordenar columnas: Trimestre más viejo a la izquierda (ascending=True)
    df_clean = df_clean.sort_index(axis=1, ascending=True)
    
    # Formatear fechas de columnas
    columnas_nuevas = []
    for col in df_clean.columns:
        if hasattr(col, 'strftime'):
            columnas_nuevas.append(col.strftime('%Y-%m-%d'))
        else:
            columnas_nuevas.append(str(col))
    df_clean.columns = columnas_nuevas
    
    # Estilos base
    header_style = {
        "color": "#94a3b8",
        "fontWeight": "normal",
        "borderBottom": "1px solid #334155",
        "padding": "8px 4px",
        "fontSize": "0.8rem",
        "backgroundColor": "transparent"
    }
    
    cell_style = {
        "color": "#e2e8f0",
        "padding": "8px 4px",
        "borderBottom": "1px solid #1e293b",
        "fontSize": "0.8rem",
        "backgroundColor": "transparent"
    }

    header = [html.Th("METRIC", style={**header_style, "textAlign": "left"})]
    for col in columnas_nuevas:
        header.append(html.Th(col, style={**header_style, "textAlign": "right"}))

    rows = []
    for idx, row in df_clean.iterrows():
        label = str(idx)
        label_cell = html.Td(label, style={**cell_style, "textAlign": "left", "fontWeight": "500", "color": "#f8fafc"})
        
        cells = [label_cell]
        for val in row:
            formatted_val = formatear_valor_millions(val)
            current_style = {**cell_style, "textAlign": "right"}
            
            key_rows = ["Net Income", "Total Revenue", "Gross Profit", "Operating Income", "EBITDA", "Total Assets", "Total Liabilities", "Total Stockholder Equity", "Free Cash Flow"]
            if any(k in label for k in key_rows):
                 current_style["color"] = "#4ade80" 
                 current_style["fontWeight"] = "bold"
            
            cells.append(html.Td(formatted_val, style=current_style))
        
        rows.append(html.Tr(cells))

    return dbc.Table(
        [html.Thead(html.Tr(header)), html.Tbody(rows)],
        hover=True,
        responsive=True,
        className="table-borderless table-sm mb-0",
        style={"backgroundColor": "#0f172a", "color": "#e2e8f0"} # Forzar fondo oscuro en la tabla
    )


def obtener_balance_sheet_component(ticker_str: str):
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_balance = ticker.quarterly_balance_sheet
        if quarterly_balance is None or quarterly_balance.empty:
            return dbc.Alert("No se pudieron obtener datos del Balance Sheet.", color="warning")
        return generar_tabla_financiera(quarterly_balance)
    except Exception as e:
        return dbc.Alert(f"Error al obtener Balance Sheet: {e}", color="danger")


def obtener_income_statement_component(ticker_str: str):
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_financials = ticker.quarterly_financials
        if quarterly_financials is None or quarterly_financials.empty:
            return dbc.Alert("No se pudieron obtener datos del Income Statement.", color="warning")
        return generar_tabla_financiera(quarterly_financials)
    except Exception as e:
        return dbc.Alert(f"Error al obtener Income Statement: {e}", color="danger")


def obtener_cash_flow_component(ticker_str: str):
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_cashflow = ticker.quarterly_cashflow
        if quarterly_cashflow is None or quarterly_cashflow.empty:
            return dbc.Alert("No se pudieron obtener datos del Cash Flow Statement.", color="warning")
        return generar_tabla_financiera(quarterly_cashflow)
    except Exception as e:
        return dbc.Alert(f"Error al obtener Cash Flow Statement: {e}", color="danger")


def formatear_moneda(valor):
    try:
        if valor is None:
            return "N/A"
        return f"${valor:,.2f}"
    except Exception:
        return str(valor or "N/A")


def formatear_porcentaje(valor):
    try:
        if valor is None:
            return "N/A"
        return f"{valor * 100:.2f}%"
    except Exception:
        return str(valor or "N/A")


def construir_texto_informacion(datos):
    if not datos:
        return "No se encontraron datos para el ticker seleccionado."

    lines = [
        f"Ticker: {datos['ticker']}",
        f"Nombre: {datos['short_name'] or 'N/A'}",
        f"Sector: {datos['sector'] or 'N/A'}",
        f"Precio actual: {formatear_moneda(datos.get('precio_actual'))}",
        f"EPS trailing: {datos.get('trailing_eps'):.2f}" if datos.get("trailing_eps") else "EPS trailing: N/A",
        f"EPS forward: {datos.get('forward_eps'):.2f}" if datos.get("forward_eps") else "EPS forward: N/A",
        f"Trailing P/E: {datos.get('trailing_pe'):.2f}" if datos.get("trailing_pe") else "Trailing P/E: N/A",
        f"Forward P/E: {datos.get('forward_pe'):.2f}" if datos.get("forward_pe") else "Forward P/E: N/A",
        f"Dividendo anual: {formatear_moneda(datos.get('dividendo_anual'))}",
        f"Dividend yield (último año): {formatear_porcentaje(datos.get('dividend_yield'))}",
        f"Avg Div Yield 5 años: {formatear_porcentaje(datos.get('five_year_avg_div_yield'))}",
        f"Valor en libros: {formatear_moneda(datos.get('book_value'))}",
    ]

    return "\n".join(lines)


def construir_texto_valoracion(datos, r, g):
    pe_justo = estimar_pe_justo(datos)
    eps_usado = datos.get("forward_eps") or datos.get("trailing_eps")
    fv_pe = valor_justo_por_pe(eps_usado, pe_justo) if eps_usado else None
    fv_div = valor_justo_dividendos(datos.get("dividendo_anual"), r, g)
    fv_book = None
    if datos.get("book_value"):
        fv_book = datos["book_value"] * 1.2

    fair_values = [v for v in [fv_pe, fv_div, fv_book] if v]
    fv_promedio = sum(fair_values) / len(fair_values) if fair_values else None

    lines = [
        f"Precio actual: {formatear_moneda(datos.get('precio_actual'))}",
        f"P/E 'justo' estimado: {pe_justo:.2f}",
        f"Valor justo por P/E: {formatear_moneda(fv_pe) if fv_pe else 'N/A'}",
        f"Valor justo por Dividendos (r={r}, g={g}): {formatear_moneda(fv_div) if fv_div else 'N/A'}",
        f"Valor justo por valor en libros: {formatear_moneda(fv_book) if fv_book else 'N/A'}",
        f"Valor justo promedio: {formatear_moneda(fv_promedio) if fv_promedio else 'N/A'}",
    ]

    if fv_promedio and datos.get("precio_actual"):
        upside = (fv_promedio / datos["precio_actual"] - 1) * 100
        lines.append(f"Upside/Downside estimado: {upside:+.2f}%")

    return "\n".join(lines)


def construir_graficas_ratio(figuras, ticker):
    if not figuras:
        return [
            dbc.Alert(
                "No se pudieron calcular los ratios históricos. Intenta nuevamente.",
                color="warning",
            )
        ]

    cards = []
    for ratio_key, data in figuras.items():
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=data["trimestres"],
                y=data["valores"],
                mode="lines+markers",
                name=data["nombre"],
                line=dict(width=2, shape="spline"),
                marker=dict(size=6),
            )
        )

        fig.update_layout(
            template="plotly_white",
            margin=dict(l=20, r=20, t=30, b=20),
            title=f"{data['nombre']} - {ticker}",
            yaxis_title=data["nombre"],
            xaxis_title="Trimestre",
            height=320,
        )

        cards.append(
            dbc.Card(
                dbc.CardBody(
                    dcc.Graph(figure=fig, config={"displayModeBar": False})
                ),
                className="mb-4",
            )
        )

    return cards


app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Estimador de Valor Justo",
)

sidebar_links = [
    {"label": "Dashboard", "icon": "🏠", "id": "sidebar-link-dashboard"},
    {"label": "Análisis Técnico", "icon": "📈", "id": "sidebar-link-analisis-tecnico"},
    {"label": "Análisis Fundamental", "icon": "🧾", "id": "sidebar-link-analisis-fundamental"},
    {"label": "Noticias", "icon": "📰", "id": "sidebar-link-noticias"},
]

news_items = [
    {
        "title": "La Fed mantiene las tasas de interés en espera para no frenar el crecimiento.",
        "source": "Bloomberg",
        "time": "Hace 15 minutos",
    },
    {
        "title": "Resultados trimestrales de NVDA superan expectativas; las acciones suben un 8%.",
        "source": "Reuters",
        "time": "Hace 1 hora",
    },
    {
        "title": "El sector tecnológico lidera las ganancias del S&P 500 en la sesión de hoy.",
        "source": "MarketWatch",
        "time": "Hace 2 horas",
    },
    {
        "title": "¿Es momento de invertir en mercados emergentes? Analistas debaten la estrategia.",
        "source": "The Wall Street Journal",
        "time": "Hace 3 horas",
    },
]

nav_ids = [link["id"] for link in sidebar_links]

sidebar = html.Div(
    [
        html.Div(
            [
                html.Div("Plataforma", className="h5 mb-1 text-white"),
                html.Div("Trading", className="text-muted small"),
            ],
            className="pb-3",
        ),
        html.Div(
            [
                html.Img(
                    src="https://avatars.dicebear.com/api/initials/Carlos-M.svg",
                    style={"width": "48px", "borderRadius": "16px", "marginRight": "0.75rem"},
                ),
                html.Div(
                    [
                        html.Strong("Carlos Martín", className="d-block text-white"),
                        html.Small("carlos.m@email.com", className="text-muted"),
                    ]
                ),
            ],
            className="d-flex align-items-center gap-2 mb-4",
        ),
        dbc.Nav(
            [
                dbc.NavLink(
                    [html.Span(link["icon"], className="me-2"), link["label"]],
                    href="#",
                    id=link["id"],
                    active=idx == 0,
                    className="text-white",
                )
                for idx, link in enumerate(sidebar_links)
            ],
            vertical=True,
            pills=True,
            className="gap-2 mt-2",
        ),
        html.Div(
            [
                html.Small("Version 3.4", className="text-muted"),
                html.Div("© 2025 Inversiones", className="text-muted small"),
            ],
            className="mt-auto pt-3",
        ),
    ],
    style={
        "backgroundColor": "#0f172a",
        "borderRadius": "1.25rem",
        "padding": "1.5rem",
        "border": "1px solid #1f2937",
        "height": "100%",
        "display": "flex",
        "flexDirection": "column",
    },
)

search_card = dbc.Card(
    dbc.CardBody(
        [
            html.H4("Busca una acción para analizar", className="text-white"),
            html.P(
                "Ingresa el nombre o ticker de la empresa (ej: AAPL, TSLA, GOOGL).",
                className="text-muted",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Input(
                            id="ticker-input",
                            type="text",
                            placeholder="Ej: AAPL",
                            value="AAPL",
                            style={
                                "height": "56px",
                                "borderRadius": "0.75rem",
                                "padding": "0 1rem",
                                "fontSize": "1rem",
                            },
                            className="w-100",
                        ),
                        md=8,
                    ),
                    dbc.Col(
                        dbc.Button(
                            "Analizar",
                            id="btn-analizar",
                            color="success",
                            className="w-100",
                            style={"height": "56px", "borderRadius": "0.75rem"},
                        ),
                        md=4,
                    ),
                ],
                className="g-2 mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Input(
                            id="tasa-r",
                            type="number",
                            placeholder="Tasa retorno (r)",
                            value=0.10,
                            min=0,
                            step=0.01,
                            style={
                                "height": "48px",
                                "borderRadius": "0.75rem",
                                "padding": "0 1rem",
                            },
                            className="w-100",
                        ),
                        md=6,
                    ),
                    dbc.Col(
                        dcc.Input(
                            id="tasa-g",
                            type="number",
                            placeholder="Tasa crecimiento (g)",
                            value=0.03,
                            min=0,
                            step=0.005,
                            style={
                                "height": "48px",
                                "borderRadius": "0.75rem",
                                "padding": "0 1rem",
                            },
                            className="w-100",
                        ),
                        md=6,
                    ),
                ],
                className="g-2",
            ),
        ]
    ),
    style={"backgroundColor": "#0f172a", "border": "1px solid #1f2937", "borderRadius": "1.25rem"},
)

dashboard_section = html.Div(
    search_card,
    id="dashboard-section",
    style={"display": "block"},
)

tabs_card = dbc.Card(
    [
        dbc.CardHeader(html.H5("Análisis Fundamental", className="mb-0 text-white"), className="bg-transparent border-0"),
        dbc.CardBody(
            dbc.Tabs(
                [
                    dbc.Tab(
                        [
                            dbc.Tabs(
                                [
                                    dbc.Tab(
                                        dcc.Loading(
                                            html.Div(
                                                id="income-text",
                                                className="table-responsive",
                                                style={"minHeight": "220px"},
                                            ),
                                            type="default",
                                        ),
                                        label="Income Statement",
                                        tab_id="subtab-income",
                                    ),
                                    dbc.Tab(
                                        dcc.Loading(
                                            html.Div(
                                                id="balance-text",
                                                className="table-responsive",
                                                style={"minHeight": "220px"},
                                            ),
                                            type="default",
                                        ),
                                        label="Balance Sheet",
                                        tab_id="subtab-balance",
                                    ),
                                    dbc.Tab(
                                        dcc.Loading(
                                            html.Div(
                                                id="cashflow-text",
                                                className="table-responsive",
                                                style={"minHeight": "220px"},
                                            ),
                                            type="default",
                                        ),
                                        label="Cash Flow",
                                        tab_id="subtab-cashflow",
                                    ),
                                ],
                                active_tab="subtab-income",
                                className="mt-2",
                            )
                        ],
                        label="Financials",
                        tab_id="tab-financials",
                    ),
                    dbc.Tab(
                        dcc.Loading(
                            html.Div(
                                id="ratio-graphs",
                                style={"minHeight": "220px"},
                            ),
                            type="default",
                        ),
                        label="Metrics",
                        tab_id="tab-metrics",
                    ),
                    dbc.Tab(
                        dcc.Loading(
                            html.Pre(
                                id="info-text",
                                className="text-white",
                                style={
                                    "backgroundColor": "#020617",
                                    "border": "none",
                                    "whiteSpace": "pre-line",
                                    "minHeight": "220px",
                                    "padding": "0.75rem",
                                },
                            ),
                            type="default",
                        ),
                        label="Summary",
                        tab_id="tab-summary",
                    ),
                    dbc.Tab(
                        dcc.Loading(
                            html.Pre(
                                id="valoracion-text",
                                className="text-white",
                                style={
                                    "backgroundColor": "#020617",
                                    "border": "none",
                                    "whiteSpace": "pre-line",
                                    "minHeight": "220px",
                                    "padding": "0.75rem",
                                },
                            ),
                            type="default",
                        ),
                        label="Valuation",
                        tab_id="tab-valuation",
                    ),
                ],
                active_tab="tab-financials",
                className="mt-2",
                style={"gap": "0.75rem"},
            )
        ),
    ],
    style={"backgroundColor": "#0f172a", "border": "1px solid #1f2937", "borderRadius": "1.25rem"},
    className="mb-4",
)

fundamental_section = html.Div(
    tabs_card,
    id="fundamental-section",
    style={"display": "none"},
)

technical_section = html.Div(
    dbc.Card(
        [
            dbc.CardHeader(html.H5("Análisis técnico", className="mb-0 text-white"), className="bg-transparent border-0"),
            dbc.CardBody(
                [
                    html.Div(
                        [
                            html.Span("Temporalidad:", className="text-white me-2"),
                            html.Div(
                                [
                                    dbc.Button(
                                        TIMEFRAME_OPTIONS[key]["label"],
                                        id=f"btn-timeframe-{key}",
                                        color="success" if key == "1d" else "dark",
                                        outline=False,
                                        size="sm",
                                        style={
                                            "borderRadius": "999px",
                                            "padding": "0.25rem 0.9rem",
                                            "marginRight": "0.35rem",
                                            "minWidth": "48px",
                                        },
                                        n_clicks=0,
                                    )
                                    for key in TIMEFRAME_KEYS
                                ],
                                className="d-flex flex-wrap",
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.Div(
                        [
                            html.Span("Tipo de gráfica:", className="text-white me-2"),
                            html.Div(
                                [
                                    dbc.Button(
                                        chart.title(),
                                        id=f"btn-chart-{chart}",
                                        color="success" if chart == "candlestick" else "dark",
                                        outline=False,
                                        size="sm",
                                        style={
                                            "borderRadius": "999px",
                                            "padding": "0.25rem 0.9rem",
                                            "marginRight": "0.35rem",
                                            "minWidth": "80px",
                                        },
                                        n_clicks=0,
                                    )
                                    for chart in CHART_TYPES
                                ],
                                className="d-flex flex-wrap",
                            ),
                        ],
                        className="mb-3",
                    ),
                    dcc.Loading(
                        dcc.Graph(id="technical-chart", config={"displayModeBar": False}),
                        type="default",
                    ),
                    html.Div(id="technical-status", className="text-muted small mt-2"),
                ]
            ),
        ],
        style={"backgroundColor": "#0f172a", "border": "1px solid #1f2937", "borderRadius": "1.25rem"},
    ),
    id="technical-section",
    style={"display": "none"},
)

timeframe_store = dcc.Store(id="technical-timeframe-store", data="1d")
chart_type_store = dcc.Store(id="technical-charttype-store", data="candlestick")

news_panel = html.Div(
    [
        html.Div(
            [html.H5("Noticias del mercado", className="text-white mb-0")],
            className="mb-3",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.P(item["title"], className="text-white mb-1"),
                        html.Small(
                            f"{item['source']} - {item['time']}", className="text-muted"
                        ),
                    ],
                    style={
                        "borderBottom": "1px solid #1f2937" if idx < len(news_items) - 1 else "none",
                        "paddingBottom": "0.75rem",
                        "marginBottom": "0.75rem",
                    },
                )
                for idx, item in enumerate(news_items)
            ]
        ),
        ],
    style={
        "backgroundColor": "#0f172a",
        "border": "1px solid #1f2937",
        "borderRadius": "1.25rem",
        "padding": "1.5rem",
        "minHeight": "100%",
    },
)

app.layout = html.Div(
    style={"backgroundColor": "#020617", "minHeight": "100vh", "color": "#f8fafc"},
    children=[
        dbc.Container(
            fluid=True,
            className="py-4 px-3",
            children=[
                dbc.Row(
                    [
                        dbc.Col(sidebar, md=3, className="pe-3"),
                        dbc.Col(
                            html.Div(
                                [
                                    dashboard_section,
                                    fundamental_section,
                                    technical_section,
                                ],
                                className="main-column",
                            ),
                            md=6,
                            id="main-col",
                        ),
                        dbc.Col(news_panel, md=3, className="ps-3", id="news-col"),
                    ],
                    className="g-4",
                )
            ],
        ),
        timeframe_store,
        chart_type_store,
    ],
)


@app.callback(
    [Output("technical-timeframe-store", "data")]
    + [Output(btn_id, "color") for btn_id in TIMEFRAME_BUTTON_IDS],
    [Input(btn_id, "n_clicks") for btn_id in TIMEFRAME_BUTTON_IDS],
    State("technical-timeframe-store", "data"),
)
def actualizar_botones_timeframe(*args):
    ctx = callback_context
    if not ctx.triggered:
        active = "1d"
    else:
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        active = trigger_id.replace("btn-timeframe-", "")

    colors = ["success" if key == active else "dark" for key in TIMEFRAME_KEYS]
    return [
        active,
        *colors,
    ]


@app.callback(
    Output("info-text", "children"),
    Output("balance-text", "children"),
    Output("income-text", "children"),
    Output("cashflow-text", "children"),
    Output("valoracion-text", "children"),
    Output("ratio-graphs", "children"),
    Input("btn-analizar", "n_clicks"),
    State("ticker-input", "value"),
    State("tasa-r", "value"),
    State("tasa-g", "value"),
)
def actualizar_resultados(n_clicks, ticker, tasa_r, tasa_g):
    if not n_clicks:
        raise PreventUpdate

    ticker = (ticker or "").strip().upper()
    if not ticker:
        mensaje = "Escribe un ticker válido antes de analizar."
        return (
            mensaje,
            "",
            "",
            "",
            "",
            [dbc.Alert(mensaje, color="warning")],
        )

    tasa_r = float(tasa_r or 0.10)
    tasa_g = float(tasa_g or 0.03)

    try:
        datos = obtener_datos(ticker)
        info_text = construir_texto_informacion(datos)
        balance_text = obtener_balance_sheet_component(ticker)
        income_text = obtener_income_statement_component(ticker)
        cashflow_text = obtener_cash_flow_component(ticker)
        valoracion_text = construir_texto_valoracion(datos, tasa_r, tasa_g)

        resultado_ratios = graficar_ratios_historicos(ticker, return_data=True)
        if resultado_ratios:
            figuras, _ = resultado_ratios
            ratio_graphs = construir_graficas_ratio(figuras, ticker)
        else:
            ratio_graphs = [
                dbc.Alert(
                    "No se pudieron generar las gráficas de ratios.",
                    color="danger",
                )
            ]

        return (
            info_text,
            balance_text,
            income_text,
            cashflow_text,
            valoracion_text,
            ratio_graphs,
        )

    except Exception as exc:
        mensaje_error = f"⚠️ Error al analizar el ticker: {exc}"
        alerta = dbc.Alert(mensaje_error, color="danger")
        return (mensaje_error, "", "", "", "", [alerta])


def crear_figura_tecnica(hist, chart_type):
    if chart_type == "line":
        fig = go.Figure(
            data=[
                go.Scatter(
                    x=hist.index,
                    y=hist["Close"],
                    mode="lines",
                    line=dict(color="#4ade80", width=2),
                    name="Precio",
                )
            ]
        )
    else:
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=hist.index,
                    open=hist["Open"],
                    high=hist["High"],
                    low=hist["Low"],
                    close=hist["Close"],
                    increasing_line_color="#4ade80",
                    decreasing_line_color="#f87171",
                    showlegend=False,
                )
            ]
        )
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#1f2937"),
        font=dict(color="#e2e8f0"),
        height=380,
    )
    return fig


@app.callback(
    Output("technical-chart", "figure"),
    Output("technical-status", "children"),
    Input("btn-analizar", "n_clicks"),
    Input("technical-timeframe-store", "data"),
    Input("technical-charttype-store", "data"),
    State("ticker-input", "value"),
)
def actualizar_chart_tecnico(n_clicks, timeframe, chart_type, ticker):
    if not ticker:
        return go.Figure(), "Ingresa un ticker para ver el análisis técnico."

    ticker_str = ticker.strip().upper()
    opciones = TIMEFRAME_OPTIONS.get(timeframe, TIMEFRAME_OPTIONS["1d"])
    try:
        ticker_obj = yf.Ticker(ticker_str)
        hist = ticker_obj.history(period=opciones["period"], interval=opciones["interval"])
    except Exception as exc:
        return go.Figure(), f"Error al obtener datos técnicos: {exc}"

    if hist.empty:
        return go.Figure(), "No hay datos disponibles para esa temporalidad."

    fig = crear_figura_tecnica(hist, chart_type)
    return fig, ""


@app.callback(
    Output("dashboard-section", "style"),
    Output("fundamental-section", "style"),
    Output("technical-section", "style"),
    Output("main-col", "style"),
    Output("news-col", "style"),
    Input("sidebar-link-dashboard", "n_clicks"),
    Input("sidebar-link-analisis-fundamental", "n_clicks"),
    Input("sidebar-link-analisis-tecnico", "n_clicks"),
)
def mostrar_seccion_principal(n_dashboard, n_fundamental, n_tecnico):
    ctx = callback_context
    default_main_style = {}
    default_news_style = {}
    tech_main_style = {"flex": "0 0 75%", "maxWidth": "75%"}
    tech_news_style = {"display": "none"}
    fundamental_main_style = {"flex": "0 0 75%", "maxWidth": "75%"}
    fundamental_news_style = {"display": "none"}

    if not ctx.triggered:
        return (
            {"display": "block"},
            {"display": "none"},
            {"display": "none"},
            default_main_style,
            default_news_style,
        )

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "sidebar-link-dashboard":
        return (
            {"display": "block"},
            {"display": "none"},
            {"display": "none"},
            default_main_style,
            default_news_style,
        )
    if trigger_id == "sidebar-link-analisis-fundamental":
        return (
            {"display": "none"},
            {"display": "block"},
            {"display": "none"},
            fundamental_main_style,
            fundamental_news_style,
        )
    if trigger_id == "sidebar-link-analisis-tecnico":
        return (
            {"display": "none"},
            {"display": "none"},
            {"display": "block"},
            tech_main_style,
            tech_news_style,
        )

    return (
        {"display": "block"},
        {"display": "none"},
        {"display": "none"},
        default_main_style,
        default_news_style,
    )


@app.callback(
    [Output(btn_id, "color") for btn_id in CHART_BUTTON_IDS]
    + [Output("technical-charttype-store", "data")],
    [Input(btn_id, "n_clicks") for btn_id in CHART_BUTTON_IDS],
    State("technical-charttype-store", "data"),
)
def actualizar_tipo_chart(*args):
    ctx = callback_context
    if not ctx.triggered:
        active = "candlestick"
    else:
        active = ctx.triggered[0]["prop_id"].split(".")[0].replace("btn-chart-", "")

    colors = ["success" if chart == active else "dark" for chart in CHART_TYPES]
    return [*colors, active]

@app.callback(
    [Output(nav_id, "active") for nav_id in nav_ids]
    + [Output(nav_id, "style") for nav_id in nav_ids],
    [Input(nav_id, "n_clicks") for nav_id in nav_ids],
)
def resaltar_sidebar(*clicks):
    ctx = callback_context
    if not ctx.triggered:
        active_id = nav_ids[0]
    else:
        active_id = ctx.triggered[0]["prop_id"].split(".")[0]

    base_style = {
        "fontWeight": "500",
        "display": "flex",
        "alignItems": "center",
        "gap": "0.5rem",
        "padding": "0.65rem 0.75rem",
        "borderRadius": "0.75rem",
        "transition": "background-color 0.2s, color 0.2s",
    }

    outputs = []
    for nav_id in nav_ids:
        is_active = nav_id == active_id
        outputs.append(is_active)
    for nav_id in nav_ids:
        style = base_style.copy()
        if nav_id == active_id:
            style.update({"color": "#bbf7d0", "backgroundColor": "#065f46"})
        else:
            style.update({"color": "#d1d5db", "backgroundColor": "transparent"})
        outputs.append(style)
    return outputs


if __name__ == "__main__":
    app.run(debug=True)

