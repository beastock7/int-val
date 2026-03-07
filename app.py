import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- NASTAVENÍ STRÁNKY ---
st.set_page_config(page_title="Auto-DCF Model", page_icon="🤖", layout="wide")
st.title("🤖 Plně Automatizovaný DCF Model")
st.markdown("Tento model analyzuje historii firmy a automaticky generuje realistické projekce na 5 let.")

# --- FUNKCE PRO AUTOMATICKOU ANALÝZU HISTORIE ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_and_analyze(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. Základní data z rozvahy
        if 'currentPrice' not in info:
            return None
            
        base_data = {
            'price': info.get('currentPrice', 0),
            'shares': info.get('sharesOutstanding', 0),
            'cash': info.get('totalCash', 0),
            'debt': info.get('totalDebt', 0),
            'revenue': info.get('totalRevenue', 0)
        }
        
        # 2. Historická analýza (Income Statement & Cash Flow)
        fin = ticker.financials
        cf = ticker.cashflow
        
        # Výchozí konzervativní hodnoty (kdyby API selhalo)
        avg_growth = 0.08
        avg_margin = 0.15
        avg_capex = 0.05
        avg_dna = 0.04
        
        if not fin.empty and not cf.empty:
            try:
                # Historické tržby a růst
                rev_history = fin.loc['Total Revenue'].dropna()
                if len(rev_history) >= 2:
                    # Výpočet meziročního růstu (od nejstaršího po nejnovější)
                    growth_rates = rev_history.pct_change(-1).dropna()
                    avg_growth = max(min(growth_rates.mean(), 0.25), 0.02) # Zastropujeme extrémy (max 25%, min 2%)
                
                # Historická EBITDA marže
                if 'EBITDA' in fin.index:
                    ebitda_history = fin.loc['EBITDA'].dropna()
                    margin_history = ebitda_history / rev_history
                    avg_margin = max(margin_history.mean(), 0.05)
                
                # Historický CapEx
                if 'Capital Expenditure' in cf.index:
                    capex_history = abs(cf.loc['Capital Expenditure'].dropna())
                    capex_pct_history = capex_history / rev_history
                    avg_capex = max(min(capex_pct_history.mean(), 0.20), 0.01)
                    
                # Historické odpisy (D&A)
                if 'Depreciation And Amortization' in cf.index:
                    dna_history = cf.loc['Depreciation And Amortization'].dropna()
                    dna_pct_history = dna_history / rev_history
                    avg_dna = max(min(dna_pct_history.mean(), 0.15), 0.01)
                    
            except Exception as e:
                pass # Při chybě se použijí výchozí hodnoty
                
        return base_data, avg_growth, avg_margin, avg_capex, avg_dna
        
    except Exception:
        return None

# --- BOČNÍ PANEL ---
with st.sidebar:
    st.header("1. Výběr společnosti")
    ticker_input = st.text_input("Zadejte Ticker (např. AAPL, NVDA, F):", "AAPL").upper()
    
    st.header("2. Makro parametry")
    wacc = st.number_input("Diskontní sazba (WACC) v %", min_value=1.0, max_value=25.0, value=9.0, step=0.1) / 100
    tgr = st.number_input("Terminální růst (TGR) v %", min_value=0.0, max_value=5.0, value=2.5, step=0.1) / 100
    tax_rate = st.number_input("Efektivní daňová sazba v %", min_value=0.0, max_value=40.0, value=21.0, step=1.0) / 100

# --- NAČTENÍ A AUTOMATIZACE ---
result = fetch_and_analyze(ticker_input)

if result is None:
    st.error("⚠️ Nepodařilo se stáhnout data. Zkuste jiný ticker nebo počkejte chvíli.")
else:
    base_data, avg_growth, avg_margin, avg_capex, avg_dna = result
    
    current_price = base_data['price']
    shares_out = base_data['shares']
    total_cash = base_data['cash']
    total_debt = base_data['debt']
    ttm_revenue = base_data['revenue']
    
    st.subheader(f"📊 Aktuální data: {ticker_input}")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Cena na burze", f"${current_price:.2f}")
    col2.metric("Počet akcií", f"{shares_out/1e9:.2f} mld")
    col3.metric("Hotovost", f"${total_cash/1e9:.2f} mld")
    col4.metric("Dluh", f"${total_debt/1e9:.2f} mld")
    col5.metric("Tržby TTM", f"${ttm_revenue/1e9:.2f} mld")

    # --- AUTOMATICKY VYGENEROVANÁ TABULKA ---
    st.divider()
    st.subheader("⚙️ Automatická projekce (vygenerováno z historických průměrů)")
    st.caption("Model sám analyzoval účetnictví. Růst tržeb modelujeme tak, že postupně klesá (tzv. Decay model). Data můžete přepsat.")

    # Tvorba "Decay" růstu (začínáme na průměru a každý rok mírně zpomalujeme o 10 %)
    g_rates = [round(avg_growth * (0.9 ** i) * 100, 1) for i in range(5)]
    
    default_assumptions = pd.DataFrame({
        "Růst tržeb (%)": g_rates,
        "EBITDA Marže (%)": [round(avg_margin * 100, 1)] * 5,
        "Odpisy (D&A) % z tržeb": [round(avg_dna * 100, 1)] * 5,
        "CapEx % z tržeb": [round(avg_capex * 100, 1)] * 5,
        "Změna NWC % z tržeb": [1.0] * 5 # Konzervativní 1% pro NWC
    }, index=["Rok 1", "Rok 2", "Rok 3", "Rok 4", "Rok 5"])

    edited_assumptions = st.data_editor(default_assumptions, use_container_width=True)

    # --- VÝPOČTOVÉ JÁDRO DCF ---
    if st.button("Spustit DCF Valuaci", type="primary", use_container_width=True):
        assump = edited_assumptions / 100 
        years = [1, 2, 3, 4, 5]
        
        last_revenue = ttm_revenue
        sum_pv_ufcf = 0
        final_year_ufcf = 0
        final_discount_factor = 0
        
        for i, year in enumerate(years):
            row_idx = f"Rok {year}"
            
            current_revenue = last_revenue * (1 + assump.at[row_idx, "Růst tržeb (%)"])
            ebitda = current_revenue * assump.at[row_idx, "EBITDA Marže (%)"]
            dna = current_revenue * assump.at[row_idx, "Odpisy (D&A) % z tržeb"]
            ebit = ebitda - dna
            nopat = ebit * (1 - tax_rate)
            
            capex = current_revenue * assump.at[row_idx, "CapEx % z tržeb"]
            nwc_change = current_revenue * assump.at[row_idx, "Změna NWC % z tržeb"]
            ufcf = nopat + dna - capex - nwc_change
            
            discount_factor = 1 / ((1 + wacc) ** (year - 0.5))
            pv_ufcf = ufcf * discount_factor
            sum_pv_ufcf += pv_ufcf
            
            last_revenue = current_revenue
            if year == 5:
                final_year_ufcf = ufcf
                final_discount_factor = discount_factor

        # Terminální hodnota a valuace
        terminal_value = (final_year_ufcf * (1 + tgr)) / (wacc - tgr)
        pv_terminal_value = terminal_value * final_discount_factor
        
        enterprise_value = sum_pv_ufcf + pv_terminal_value
        equity_value = enterprise_value + total_cash - total_debt
        fair_value_per_share = equity_value / shares_out
        margin_of_safety = ((fair_value_per_share - current_price) / current_price) * 100

        # --- VÝSLEDKY ---
        st.divider()
        st.header("🏆 Výsledek Automatické Valuace")
        
        res1, res2, res3 = st.columns(3)
        res1.metric("Vnitřní hodnota (Fair Value)", f"${fair_value_per_share:.2f}")
        res2.metric("Aktuální cena na burze", f"${current_price:.2f}")
        if margin_of_safety > 0:
            res3.metric("Bezpečnostní polštář", f"{margin_of_safety:.1f} %", "Podhodnoceno")
        else:
            res3.metric("Přirážka", f"{abs(margin_of_safety):.1f} %", "-Nadhodnoceno")
            
        st.info("💡 Tento výpočet je založen na historických výsledcích firmy. Ujistěte se, že historické průměry v tabulce výše odpovídají vašemu očekávání pro budoucnost.")
