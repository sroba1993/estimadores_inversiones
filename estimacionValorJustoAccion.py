import yfinance as yf
import investpy as ip
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import pandas as pd
from datetime import datetime, timedelta
import warnings
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading

warnings.filterwarnings('ignore')

def obtener_datos(ticker_str: str):
    """
    Descarga los datos básicos de la acción usando yfinance.
    Devuelve un dict con los campos necesarios para hacer los cálculos.
    """
    ticker = yf.Ticker(ticker_str)

    info = ticker.get_info() if hasattr(ticker, "get_info") else ticker.info

    datos = {
        "ticker": ticker_str,
        "precio_actual": info.get("currentPrice"),
        "trailing_eps": info.get("trailingEps"),
        "forward_eps": info.get("forwardEps"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividendo_anual": info.get("dividendRate"),      # dividendo anual por acción
        "dividend_yield": info.get("dividendYield"),      # en decimal, ej: 0.025 = 2.5%
        "five_year_avg_div_yield": info.get("fiveYearAvgDividendYield"),
        "book_value": info.get("bookValue"),              # valor en libros por acción
        "sector": info.get("sector"),
        "short_name": info.get("shortName")
    }

    return datos

def valor_justo_por_pe(eps, pe_justo):
    """
    Valor justo simple por múltiplo P/E:
    fair_value = EPS * P/E “razonable”.
    """
    if eps is None or pe_justo is None:
        return None
    return eps * pe_justo

def valor_justo_dividendos(dividendo_anual, tasa_descuento, tasa_crecimiento):
    """
    Modelo de Gordon (Dividend Discount Model):
    Valor = D1 / (r - g) = dividendo_anual * (1+g) / (r - g)
    donde:
        r = tasa de retorno requerida
        g = tasa de crecimiento esperada del dividendo
    Todas en DECIMAL (0.10 = 10%)
    """
    if not dividendo_anual or tasa_descuento <= tasa_crecimiento:
        return None
    return dividendo_anual * (1 + tasa_crecimiento) / (tasa_descuento - tasa_crecimiento)

def estimar_pe_justo(datos, pe_min=8, pe_max=20):
    """
    Estima un P/E “razonable” a partir de:
      - trailing PE
      - forward PE
    Acota entre pe_min y pe_max para evitar valores extremos.
    """
    trailing = datos.get("trailing_pe")
    forward = datos.get("forward_pe")

    # Si hay ambos, promediamos, sino usamos el que exista, sino un default 15
    if trailing and forward:
        pe_base = (trailing + forward) / 2
    elif trailing:
        pe_base = trailing
    elif forward:
        pe_base = forward
    else:
        pe_base = 15.0  # valor por defecto

    # Acotar a un rango razonable
    pe_justo = max(pe_min, min(pe_base, pe_max))
    return pe_justo


def obtener_balance_sheet_text(ticker_str: str) -> str:
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_balance = ticker.quarterly_balance_sheet

        if quarterly_balance is None or quarterly_balance.empty:
            return "⚠️  No se pudieron obtener datos del Balance Sheet trimestral.\n\n" \
                   "Posibles razones:\n" \
                   "- El ticker no existe o no está disponible en Yahoo Finance\n" \
                   "- La empresa no reporta estados financieros trimestrales\n" \
                   "- Problemas de conexión con Yahoo Finance"

        ultimo_trimestre = quarterly_balance.columns[0]
        if hasattr(ultimo_trimestre, 'strftime'):
            fecha_str = ultimo_trimestre.strftime('%Y-%m-%d')
        else:
            fecha_str = str(ultimo_trimestre)

        balance_text = f"=== BALANCE SHEET - ÚLTIMO TRIMESTRE ===\n\n"
        balance_text += f"Fecha del reporte: {fecha_str}\n"
        balance_text += f"Ticker: {ticker_str}\n\n"
        balance_text += "=" * 70 + "\n\n"

        def formatear_valor(valor):
            if pd.isna(valor) or valor is None:
                return "N/A"
            try:
                valor_float = float(valor)
                if abs(valor_float) >= 1e9:
                    return f"${valor_float/1e9:.2f}B"
                elif abs(valor_float) >= 1e6:
                    return f"${valor_float/1e6:.2f}M"
                elif abs(valor_float) >= 1e3:
                    return f"${valor_float/1e3:.2f}K"
                else:
                    return f"${valor_float:,.2f}"
            except:
                return str(valor)

        ultimo_valor = quarterly_balance[ultimo_trimestre]

        activos = []
        pasivos = []
        patrimonio = []
        otros = []

        cuentas_activos = [
            'Cash And Cash Equivalents', 'Cash', 'Cash And Short Term Investments',
            'Short Term Investments', 'Net Receivables', 'Inventory',
            'Other Current Assets', 'Total Current Assets',
            'Property Plant Equipment', 'Good Will', 'Intangible Assets',
            'Long Term Investments', 'Other Assets', 'Total Assets'
        ]

        cuentas_pasivos = [
            'Accounts Payable', 'Short Long Term Debt', 'Short Term Debt',
            'Other Current Liab', 'Total Current Liabilities',
            'Long Term Debt', 'Other Liab', 'Total Liab', 'Total Liabilities'
        ]

        cuentas_patrimonio = [
            'Common Stock', 'Retained Earnings', 'Treasury Stock',
            'Other Stockholder Equity', 'Total Stockholder Equity',
            'Total Stockholders Equity'
        ]

        for cuenta in quarterly_balance.index:
            cuenta_str = str(cuenta)
            valor = ultimo_valor.get(cuenta)

            if any(activo in cuenta_str for activo in cuentas_activos):
                activos.append((cuenta_str, valor))
            elif any(pasivo in cuenta_str for pasivo in cuentas_pasivos):
                pasivos.append((cuenta_str, valor))
            elif any(pat in cuenta_str for pat in cuentas_patrimonio):
                patrimonio.append((cuenta_str, valor))
            else:
                otros.append((cuenta_str, valor))

        balance_text += "ACTIVOS\n"
        balance_text += "-" * 70 + "\n"
        if activos:
            for cuenta, valor in activos:
                balance_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            balance_text += "No hay datos de activos disponibles\n"

        balance_text += "\n"

        balance_text += "PASIVOS\n"
        balance_text += "-" * 70 + "\n"
        if pasivos:
            for cuenta, valor in pasivos:
                balance_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            balance_text += "No hay datos de pasivos disponibles\n"

        balance_text += "\n"

        balance_text += "PATRIMONIO\n"
        balance_text += "-" * 70 + "\n"
        if patrimonio:
            for cuenta, valor in patrimonio:
                balance_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            balance_text += "No hay datos de patrimonio disponibles\n"

        balance_text += "\n"

        if otros:
            balance_text += "OTRAS CUENTAS\n"
            balance_text += "-" * 70 + "\n"
            for cuenta, valor in otros:
                balance_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
            balance_text += "\n"

        total_activos = ultimo_valor.get('Total Assets')
        total_pasivos = ultimo_valor.get('Total Liab') or ultimo_valor.get('Total Liabilities')
        total_patrimonio = ultimo_valor.get('Total Stockholder Equity') or ultimo_valor.get('Total Stockholders Equity')

        if total_activos and (total_pasivos or total_patrimonio):
            balance_text += "=" * 70 + "\n"
            balance_text += "VERIFICACIÓN DEL BALANCE\n"
            balance_text += "-" * 70 + "\n"
            balance_text += f"Total Activos:     {formatear_valor(total_activos)}\n"
            if total_pasivos:
                balance_text += f"Total Pasivos:     {formatear_valor(total_pasivos)}\n"
            if total_patrimonio:
                balance_text += f"Total Patrimonio:  {formatear_valor(total_patrimonio)}\n"

            suma_pasivos_patrimonio = (total_pasivos or 0) + (total_patrimonio or 0)
            balance_text += f"Pasivos + Patrimonio: {formatear_valor(suma_pasivos_patrimonio)}\n"

            diferencia = abs(float(total_activos) - suma_pasivos_patrimonio) if total_activos and suma_pasivos_patrimonio else None
            if diferencia is not None and diferencia < 1000:
                balance_text += "\n✓ El balance cuadra correctamente.\n"
            elif diferencia is not None:
                balance_text += f"\n⚠️  Diferencia: {formatear_valor(diferencia)}\n"

        balance_text += "\n" + "=" * 70 + "\n"
        balance_text += f"\nNota: Los valores están en la moneda reportada por la empresa.\n"
        balance_text += f"Fecha de obtención: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return balance_text
    except Exception as e:
        return f"❌ Error al obtener el Balance Sheet:\n{str(e)}\n\nPor favor, verifica que el ticker sea correcto y que Yahoo Finance tenga datos disponibles."


def obtener_income_statement_text(ticker_str: str) -> str:
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_financials = ticker.quarterly_financials

        if quarterly_financials is None or quarterly_financials.empty:
            return "⚠️  No se pudieron obtener datos del Income Statement trimestral.\n\n" \
                   "Posibles razones:\n" \
                   "- El ticker no existe o no está disponible en Yahoo Finance\n" \
                   "- La empresa no reporta estados financieros trimestrales\n" \
                   "- Problemas de conexión con Yahoo Finance"

        ultimo_trimestre = quarterly_financials.columns[0]
        if hasattr(ultimo_trimestre, 'strftime'):
            fecha_str = ultimo_trimestre.strftime('%Y-%m-%d')
        else:
            fecha_str = str(ultimo_trimestre)

        income_text = f"=== INCOME STATEMENT - ÚLTIMO TRIMESTRE ===\n\n"
        income_text += f"Fecha del reporte: {fecha_str}\n"
        income_text += f"Ticker: {ticker_str}\n\n"
        income_text += "=" * 70 + "\n\n"

        def formatear_valor(valor):
            if pd.isna(valor) or valor is None:
                return "N/A"
            try:
                valor_float = float(valor)
                if abs(valor_float) >= 1e9:
                    return f"${valor_float/1e9:.2f}B"
                elif abs(valor_float) >= 1e6:
                    return f"${valor_float/1e6:.2f}M"
                elif abs(valor_float) >= 1e3:
                    return f"${valor_float/1e3:.2f}K"
                else:
                    return f"${valor_float:,.2f}"
            except:
                return str(valor)

        ultimo_valor = quarterly_financials[ultimo_trimestre]

        ingresos = []
        costos = []
        gastos_operativos = []
        otros_ingresos_gastos = []
        impuestos = []
        utilidad = []
        otros = []

        cuentas_ingresos = [
            'Total Revenue', 'Revenue', 'Revenues', 'Net Sales', 'Sales',
            'Operating Revenue', 'Gross Revenue'
        ]
        cuentas_costos = [
            'Cost Of Revenue', 'Cost Of Goods Sold', 'Cost Of Sales',
            'Total Cost Of Revenue'
        ]
        cuentas_gastos_operativos = [
            'Research Development', 'Selling General Administrative',
            'Selling And Marketing Expenses', 'General And Administrative Expenses',
            'Operating Expenses', 'Total Operating Expenses'
        ]
        cuentas_otros_ingresos_gastos = [
            'Interest Expense', 'Interest Income', 'Other Income Expense',
            'Other Operating Expenses', 'Non Recurring', 'Extraordinary Items',
            'Discontinued Operations', 'Other Items'
        ]
        cuentas_impuestos = [
            'Income Tax Expense', 'Tax Provision', 'Income Before Tax',
            'Tax Effect Of Unusual Items'
        ]
        cuentas_utilidad = [
            'Gross Profit', 'Operating Income', 'Operating Income Or Loss',
            'Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Ops',
            'Net Income Applicable To Common Shares', 'Ebit', 'Ebitda'
        ]

        for cuenta in quarterly_financials.index:
            cuenta_str = str(cuenta)
            valor = ultimo_valor.get(cuenta)

            if any(ingreso in cuenta_str for ingreso in cuentas_ingresos):
                ingresos.append((cuenta_str, valor))
            elif any(costo in cuenta_str for costo in cuentas_costos):
                costos.append((cuenta_str, valor))
            elif any(gasto in cuenta_str for gasto in cuentas_gastos_operativos):
                gastos_operativos.append((cuenta_str, valor))
            elif any(util in cuenta_str for util in cuentas_utilidad):
                utilidad.append((cuenta_str, valor))
            elif any(imp in cuenta_str for imp in cuentas_impuestos):
                impuestos.append((cuenta_str, valor))
            elif any(otro in cuenta_str for otro in cuentas_otros_ingresos_gastos):
                otros_ingresos_gastos.append((cuenta_str, valor))
            else:
                otros.append((cuenta_str, valor))

        income_text += "INGRESOS\n"
        income_text += "-" * 70 + "\n"
        if ingresos:
            for cuenta, valor in ingresos:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            income_text += "No hay datos de ingresos disponibles\n"

        income_text += "\n"

        income_text += "COSTOS\n"
        income_text += "-" * 70 + "\n"
        if costos:
            for cuenta, valor in costos:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            income_text += "No hay datos de costos disponibles\n"

        income_text += "\n"

        total_revenue = ultimo_valor.get('Total Revenue') or ultimo_valor.get('Revenue') or ultimo_valor.get('Revenues')
        cost_of_revenue = ultimo_valor.get('Cost Of Revenue') or ultimo_valor.get('Cost Of Goods Sold')
        gross_profit = ultimo_valor.get('Gross Profit')

        if gross_profit is None and total_revenue and cost_of_revenue:
            try:
                gross_profit = float(total_revenue) - float(cost_of_revenue)
            except:
                pass

        if gross_profit:
            income_text += "UTILIDAD BRUTA\n"
            income_text += "-" * 70 + "\n"
            income_text += f"{'Gross Profit':.<50} {formatear_valor(gross_profit):>15}\n"
            income_text += "\n"

        income_text += "GASTOS OPERATIVOS\n"
        income_text += "-" * 70 + "\n"
        if gastos_operativos:
            for cuenta, valor in gastos_operativos:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            income_text += "No hay datos de gastos operativos disponibles\n"

        income_text += "\n"

        operating_income = ultimo_valor.get('Operating Income') or ultimo_valor.get('Ebit')
        if operating_income:
            income_text += "UTILIDAD OPERATIVA\n"
            income_text += "-" * 70 + "\n"
            income_text += f"{'Operating Income (EBIT)':.<50} {formatear_valor(operating_income):>15}\n"
            income_text += "\n"

        if otros_ingresos_gastos:
            income_text += "OTROS INGRESOS Y GASTOS\n"
            income_text += "-" * 70 + "\n"
            for cuenta, valor in otros_ingresos_gastos:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
            income_text += "\n"

        if impuestos:
            income_text += "IMPUESTOS\n"
            income_text += "-" * 70 + "\n"
            for cuenta, valor in impuestos:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
            income_text += "\n"

        income_text += "UTILIDAD NETA\n"
        income_text += "-" * 70 + "\n"
        if utilidad:
            for cuenta, valor in utilidad:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            income_text += "No hay datos de utilidad neta disponibles\n"

        income_text += "\n"

        if otros:
            income_text += "OTRAS CUENTAS\n"
            income_text += "-" * 70 + "\n"
            for cuenta, valor in otros:
                income_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
            income_text += "\n"

        if total_revenue:
            income_text += "=" * 70 + "\n"
            income_text += "MÁRGENES Y RATIOS\n"
            income_text += "-" * 70 + "\n"

            if gross_profit:
                try:
                    margen_bruto = (float(gross_profit) / float(total_revenue)) * 100
                    income_text += f"Margen Bruto: {margen_bruto:.2f}%\n"
                except:
                    pass

            if operating_income:
                try:
                    margen_operativo = (float(operating_income) / float(total_revenue)) * 100
                    income_text += f"Margen Operativo: {margen_operativo:.2f}%\n"
                except:
                    pass

            net_income = ultimo_valor.get('Net Income') or ultimo_valor.get('Net Income Common Stockholders')
            if net_income:
                try:
                    margen_neto = (float(net_income) / float(total_revenue)) * 100
                    income_text += f"Margen Neto: {margen_neto:.2f}%\n"
                except:
                    pass

        income_text += "\n" + "=" * 70 + "\n"
        income_text += f"\nNota: Los valores están en la moneda reportada por la empresa.\n"
        income_text += f"Fecha de obtención: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return income_text
    except Exception as e:
        return f"❌ Error al obtener el Income Statement:\n{str(e)}\n\nPor favor, verifica que el ticker sea correcto y que Yahoo Finance tenga datos disponibles."


def obtener_cash_flow_text(ticker_str: str) -> str:
    try:
        ticker = yf.Ticker(ticker_str)
        quarterly_cashflow = ticker.quarterly_cashflow

        if quarterly_cashflow is None or quarterly_cashflow.empty:
            return "⚠️  No se pudieron obtener datos del Cash Flow Statement trimestral.\n\n" \
                   "Posibles razones:\n" \
                   "- El ticker no existe o no está disponible en Yahoo Finance\n" \
                   "- La empresa no reporta estados financieros trimestrales\n" \
                   "- Problemas de conexión con Yahoo Finance"

        ultimo_trimestre = quarterly_cashflow.columns[0]
        if hasattr(ultimo_trimestre, 'strftime'):
            fecha_str = ultimo_trimestre.strftime('%Y-%m-%d')
        else:
            fecha_str = str(ultimo_trimestre)

        cashflow_text = f"=== CASH FLOW STATEMENT - ÚLTIMO TRIMESTRE ===\n\n"
        cashflow_text += f"Fecha del reporte: {fecha_str}\n"
        cashflow_text += f"Ticker: {ticker_str}\n\n"
        cashflow_text += "=" * 70 + "\n\n"

        def formatear_valor(valor):
            if pd.isna(valor) or valor is None:
                return "N/A"
            try:
                valor_float = float(valor)
                if abs(valor_float) >= 1e9:
                    return f"${valor_float/1e9:.2f}B"
                elif abs(valor_float) >= 1e6:
                    return f"${valor_float/1e6:.2f}M"
                elif abs(valor_float) >= 1e3:
                    return f"${valor_float/1e3:.2f}K"
                else:
                    return f"${valor_float:,.2f}"
            except:
                return str(valor)

        ultimo_valor = quarterly_cashflow[ultimo_trimestre]

        flujo_operativo = []
        flujo_inversion = []
        flujo_financiamiento = []
        otros = []

        cuentas_operativo = [
            'Net Income', 'Net Income From Continuing Ops', 'Net Income Common Stockholders',
            'Depreciation', 'Depreciation And Amortization', 'Amortization',
            'Change To Netincome', 'Change To Account Receivables', 'Change To Liabilities',
            'Change To Inventory', 'Change To Operating Activities', 'Total Cash From Operating Activities',
            'Operating Cash Flow', 'Cash From Operating Activities', 'Other Cashflows From Investing Activities',
            'Change In Cash', 'Change In Cash And Cash Equivalents'
        ]

        cuentas_inversion = [
            'Capital Expenditures', 'Capital Expenditure', 'Investments', 'Other Cashflows From Investing Activities',
            'Total Cashflows From Investing Activities', 'Cash From Investing Activities',
            'Purchase Of Fixed Assets', 'Sale Of Fixed Assets', 'Purchase Of Investments',
            'Sale Of Investments', 'Other Investing Cash Flow Items'
        ]

        cuentas_financiamiento = [
            'Dividends Paid', 'Common Stock Issued', 'Common Stock Repurchased', 'Repurchase Of Stock',
            'Sale Of Stock', 'Net Borrowings', 'Cash From Financing Activities',
            'Total Cash From Financing Activities', 'Total Cashflows From Financing Activities',
            'Issuance Of Debt', 'Repayment Of Debt', 'Other Financing Cash Flow Items'
        ]

        for cuenta in quarterly_cashflow.index:
            cuenta_str = str(cuenta)
            valor = ultimo_valor.get(cuenta)

            if any(op in cuenta_str for op in cuentas_operativo):
                flujo_operativo.append((cuenta_str, valor))
            elif any(inv in cuenta_str for inv in cuentas_inversion):
                flujo_inversion.append((cuenta_str, valor))
            elif any(fin in cuenta_str for fin in cuentas_financiamiento):
                flujo_financiamiento.append((cuenta_str, valor))
            else:
                otros.append((cuenta_str, valor))

        cashflow_text += "FLUJO DE EFECTIVO DE OPERACIONES\n"
        cashflow_text += "-" * 70 + "\n"
        if flujo_operativo:
            for cuenta, valor in flujo_operativo:
                cashflow_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            cashflow_text += "No hay datos de flujo de efectivo operativo disponibles\n"

        cashflow_text += "\n"

        total_operativo = ultimo_valor.get('Total Cash From Operating Activities') or \
                         ultimo_valor.get('Operating Cash Flow') or \
                         ultimo_valor.get('Cash From Operating Activities')

        if total_operativo:
            cashflow_text += f"{'Total Flujo Operativo':.<50} {formatear_valor(total_operativo):>15}\n"
            cashflow_text += "\n"

        cashflow_text += "FLUJO DE EFECTIVO DE INVERSIÓN\n"
        cashflow_text += "-" * 70 + "\n"
        if flujo_inversion:
            for cuenta, valor in flujo_inversion:
                cashflow_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            cashflow_text += "No hay datos de flujo de efectivo de inversión disponibles\n"

        cashflow_text += "\n"

        total_inversion = ultimo_valor.get('Total Cashflows From Investing Activities') or \
                         ultimo_valor.get('Cash From Investing Activities')

        if total_inversion:
            cashflow_text += f"{'Total Flujo de Inversión':.<50} {formatear_valor(total_inversion):>15}\n"
            cashflow_text += "\n"

        cashflow_text += "FLUJO DE EFECTIVO DE FINANCIAMIENTO\n"
        cashflow_text += "-" * 70 + "\n"
        if flujo_financiamiento:
            for cuenta, valor in flujo_financiamiento:
                cashflow_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
        else:
            cashflow_text += "No hay datos de flujo de efectivo de financiamiento disponibles\n"

        cashflow_text += "\n"

        total_financiamiento = ultimo_valor.get('Total Cash From Financing Activities') or \
                              ultimo_valor.get('Total Cashflows From Financing Activities') or \
                              ultimo_valor.get('Cash From Financing Activities')

        if total_financiamiento:
            cashflow_text += f"{'Total Flujo de Financiamiento':.<50} {formatear_valor(total_financiamiento):>15}\n"
            cashflow_text += "\n"

        if otros:
            cashflow_text += "OTRAS CUENTAS\n"
            cashflow_text += "-" * 70 + "\n"
            for cuenta, valor in otros:
                cashflow_text += f"{cuenta:.<50} {formatear_valor(valor):>15}\n"
            cashflow_text += "\n"

        cambio_efectivo = ultimo_valor.get('Change In Cash') or \
                         ultimo_valor.get('Change In Cash And Cash Equivalents')

        if cambio_efectivo is None and (total_operativo or total_inversion or total_financiamiento):
            try:
                cambio_efectivo = (float(total_operativo or 0) +
                                  float(total_inversion or 0) +
                                  float(total_financiamiento or 0))
            except:
                pass

        if cambio_efectivo is not None:
            cashflow_text += "=" * 70 + "\n"
            cashflow_text += "RESUMEN\n"
            cashflow_text += "-" * 70 + "\n"
            if total_operativo:
                cashflow_text += f"Flujo Operativo:        {formatear_valor(total_operativo)}\n"
            if total_inversion:
                cashflow_text += f"Flujo de Inversión:     {formatear_valor(total_inversion)}\n"
            if total_financiamiento:
                cashflow_text += f"Flujo de Financiamiento: {formatear_valor(total_financiamiento)}\n"
            cashflow_text += f"Cambio Neto en Efectivo: {formatear_valor(cambio_efectivo)}\n"

        net_income = ultimo_valor.get('Net Income') or ultimo_valor.get('Net Income Common Stockholders')
        if net_income and total_operativo:
            try:
                capex = ultimo_valor.get('Capital Expenditures') or ultimo_valor.get('Capital Expenditure')
                if capex:
                    fcf = float(total_operativo) - float(capex)
                    cashflow_text += "\n" + "=" * 70 + "\n"
                    cashflow_text += "RATIOS Y MÉTRICAS\n"
                    cashflow_text += "-" * 70 + "\n"
                    cashflow_text += f"Free Cash Flow (FCF): {formatear_valor(fcf)}\n"
                    cashflow_text += f"  (Operating CF - CapEx)\n"

                if net_income and float(net_income) != 0:
                    conversion_ratio = (float(total_operativo) / float(net_income)) * 100
                    cashflow_text += f"Cash Flow Conversion: {conversion_ratio:.2f}%\n"
                    cashflow_text += f"  (Operating CF / Net Income)\n"
            except:
                pass

        cashflow_text += "\n" + "=" * 70 + "\n"
        cashflow_text += f"\nNota: Los valores están en la moneda reportada por la empresa.\n"
        cashflow_text += f"Fecha de obtención: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        return cashflow_text
    except Exception as e:
        return f"❌ Error al obtener el Cash Flow Statement:\n{str(e)}\n\nPor favor, verifica que el ticker sea correcto y que Yahoo Finance tenga datos disponibles."

class AplicacionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Estimador de Valor Justo de Acciones")
        self.root.geometry("1400x900")
        self.root.configure(bg='#f0f0f0')
        
        # Variables
        self.ticker_var = tk.StringVar(value="AAPL")
        self.tasa_retorno_var = tk.StringVar(value="0.10")
        self.tasa_crecimiento_var = tk.StringVar(value="0.03")
        self.datos_actuales = None
        self.ratios_data = None
        self.figuras_ratios = None
        
        # Diccionario de bolsas/países y sus tickers
        self.bolsas_tickers = {
            # Para Yahoo: NYSE y NASDAQ no llevan sufijo
            "NYSE (Estados Unidos)": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA",
                "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS",
                "BAC", "XOM", "CVX", "ABBV"
            ],
            "NASDAQ (Estados Unidos)": [
                "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA",
                "AMD", "INTC", "NFLX", "CMCSA", "ADBE", "PYPL", "COST",
                "AVGO", "QCOM", "TXN", "CHTR", "AMGN", "SBUX"
            ],

            # Colombia: todas con sufijo .CL en Yahoo Finance
            # Ejemplos: ECOPETROL.CL, GEB.CL, NUTRESA.CL, EXITO.CL, CEMARGOS.CL, GRUPOSURA.CL, BCOLOMBIA.CL, GRUPOAVAL.CL, PFBCOLOM.CL :contentReference[oaicite:1]{index=1}
            "Colombia (BVC)": [
                "ECOPETROL.CL",   # Ecopetrol
                "BCOLOMBIA.CL",   # Bancolombia
                "GRUPOSURA.CL",   # Grupo SURA
                "NUTRESA.CL",     # Grupo Nutresa
                "EXITO.CL",       # Almacenes Éxito
                "CEMARGOS.CL",    # Cementos Argos
                "GEB.CL",         # Grupo Energía Bogotá
                "ISA.CL",         # Interconexión Eléctrica (ISA)
                "GRUPOAVAL.CL",   # Grupo Aval
                "PFBCOLOM.CL",    # Pref. Bancolombia
                "BVC.CL",          # Bolsa de Valores de Colombia
                "BVC.CL"  
            ],

            # México: sufijo .MX
            "México (BMV)": [
                "AMXL.MX", "WALMEX.MX", "GFNORTEO.MX", "CEMEXCPO.MX",
                "FEMSAUBD.MX", "ASURB.MX", "GMEXICOB.MX", "KIMBERA.MX",
                "ALFAA.MX", "BIMBOA.MX"
            ],

            # Brasil: sufijo .SA (B3)
            "Brasil (B3)": [
                "PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA", "ABEV3.SA",
                "WEGE3.SA", "RENT3.SA", "MGLU3.SA", "SUZB3.SA", "RADL3.SA"
            ],

            # Argentina: sufijo .BA (BYMA)
            "Argentina (BYMA)": [
                "GGAL.BA", "PAMP.BA", "TXAR.BA", "MIRG.BA", "BBAR.BA",
                "BMA.BA", "LOMA.BA", "TGSU2.BA", "SUPV.BA", "CECO2.BA"
            ],

            # Chile: sufijo .SN (Bolsa de Santiago)
            "Chile (Santiago)": [
                "FALABELLA.SN", "ENELCHILE.SN", "COPEC.SN", "CMPC.SN",
                "SMU.SN", "LTM.SN", "PARAUCO.SN", "BSANTANDER.SN",
                "BCI.SN",  # Banco de Crédito e Inversiones :contentReference[oaicite:2]{index=2}
                # Ojo: ITAUSA es brasileña; en Yahoo es ITSA4.SA, no ITAUSA.SN. La dejo fuera aquí.
            ],

            # España: sufijo .MC (BME / Bolsa de Madrid) :contentReference[oaicite:3]{index=3}
            "España (BME)": [
                "SAN.MC", "BBVA.MC", "IBE.MC", "REP.MC", "TEF.MC",
                "ITX.MC", "CABK.MC", "ENG.MC", "FER.MC", "GRF.MC"
            ],

            # Reino Unido: sufijo .L (LSE) :contentReference[oaicite:4]{index=4}
            "Reino Unido (LSE)": [
                "BP.L", "GSK.L", "RIO.L", "BATS.L", "HSBA.L",
                "DGE.L", "AZN.L", "ULVR.L", "BT-A.L", "VOD.L"
            ],

            # Alemania: sufijo .DE (XETRA) :contentReference[oaicite:5]{index=5}
            "Alemania (XETR)": [
                "SAP.DE", "SIE.DE", "ALV.DE", "MUV2.DE", "BAYN.DE",
                "BMW.DE", "VOW3.DE", "DBK.DE", "DTE.DE", "IFX.DE"
            ],

            # Francia: sufijo .PA (Euronext Paris)
            "Francia (EPA)": [
                "TTE.PA", "SAN.PA", "BNP.PA", "OR.PA", "MC.PA",
                "AIR.PA", "EL.PA", "VIE.PA", "DG.PA", "ATO.PA"
            ],

            # Japón: sufijo .T (Tokyo Stock Exchange)
            "Japón (TSE)": [
                "7203.T", "6758.T", "9984.T", "6861.T", "6098.T",
                "8035.T", "8058.T", "8306.T", "8411.T", "9434.T"
            ]
        }

        
        self.crear_interfaz()
    
    def crear_interfaz(self):
        # Frame superior para entrada de datos
        frame_entrada = tk.Frame(self.root, bg='#ffffff', relief=tk.RAISED, bd=2)
        frame_entrada.pack(fill=tk.X, padx=10, pady=10)
        
        # Título
        titulo = tk.Label(frame_entrada, text="Estimador de Valor Justo de Acciones", 
                         font=('Arial', 16, 'bold'), bg='#ffffff')
        titulo.pack(pady=10)
        
        # Frame para campos de entrada
        frame_campos = tk.Frame(frame_entrada, bg='#ffffff')
        frame_campos.pack(pady=10, padx=20)
        
        # Ticker - Botón para abrir modal
        tk.Label(frame_campos, text="Ticker:", font=('Arial', 10), bg='#ffffff').grid(row=0, column=0, padx=5, pady=5, sticky='e')
        frame_ticker = tk.Frame(frame_campos, bg='#ffffff')
        frame_ticker.grid(row=0, column=1, padx=5, pady=5)
        entry_ticker = tk.Entry(frame_ticker, textvariable=self.ticker_var, font=('Arial', 10), width=15)
        entry_ticker.pack(side=tk.LEFT, padx=(0, 5))
        btn_seleccionar_ticker = tk.Button(frame_ticker, text="Seleccionar Ticker", command=self.abrir_modal_ticker,
                                          bg='#2196F3', fg='white', font=('Arial', 9), 
                                          padx=10, pady=3, cursor='hand2')
        btn_seleccionar_ticker.pack(side=tk.LEFT)
        
        # Tasa de retorno
        tk.Label(frame_campos, text="Tasa de retorno (r):", font=('Arial', 10), bg='#ffffff').grid(row=0, column=2, padx=5, pady=5, sticky='e')
        entry_r = tk.Entry(frame_campos, textvariable=self.tasa_retorno_var, font=('Arial', 10), width=10)
        entry_r.grid(row=0, column=3, padx=5, pady=5)
        
        # Tasa de crecimiento
        tk.Label(frame_campos, text="Tasa crecimiento (g):", font=('Arial', 10), bg='#ffffff').grid(row=0, column=4, padx=5, pady=5, sticky='e')
        entry_g = tk.Entry(frame_campos, textvariable=self.tasa_crecimiento_var, font=('Arial', 10), width=10)
        entry_g.grid(row=0, column=5, padx=5, pady=5)
        
        # Botón de análisis
        btn_analizar = tk.Button(frame_campos, text="Analizar Acción", command=self.analizar_accion,
                                bg='#4CAF50', fg='white', font=('Arial', 11, 'bold'), 
                                padx=20, pady=5, cursor='hand2')
        btn_analizar.grid(row=0, column=6, padx=10, pady=5)
        
        # Frame principal con paned window para dividir datos y gráficas
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Frame izquierdo para datos y resultados
        frame_datos = tk.Frame(paned, bg='#ffffff', relief=tk.SUNKEN, bd=2)
        paned.add(frame_datos, width=500, minsize=400)
        
        # Notebook para tabs de datos
        notebook = ttk.Notebook(frame_datos)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab de información básica
        tab_info = tk.Frame(notebook, bg='#ffffff')
        notebook.add(tab_info, text="Información Básica")
        self.text_info = scrolledtext.ScrolledText(tab_info, wrap=tk.WORD, font=('Consolas', 9),
                                                   bg='#f9f9f9', fg='#333333')
        self.text_info.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab de Balance Sheet
        tab_balance = tk.Frame(notebook, bg='#ffffff')
        notebook.add(tab_balance, text="Balance Sheet")
        self.text_balance = scrolledtext.ScrolledText(tab_balance, wrap=tk.WORD, font=('Consolas', 9),
                                                      bg='#f9f9f9', fg='#333333')
        self.text_balance.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab de Income Statement
        tab_income = tk.Frame(notebook, bg='#ffffff')
        notebook.add(tab_income, text="Income Statement")
        self.text_income = scrolledtext.ScrolledText(tab_income, wrap=tk.WORD, font=('Consolas', 9),
                                                     bg='#f9f9f9', fg='#333333')
        self.text_income.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab de Cash Flow
        tab_cashflow = tk.Frame(notebook, bg='#ffffff')
        notebook.add(tab_cashflow, text="Cash Flow")
        self.text_cashflow = scrolledtext.ScrolledText(tab_cashflow, wrap=tk.WORD, font=('Consolas', 9),
                                                       bg='#f9f9f9', fg='#333333')
        self.text_cashflow.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab de resultados de valoración
        tab_valoracion = tk.Frame(notebook, bg='#ffffff')
        notebook.add(tab_valoracion, text="Valoración")
        self.text_valoracion = scrolledtext.ScrolledText(tab_valoracion, wrap=tk.WORD, font=('Consolas', 9),
                                                         bg='#f9f9f9', fg='#333333')
        self.text_valoracion.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Frame derecho para gráficas
        frame_graficas = tk.Frame(paned, bg='#ffffff', relief=tk.SUNKEN, bd=2)
        paned.add(frame_graficas, width=900, minsize=600)
        
        # Notebook para gráficas
        notebook_graficas = ttk.Notebook(frame_graficas)
        notebook_graficas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tabs_graficas = {}
        self.canvas_graficas = {}
        
        # Crear tabs para cada ratio
        ratios_nombres = {
            'Net Margin': 'Net Margin (%)',
            'PS': 'PS (Price to Sales)',
            'PER': 'PER (P/E)',
            'PCF': 'PCF (P/CF)',
            'PBV': 'PBV (P/B)'
        }
        
        for ratio_key, ratio_nombre in ratios_nombres.items():
            tab = tk.Frame(notebook_graficas, bg='#ffffff')
            notebook_graficas.add(tab, text=ratio_nombre)
            self.tabs_graficas[ratio_key] = tab
    
    def analizar_accion(self):
        """Ejecuta el análisis en un hilo separado para no bloquear la GUI"""
        ticker_str = self.ticker_var.get().strip().upper()
        if not ticker_str:
            messagebox.showerror("Error", "Por favor ingresa un ticker válido")
            return
        
        try:
            r = float(self.tasa_retorno_var.get())
            g = float(self.tasa_crecimiento_var.get())
        except ValueError:
            messagebox.showerror("Error", "Las tasas deben ser números válidos")
            return
        
        # Limpiar resultados anteriores
        self.text_info.delete(1.0, tk.END)
        self.text_valoracion.delete(1.0, tk.END)
        self.text_info.insert(tk.END, "Descargando datos...\nPor favor espera...\n")
        self.root.update()
        
        # Ejecutar en hilo separado
        thread = threading.Thread(target=self.ejecutar_analisis, args=(ticker_str, r, g))
        thread.daemon = True
        thread.start()
    
    def ejecutar_analisis(self, ticker_str, r, g):
        """Ejecuta el análisis completo"""
        try:
            # Obtener datos básicos
            datos = obtener_datos(ticker_str)
            self.datos_actuales = datos
            
            # Mostrar información básica
            info_text = f"=== INFORMACIÓN BÁSICA ===\n\n"
            info_text += f"Ticker:          {datos['ticker']}\n"
            info_text += f"Nombre corto:    {datos['short_name']}\n"
            info_text += f"Sector:          {datos['sector']}\n"
            info_text += f"Precio actual:   ${datos['precio_actual']:.2f}\n" if datos['precio_actual'] else f"Precio actual:   N/A\n"
            info_text += f"EPS trailing:    {datos['trailing_eps']:.2f}\n" if datos['trailing_eps'] else f"EPS trailing:    N/A\n"
            info_text += f"EPS forward:     {datos['forward_eps']:.2f}\n" if datos['forward_eps'] else f"EPS forward:     N/A\n"
            info_text += f"Trailing P/E:    {datos['trailing_pe']:.2f}\n" if datos['trailing_pe'] else f"Trailing P/E:    N/A\n"
            info_text += f"Forward P/E:     {datos['forward_pe']:.2f}\n" if datos['forward_pe'] else f"Forward P/E:     N/A\n"
            info_text += f"Dividendo anual: ${datos['dividendo_anual']:.2f}\n" if datos['dividendo_anual'] else f"Dividendo anual: N/A\n"
            info_text += f"Div. yield:      {datos['dividend_yield']*100:.2f}%\n" if datos['dividend_yield'] else f"Div. yield:      N/A\n"
            info_text += f"5Y avg yield:    {datos['five_year_avg_div_yield']*100:.2f}%\n" if datos['five_year_avg_div_yield'] else f"5Y avg yield:    N/A\n"
            info_text += f"Valor en libros: ${datos['book_value']:.2f}\n" if datos['book_value'] else f"Valor en libros: N/A\n"
            
            self.text_info.delete(1.0, tk.END)
            self.text_info.insert(tk.END, info_text)
            
            # Obtener y mostrar Balance Sheet del último trimestre
            self.text_balance.delete(1.0, tk.END)
            self.text_balance.insert(tk.END, "Obteniendo Balance Sheet...\n")
            self.root.update()
            
            balance_text = self.obtener_balance_sheet(ticker_str)
            self.text_balance.delete(1.0, tk.END)
            self.text_balance.insert(tk.END, balance_text)
            
            # Obtener y mostrar Income Statement del último trimestre
            self.text_income.delete(1.0, tk.END)
            self.text_income.insert(tk.END, "Obteniendo Income Statement...\n")
            self.root.update()
            
            income_text = self.obtener_income_statement(ticker_str)
            self.text_income.delete(1.0, tk.END)
            self.text_income.insert(tk.END, income_text)
            
            # Obtener y mostrar Cash Flow del último trimestre
            self.text_cashflow.delete(1.0, tk.END)
            self.text_cashflow.insert(tk.END, "Obteniendo Cash Flow...\n")
            self.root.update()
            
            cashflow_text = self.obtener_cash_flow(ticker_str)
            self.text_cashflow.delete(1.0, tk.END)
            self.text_cashflow.insert(tk.END, cashflow_text)
            
            # Calcular valoraciones
            pe_justo = estimar_pe_justo(datos)
            eps_usado = datos["forward_eps"] or datos["trailing_eps"]
            fv_pe = valor_justo_por_pe(eps_usado, pe_justo)
            fv_div = valor_justo_dividendos(datos["dividendo_anual"], r, g)
            
            fv_book = None
            if datos["book_value"]:
                pb_justo = 1.2
                fv_book = datos["book_value"] * pb_justo
            
            fair_values = [v for v in [fv_pe, fv_div, fv_book] if v]
            fv_promedio = sum(fair_values) / len(fair_values) if fair_values else None
            
            # Mostrar resultados de valoración
            valoracion_text = "===== RESULTADOS DE VALORACIÓN =====\n\n"
            valoracion_text += f"Precio actual:                           ${datos['precio_actual']:.2f}\n" if datos['precio_actual'] else f"Precio actual:                           N/A\n"
            valoracion_text += f"PE 'justo' estimado:                     {pe_justo:.2f}\n"
            valoracion_text += f"Valor justo por P/E (EPS usado={eps_usado:.2f}): ${fv_pe:.2f}\n" if fv_pe else f"Valor justo por P/E: No disponible\n"
            valoracion_text += f"Valor justo por Dividendos (r={r}, g={g}):    ${fv_div:.2f}\n" if fv_div else f"Valor justo por Dividendos: No disponible\n"
            valoracion_text += f"Valor justo por valor en libros (P/B=1.2):   ${fv_book:.2f}\n" if fv_book else f"Valor justo por valor en libros: No disponible\n"
            valoracion_text += "-----------------------------------------\n"
            valoracion_text += f"Valor justo promedio: ${fv_promedio:.2f}\n" if fv_promedio else f"Valor justo promedio: No disponible\n"
            
            if fv_promedio and datos["precio_actual"]:
                upside = (fv_promedio / datos["precio_actual"] - 1) * 100
                valoracion_text += f"\nUpside/Downside estimado: {upside:+.2f}%\n"
                if upside > 0:
                    valoracion_text += f"La acción está {upside:.2f}% por debajo de su valor justo estimado.\n"
                else:
                    valoracion_text += f"La acción está {abs(upside):.2f}% por encima de su valor justo estimado.\n"
            
            self.text_valoracion.delete(1.0, tk.END)
            self.text_valoracion.insert(tk.END, valoracion_text)
            
            # Obtener y mostrar gráficas de ratios históricos
            self.text_info.insert(tk.END, "\n\nObteniendo ratios históricos...\n")
            self.root.update()
            
            resultado = graficar_ratios_historicos(ticker_str, return_data=True)
            if resultado:
                self.figuras_ratios, self.ratios_data = resultado
                self.mostrar_graficas()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al analizar la acción: {str(e)}")
            self.text_info.delete(1.0, tk.END)
            self.text_info.insert(tk.END, f"Error: {str(e)}")
    
    def obtener_balance_sheet(self, ticker_str: str) -> str:
        """Wrapper para mantener compatibilidad con la GUI original."""
        return obtener_balance_sheet_text(ticker_str)
    
    def obtener_income_statement(self, ticker_str: str) -> str:
        return obtener_income_statement_text(ticker_str)
    
    def obtener_cash_flow(self, ticker_str: str) -> str:
        return obtener_cash_flow_text(ticker_str)
    
    def mostrar_graficas(self):
        """Muestra las gráficas en los tabs correspondientes"""
        if not self.figuras_ratios:
            return
        
        for ratio_key, tab in self.tabs_graficas.items():
            # Limpiar tab anterior
            for widget in tab.winfo_children():
                widget.destroy()
            
            if ratio_key in self.figuras_ratios:
                datos_ratio = self.figuras_ratios[ratio_key]
                trimestres = datos_ratio['trimestres']
                valores = datos_ratio['valores']
                nombre = datos_ratio['nombre']
                
                # Crear nueva figura para el canvas de Tkinter
                fig_tk = Figure(figsize=(10, 5), dpi=100)
                ax = fig_tk.add_subplot(111)
                
                # Graficar datos
                ax.plot(range(len(trimestres)), valores, marker='o', linewidth=2, markersize=6, color='#2E86AB')
                ax.set_title(f'{nombre} - Últimos 5 Años (Trimestral)\n{self.ticker_var.get()}', 
                            fontsize=12, fontweight='bold')
                ax.set_xlabel('Trimestre', fontsize=10)
                ax.set_ylabel(nombre, fontsize=10)
                ax.grid(True, alpha=0.3)
                
                # Configurar etiquetas del eje X
                num_trimestres = len(trimestres)
                if num_trimestres > 16:
                    indices_mostrar = list(range(0, num_trimestres, 2))
                    labels_mostrar = [trimestres[i] for i in indices_mostrar]
                    if (num_trimestres - 1) not in indices_mostrar:
                        indices_mostrar.append(num_trimestres - 1)
                        labels_mostrar.append(trimestres[-1])
                    ax.set_xticks(indices_mostrar)
                    ax.set_xticklabels(labels_mostrar, rotation=45, ha='right', fontsize=8)
                else:
                    ax.set_xticks(range(num_trimestres))
                    ax.set_xticklabels(trimestres, rotation=45, ha='right', fontsize=8)
                
                # Agregar valores en algunos puntos
                step = max(1, len(trimestres) // 10)
                for i in range(0, len(trimestres), step):
                    ax.annotate(f'{valores[i]:.2f}', 
                               (i, valores[i]), 
                               textcoords="offset points", 
                               xytext=(0,10), 
                               ha='center', 
                               fontsize=7)
                
                fig_tk.tight_layout()
                
                # Crear canvas para Tkinter
                canvas = FigureCanvasTkAgg(fig_tk, tab)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
                
                # Agregar toolbar de navegación
                toolbar = NavigationToolbar2Tk(canvas, tab)
                toolbar.update()
            else:
                # Mostrar mensaje si no hay datos
                label = tk.Label(tab, text=f"No hay datos disponibles para {ratio_key}", 
                               font=('Arial', 12), bg='#ffffff', fg='#666666')
                label.pack(expand=True)
    
    def abrir_modal_ticker(self):
        """Abre el modal para seleccionar ticker por bolsa/país"""
        modal = tk.Toplevel(self.root)
        modal.title("Seleccionar Ticker")
        modal.geometry("500x300")
        modal.configure(bg='#f0f0f0')
        modal.transient(self.root)
        modal.grab_set()
        
        # Centrar el modal
        modal.update_idletasks()
        x = (modal.winfo_screenwidth() // 2) - (500 // 2)
        y = (modal.winfo_screenheight() // 2) - (300 // 2)
        modal.geometry(f"500x300+{x}+{y}")
        
        # Frame principal del modal
        frame_modal = tk.Frame(modal, bg='#f0f0f0')
        frame_modal.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Título
        titulo_modal = tk.Label(frame_modal, text="Seleccionar Ticker por Bolsa/País", 
                               font=('Arial', 14, 'bold'), bg='#f0f0f0')
        titulo_modal.pack(pady=(0, 20))
        
        # Frame para las listas desplegables
        frame_listas = tk.Frame(frame_modal, bg='#f0f0f0')
        frame_listas.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Lista desplegable de bolsa/país
        tk.Label(frame_listas, text="Bolsa/País:", font=('Arial', 10), bg='#f0f0f0').pack(anchor='w', pady=(0, 5))
        bolsa_var = tk.StringVar()
        combo_bolsa = ttk.Combobox(frame_listas, textvariable=bolsa_var, 
                                   values=list(self.bolsas_tickers.keys()),
                                   state='readonly', font=('Arial', 10), width=40)
        combo_bolsa.pack(fill=tk.X, pady=(0, 15))
        combo_bolsa.set("")  # Inicialmente vacío
        
        # Lista desplegable de tickers
        tk.Label(frame_listas, text="Ticker:", font=('Arial', 10), bg='#f0f0f0').pack(anchor='w', pady=(0, 5))
        ticker_var_modal = tk.StringVar()
        combo_ticker = ttk.Combobox(frame_listas, textvariable=ticker_var_modal,
                                    state='readonly', font=('Arial', 10), width=40)
        combo_ticker.pack(fill=tk.X, pady=(0, 15))
        combo_ticker['values'] = []  # Inicialmente vacío
        
        # Función para actualizar la lista de tickers cuando se selecciona una bolsa
        def actualizar_tickers(event=None):
            bolsa_seleccionada = bolsa_var.get()
            if bolsa_seleccionada and bolsa_seleccionada in self.bolsas_tickers:
                tickers = self.bolsas_tickers[bolsa_seleccionada]
                combo_ticker['values'] = tickers
                combo_ticker.set("")  # Limpiar selección anterior
                # Habilitar o deshabilitar botón de seleccionar
                actualizar_boton_seleccionar()
            else:
                combo_ticker['values'] = []
                combo_ticker.set("")
                actualizar_boton_seleccionar()
        
        combo_bolsa.bind('<<ComboboxSelected>>', actualizar_tickers)
        
        # Función para actualizar estado del botón de seleccionar
        def actualizar_boton_seleccionar():
            if bolsa_var.get() and ticker_var_modal.get():
                btn_seleccionar.config(state=tk.NORMAL)
            else:
                btn_seleccionar.config(state=tk.DISABLED)
        
        combo_ticker.bind('<<ComboboxSelected>>', lambda e: actualizar_boton_seleccionar())
        
        # Frame para botones
        frame_botones = tk.Frame(frame_modal, bg='#f0f0f0')
        frame_botones.pack(fill=tk.X, pady=(10, 0))
        
        # Botón de seleccionar (inicialmente deshabilitado)
        btn_seleccionar = tk.Button(frame_botones, text="Seleccionar", 
                                   command=lambda: self.seleccionar_ticker(modal, ticker_var_modal.get()),
                                   bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'),
                                   padx=20, pady=5, cursor='hand2', state=tk.DISABLED)
        btn_seleccionar.pack(side=tk.LEFT, padx=(0, 10))
        
        # Botón de cancelar
        btn_cancelar = tk.Button(frame_botones, text="Cancelar", 
                                command=modal.destroy,
                                bg='#f44336', fg='white', font=('Arial', 10),
                                padx=20, pady=5, cursor='hand2')
        btn_cancelar.pack(side=tk.LEFT)
    
    def seleccionar_ticker(self, modal, ticker_seleccionado):
        """Cierra el modal y actualiza el ticker en la pantalla principal"""
        if ticker_seleccionado:
            self.ticker_var.set(ticker_seleccionado)
            modal.destroy()

def main():
    print("=== Estimador de valor justo por acción (simple) ===")
    ticker_str = input("Ingresa el ticker de la acción (ej: AAPL, MSFT, NKE): ").strip().upper()

    print("\nDescargando datos desde Yahoo Finance...\n")
    datos = obtener_datos(ticker_str)

    # Mostrar datos base
    print(f"Ticker:          {datos['ticker']}")
    print(f"Nombre corto:    {datos['short_name']}")
    print(f"Sector:          {datos['sector']}")
    print(f"Precio actual:   {datos['precio_actual']}")
    print(f"EPS trailing:    {datos['trailing_eps']}")
    print(f"EPS forward:     {datos['forward_eps']}")
    print(f"Trailing P/E:    {datos['trailing_pe']}")
    print(f"Forward P/E:     {datos['forward_pe']}")
    print(f"Dividendo anual: {datos['dividendo_anual']}")
    print(f"Div. yield:      {datos['dividend_yield']}")
    print(f"5Y avg yield:    {datos['five_year_avg_div_yield']}")
    print(f"Valor en libros: {datos['book_value']}")
    print("\n-----------------------------------------\n")

    # 1) Valor justo por P/E
    pe_justo = estimar_pe_justo(datos)
    # Preferimos usar EPS forward, si no, trailing
    eps_usado = datos["forward_eps"] or datos["trailing_eps"]

    fv_pe = valor_justo_por_pe(eps_usado, pe_justo)

    # 2) Valor justo por dividendos (Gordon)
    # Preguntamos al usuario parámetros r y g para que vea el impacto
    # R es lo que tú, como inversor, exiges mínimo que te rinda esa acción anualmente.
    # G es la tasa de crecimiento esperada del dividendo.
    # Ejemplo: si r = 0.10 (10%) y g = 0.03 (3%), entonces el valor justo por dividendos es:
    # fv_div = dividendo_anual * (1 + g) / (r - g)
    # fv_div = dividendo_anual * (1 + 0.03) / (0.10 - 0.03)
    # fv_div = dividendo_anual * 1.03 / 0.07
    # fv_div = dividendo_anual * 14.71
    # Ejemplo: si dividendo_anual = 1 y r = 0.10 (10%) y g = 0.03 (3%), entecopetrol.cl
    # onces el valor justo por dividendos es:
    # fv_div = 1 * (1 + 0.03) / (0.10 - 0.03)
    # fv_div = 1 * 1.03 / 0.07
    # fv_div = 1 * 14.71
   # “Si exijo más retorno (r ↑), el valor justo baja.
   # Si creo que la empresa crecerá más (g ↑), el valor justo sube”.
    try:
        r_input = input("Tasa de retorno requerida r (ej: 0.10 para 10%, Enter para 0.10): ").strip()
        g_input = input("Tasa de crecimiento g estimada del dividendo (ej: 0.03 para 3%, Enter para 0.03): ").strip()

        r = float(r_input) if r_input else 0.10
        g = float(g_input) if g_input else 0.03
    except ValueError:
        print("Entrada inválida, usando valores por defecto r=0.10, g=0.03")
        r, g = 0.10, 0.03

    fv_div = valor_justo_dividendos(datos["dividendo_anual"], r, g)

    # 3) Valor justo por valor en libros (opcional, muy simplificado)
    #    Supuesto: accion tipo “utility/financiera” donde P/B justo ~ 1.2x
    # Ejemplo: si book_value = 10 y pb_justo = 1.2, entonces el valor justo por valor en libros es:
    # fv_book = book_value * pb_justo
    # fv_book = 10 * 1.2
    # fv_book = 12
    fv_book = None
    if datos["book_value"]:
        pb_justo = 1.2   # puedes jugar con esto
        fv_book = datos["book_value"] * pb_justo

    # 4) Valor justo “combinado” (promedio de lo que exista)
    fair_values = [v for v in [fv_pe, fv_div, fv_book] if v]
    fv_promedio = sum(fair_values) / len(fair_values) if fair_values else None

    # Imprimir resultados
    print("\n===== RESULTADOS DE VALORACIÓN =====")
    print(f"Precio actual:                           {datos['precio_actual']}")
    print(f"PE ‘justo’ estimado:                     {pe_justo:.2f}")
    print(f"Valor justo por P/E (EPS usado={eps_usado}): {fv_pe if fv_pe else 'No disponible'}")
    print(f"Valor justo por Dividendos (r={r}, g={g}):    {fv_div if fv_div else 'No disponible'}")
    print(f"Valor justo por valor en libros (P/B=1.2):   {fv_book if fv_book else 'No disponible'}")
    print("-----------------------------------------")
    print(f"Valor justo promedio (si hay varios métodos): {fv_promedio if fv_promedio else 'No disponible'}")
    print("=========================================\n")

    # Pequeño comentario automático
    if fv_promedio and datos["precio_actual"]:
        upside = (fv_promedio / datos["precio_actual"] - 1) * 100
        print(f"Upside/downside estimado vs precio actual: {upside:.2f}%")
    else:
        print("No se puede calcular el upside/downside por falta de datos.")
    
    # Llamar al método para graficar ratios históricos
    print("\n" + "="*50)
    graficar_ratios_historicos(ticker_str)


def graficar_ratios_historicos(ticker_str: str, return_data=False):
    """
    Obtiene los ratios históricos trimestre a trimestre de los últimos 5 años y crea gráficas independientes
    para cada ratio:
    - Net Margin (%)
    - PS (Price to Sales)
    - PER (P/E)
    - PCF (P/CF)
    - PBV (P/B)
    
    Args:
        ticker_str: Símbolo de la acción
        return_data: Si es True, retorna los datos en lugar de guardar gráficas
    """
    print("\n=== Obteniendo ratios históricos trimestrales de los últimos 5 años ===")
    ticker = yf.Ticker(ticker_str)
    
    # Obtener datos históricos de precios (últimos 5 años)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    hist = ticker.history(start=start_date, end=end_date)
    
    # Obtener estados financieros trimestrales
    try:
        quarterly_financials = ticker.quarterly_financials  # Income statement trimestral
        quarterly_balance = ticker.quarterly_balance_sheet
        quarterly_cashflow = ticker.quarterly_cashflow
        info = ticker.info
    except Exception as e:
        print(f"Error al obtener datos financieros trimestrales: {e}")
        return
    
    if quarterly_financials is None or quarterly_financials.empty:
        print("No se pudieron obtener datos financieros trimestrales suficientes.")
        return
    
    # Obtener todos los trimestres disponibles
    # yfinance devuelve las fechas más recientes primero (más reciente a más antiguo)
    todas_fechas = list(quarterly_financials.columns)
    
    # Convertir todas las fechas a datetime para comparación
    fechas_datetime = []
    for fecha in todas_fechas:
        try:
            if isinstance(fecha, pd.Timestamp):
                fecha_dt = fecha.to_pydatetime()
            elif hasattr(fecha, 'year'):
                fecha_dt = fecha
            else:
                fecha_dt = pd.to_datetime(fecha).to_pydatetime()
            fechas_datetime.append((fecha, fecha_dt))
        except Exception as e:
            continue
    
    # Ordenar por fecha (más reciente primero) y tomar los últimos 20 trimestres (5 años)
    fechas_datetime.sort(key=lambda x: x[1], reverse=True)
    fechas_trimestrales = [fecha_orig for fecha_orig, _ in fechas_datetime[:20]]
    
    if not fechas_trimestrales:
        print("No hay suficientes datos trimestrales disponibles.")
        return
    
    print(f"Procesando {len(fechas_trimestrales)} trimestres (últimos 5 años)...")
    
    # Función auxiliar para buscar valores en los estados financieros
    def buscar_valor(df, posibles_nombres, fecha_col):
        """Busca un valor en el DataFrame usando varios nombres posibles"""
        if df is None or df.empty:
            return None
        for nombre in posibles_nombres:
            if nombre in df.index:
                try:
                    valor = df.loc[nombre, fecha_col]
                    if pd.notna(valor) and valor != 0:
                        return float(valor)
                except:
                    continue
        return None
    
    # Función para obtener el trimestre de una fecha
    def obtener_trimestre_label(fecha):
        """Obtiene el label del trimestre en formato YYYY-Q1, YYYY-Q2, etc."""
        if hasattr(fecha, 'year') and hasattr(fecha, 'month'):
            año = fecha.year
            mes = fecha.month
            trimestre = (mes - 1) // 3 + 1
            return f"{año}-Q{trimestre}"
        elif hasattr(fecha, 'strftime'):
            año = int(fecha.strftime('%Y'))
            mes = int(fecha.strftime('%m'))
            trimestre = (mes - 1) // 3 + 1
            return f"{año}-Q{trimestre}"
        else:
            # Intentar extraer de string
            fecha_str = str(fecha)
            if len(fecha_str) >= 7:
                año = int(fecha_str[:4])
                mes = int(fecha_str[5:7])
                trimestre = (mes - 1) // 3 + 1
                return f"{año}-Q{trimestre}"
        return str(fecha)
    
    ratios_data = {}
    
    # Calcular ratios para cada trimestre
    for fecha in fechas_trimestrales:
        try:
            # Obtener valores del estado de resultados trimestral (intentar diferentes nombres)
            revenue = buscar_valor(quarterly_financials, ['Total Revenue', 'Revenue', 'Revenues'], fecha)
            net_income = buscar_valor(quarterly_financials, ['Net Income', 'Net Income Common Stockholders'], fecha)
            
            # Obtener valores del balance trimestral
            total_assets = buscar_valor(quarterly_balance, ['Total Assets', 'Assets'], fecha)
            total_liab = buscar_valor(quarterly_balance, ['Total Liab', 'Total Liabilities', 'Liabilities'], fecha)
            book_value = total_assets - total_liab if (total_assets and total_liab) else None
            
            # Obtener valores del flujo de caja trimestral
            operating_cf = buscar_valor(quarterly_cashflow, ['Total Cash From Operating Activities', 
                                                             'Operating Cash Flow', 
                                                             'Cash From Operating Activities'], fecha)
            
            # Obtener año y mes del trimestre para filtrar precios
            if hasattr(fecha, 'year') and hasattr(fecha, 'month'):
                año = fecha.year
                mes = fecha.month
            elif hasattr(fecha, 'strftime'):
                año = int(fecha.strftime('%Y'))
                mes = int(fecha.strftime('%m'))
            else:
                fecha_str = str(fecha)
                if len(fecha_str) >= 7:
                    año = int(fecha_str[:4])
                    mes = int(fecha_str[5:7])
                else:
                    continue
            
            # Filtrar precios del trimestre correspondiente
            # Calcular rango del trimestre
            mes_inicio = ((mes - 1) // 3) * 3 + 1
            mes_fin = mes_inicio + 2
            
            precios_trimestre = hist[
                (hist.index.year == año) & 
                (hist.index.month >= mes_inicio) & 
                (hist.index.month <= mes_fin)
            ]
            precio_promedio = precios_trimestre['Close'].mean() if not precios_trimestre.empty else None
            
            # Obtener shares outstanding (intentar obtener histórico del balance sheet trimestral)
            shares_outstanding = None
            
            # Intentar obtener desde el balance sheet trimestral histórico
            if quarterly_balance is not None:
                # Buscar diferentes nombres para shares outstanding
                posibles_shares = ['Share Issued', 'Shares Outstanding', 'Common Stock Shares Outstanding']
                for nombre in posibles_shares:
                    if nombre in quarterly_balance.index:
                        try:
                            shares_val = quarterly_balance.loc[nombre, fecha]
                            if pd.notna(shares_val) and shares_val > 0:
                                shares_outstanding = float(shares_val)
                                break
                        except:
                            continue
            
            # Si no se encontró en el balance trimestral, usar el valor actual de info
            if not shares_outstanding:
                shares_outstanding = info.get('sharesOutstanding') if info else None
                if shares_outstanding:
                    shares_outstanding = float(shares_outstanding)
            
            # Si aún no hay, intentar calcular desde market cap
            if not shares_outstanding and precio_promedio:
                try:
                    market_cap = info.get('marketCap', 0)
                    if market_cap and precio_promedio:
                        shares_outstanding = market_cap / precio_promedio
                except:
                    pass
            
            if not shares_outstanding or shares_outstanding <= 0:
                trimestre_label = obtener_trimestre_label(fecha)
                print(f"Advertencia: No se pudo obtener shares outstanding para {trimestre_label}")
                continue
            
            # Calcular ratios
            ratios = {}
            
            # 1. Net Margin (%)
            if net_income and revenue and revenue != 0:
                ratios['Net Margin'] = (net_income / revenue) * 100
            else:
                ratios['Net Margin'] = None
            
            # 2. PS (Price to Sales)
            if precio_promedio and revenue and shares_outstanding:
                market_cap = precio_promedio * shares_outstanding
                if revenue != 0:
                    ratios['PS'] = market_cap / revenue
                else:
                    ratios['PS'] = None
            else:
                ratios['PS'] = None
            
            # 3. PER (P/E)
            if net_income and shares_outstanding and shares_outstanding != 0:
                eps = net_income / shares_outstanding
                if eps != 0 and precio_promedio:
                    ratios['PER'] = precio_promedio / eps
                else:
                    ratios['PER'] = None
            else:
                ratios['PER'] = None
            
            # 4. PCF (P/CF) - Price to Cash Flow
            if precio_promedio and operating_cf and shares_outstanding and shares_outstanding != 0:
                cf_per_share = operating_cf / shares_outstanding
                if cf_per_share != 0:
                    ratios['PCF'] = precio_promedio / cf_per_share
                else:
                    ratios['PCF'] = None
            else:
                ratios['PCF'] = None
            
            # 5. PBV (P/B)
            if precio_promedio and book_value and shares_outstanding and shares_outstanding != 0:
                bv_per_share = book_value / shares_outstanding
                if bv_per_share != 0:
                    ratios['PBV'] = precio_promedio / bv_per_share
                else:
                    ratios['PBV'] = None
            else:
                ratios['PBV'] = None
            
            # Guardar con label del trimestre
            trimestre_label = obtener_trimestre_label(fecha)
            ratios_data[trimestre_label] = ratios
            
        except Exception as e:
            trimestre_label = obtener_trimestre_label(fecha) if 'fecha' in locals() else 'desconocido'
            print(f"Error procesando datos para {trimestre_label}: {e}")
            continue
    
    if not ratios_data:
        print("No se pudieron calcular ratios históricos trimestrales.")
        return
    
    print(f"Ratios calculados para {len(ratios_data)} trimestres.")
    
    # Crear gráficas independientes para cada ratio
    ratios_nombres = {
        'Net Margin': 'Net Margin (%)',
        'PS': 'PS (Price to Sales)',
        'PER': 'PER (P/E)',
        'PCF': 'PCF (P/CF)',
        'PBV': 'PBV (P/B)'
    }
    
    # Ordenar trimestres cronológicamente
    def ordenar_trimestres(trimestre_str):
        """Convierte 'YYYY-QN' a tupla (año, trimestre) para ordenar"""
        try:
            año, q = trimestre_str.split('-Q')
            return (int(año), int(q))
        except:
            return (0, 0)
    
    trimestres_ordenados = sorted(ratios_data.keys(), key=ordenar_trimestres)
    print(f"Trimestres a graficar: {len(trimestres_ordenados)}")
    
    figuras_ratios = {}  # Para almacenar figuras si return_data=True
    
    for ratio_key, ratio_nombre in ratios_nombres.items():
        valores = [ratios_data[trimestre].get(ratio_key) for trimestre in trimestres_ordenados]
        
        # Filtrar valores None
        trimestres_validos = [trimestre for trimestre, val in zip(trimestres_ordenados, valores) if val is not None]
        valores_validos = [val for val in valores if val is not None]
        
        if not valores_validos:
            print(f"No hay datos suficientes para graficar {ratio_nombre}")
            continue
        
        # Crear gráfica
        plt.figure(figsize=(14, 6))
        plt.plot(range(len(trimestres_validos)), valores_validos, marker='o', linewidth=2, markersize=6)
        plt.title(f'{ratio_nombre} - Últimos 5 Años (Trimestral)\n{ticker_str}', fontsize=14, fontweight='bold')
        plt.xlabel('Trimestre', fontsize=12)
        plt.ylabel(ratio_nombre, fontsize=12)
        plt.grid(True, alpha=0.3)
        
        # Configurar etiquetas del eje X
        # Mostrar todos los trimestres, pero si hay muchos, rotar las etiquetas
        num_trimestres = len(trimestres_validos)
        if num_trimestres > 16:
            # Si hay más de 16 trimestres, mostrar cada 2 para mejor legibilidad
            indices_mostrar = list(range(0, num_trimestres, 2))
            labels_mostrar = [trimestres_validos[i] for i in indices_mostrar]
            plt.xticks(indices_mostrar, labels_mostrar, rotation=45, ha='right', fontsize=9)
            # También mostrar el último trimestre si no está incluido
            if (num_trimestres - 1) not in indices_mostrar:
                indices_mostrar.append(num_trimestres - 1)
                labels_mostrar.append(trimestres_validos[-1])
                plt.xticks(indices_mostrar, labels_mostrar, rotation=45, ha='right', fontsize=9)
        else:
            # Mostrar todos los trimestres si son 16 o menos
            plt.xticks(range(num_trimestres), trimestres_validos, rotation=45, ha='right', fontsize=9)
        
        # Agregar valores en los puntos (solo algunos para no saturar)
        step = max(1, len(trimestres_validos) // 10)  # Mostrar aproximadamente 10 anotaciones
        for i in range(0, len(trimestres_validos), step):
            plt.annotate(f'{valores_validos[i]:.2f}', 
                        (i, valores_validos[i]), 
                        textcoords="offset points", 
                        xytext=(0,10), 
                        ha='center', 
                        fontsize=8)
        
        plt.tight_layout()
        if not return_data:
            plt.savefig(f'{ticker_str}_{ratio_key}_historico.png', dpi=300, bbox_inches='tight')
            print(f"Gráfica guardada: {ticker_str}_{ratio_key}_historico.png ({len(trimestres_validos)} trimestres)")
            plt.close()
        else:
            # Guardar datos para uso en GUI (no la figura, se creará en la GUI)
            figuras_ratios[ratio_key] = {
                'trimestres': trimestres_validos,
                'valores': valores_validos,
                'nombre': ratio_nombre
            }
            plt.close()  # Cerrar figura ya que crearemos una nueva en la GUI
    
    if return_data:
        print(f"\n=== Datos de ratios históricos obtenidos ===")
        print(f"Total de trimestres procesados: {len(trimestres_ordenados)} de {len(fechas_trimestrales)} disponibles")
        return figuras_ratios, ratios_data
    else:
        print(f"\n=== Gráficas de ratios históricos trimestrales completadas ===")
        print(f"Total de trimestres procesados: {len(trimestres_ordenados)} de {len(fechas_trimestrales)} disponibles")


def obtener_datos_investpy(ticker_str: str, country='colombia', years=5):
    """
    Función alternativa usando investpy para obtener datos históricos de acciones colombianas.
    Investpy extrae datos de Investing.com que tiene buena cobertura de acciones colombianas.
    
    Nota: investpy solo proporciona datos de precios históricos, no estados financieros.
    Para estados financieros, se debe usar yfinance o otra fuente.
    
    Args:
        ticker_str: Símbolo de la acción (ej: 'ECOPETROL', 'AVAL') - SIN el .CL
        country: País (default: 'colombia')
        years: Número de años de datos históricos a obtener (default: 5)
    
    Returns:
        DataFrame con datos históricos de precios (OHLCV) o None si hay error
    """
    try:
        # Obtener datos históricos de los últimos N años
        end_date = datetime.now().strftime('%d/%m/%Y')
        start_date = (datetime.now() - timedelta(days=years*365)).strftime('%d/%m/%Y')
        
        print(f"📊 Obteniendo datos históricos de {ticker_str} (Colombia) desde {start_date} hasta {end_date}...")
        df = ip.get_stock_historical_data(
            stock=ticker_str.upper(),
            country=country,
            from_date=start_date,
            to_date=end_date
        )
        
        if df is not None and not df.empty:
            print(f"✓ Datos obtenidos exitosamente: {len(df)} registros diarios")
            print(f"  Rango: {df.index[0].strftime('%Y-%m-%d')} a {df.index[-1].strftime('%Y-%m-%d')}")
            return df
        else:
            print("⚠️  No se obtuvieron datos.")
            return None
        
    except Exception as e:
        print(f"❌ Error al obtener datos con investpy: {e}")
        print("   Sugerencia: Verifica que el ticker sea correcto (sin .CL, ej: 'ECOPETROL' no 'ECOPETROL.CL')")
        return None


def obtener_ratios_alpha_vantage(ticker_str: str, api_key: str = None):
    """
    Función alternativa usando Alpha Vantage API para obtener datos financieros.
    
    Nota: Alpha Vantage requiere una API key gratuita (obtener en https://www.alphavantage.co/support/#api-key)
    Alpha Vantage tiene cobertura limitada de acciones colombianas.
    
    Args:
        ticker_str: Símbolo de la acción
        api_key: API key de Alpha Vantage (opcional, se puede configurar como variable de entorno)
    
    Returns:
        Dict con datos financieros o None si hay error
    """
    try:
        import requests
    except ImportError:
        print("⚠️  requests no está instalado. Instálalo con: pip install requests")
        return None
    
    if not api_key:
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            print("⚠️  Se requiere una API key de Alpha Vantage.")
            print("   Obtén una gratis en: https://www.alphavantage.co/support/#api-key")
            print("   O configura la variable de entorno: ALPHA_VANTAGE_API_KEY")
            return None
    
    try:
        # Obtener datos de la compañía
        url = f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker_str}&apikey={api_key}'
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if 'Error Message' in data:
            print(f"❌ Error de Alpha Vantage: {data['Error Message']}")
            return None
        
        if 'Note' in data:
            print(f"⚠️  Alpha Vantage: {data['Note']}")
            return None
        
        if data and 'Symbol' in data:
            print(f"✓ Datos obtenidos de Alpha Vantage para {data.get('Symbol', ticker_str)}")
            return data
        else:
            print("⚠️  No se encontraron datos para este ticker en Alpha Vantage.")
            print("   Alpha Vantage tiene cobertura limitada de acciones colombianas.")
            return None
        
    except Exception as e:
        print(f"❌ Error al obtener datos de Alpha Vantage: {e}")
        return None


def main_gui():
    """Inicia la aplicación con interfaz gráfica"""
    root = tk.Tk()
    app = AplicacionGUI(root)
    root.mainloop()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--gui':
        main_gui()
    else:
        # Por defecto, iniciar GUI
        main_gui()
        # Para usar la versión de consola, ejecutar: python estimacionValorJustoAccion.py --console
        # main()  # Descomentar para usar versión consola
