import streamlit as st
import yfinance as yf
import pandas as pd

# Nastavení vzhledu stránky
st.set_page_config(page_title="Můj DCF Kalkulátor", layout="wide")
st.title("📈 Vlastní DCF Kalkulátor (Gordon Growth)")
st.markdown("Tato aplikace stahuje živá data z Yahoo Finance a počítá vnitřní hodnotu akcie.")

# --- BOČNÍ PANEL (SIDEBAR) PRO VSTUPY ---
st.sidebar.header("1. Výběr akcie")
ticker_symbol = st.sidebar.text_input("Zadejte Ticker (např. NVO, AAPL, MSFT):", "NVO").upper()

st.sidebar.header("2. Nastavení (Assumptions)")
wacc = st.sidebar.slider("Diskontní sazba (WACC) %", 5.0, 15.0, 8.0, 0.5) / 100
terminal_growth = st.sidebar.slider("Terminální růst %", 0.0, 5.0, 2.0, 0.5) / 100
ebitda_margin = st.sidebar.slider("EBITDA Marže %", 5.0, 80.0, 48.0, 1.0) / 100
tax_rate = st.sidebar.slider("Daňová sazba %", 0.0, 40.0, 21.0, 1.0) / 100

st.sidebar.subheader("Očekávaný růst tržeb")
g1 = st.sidebar.number_input("Rok 1 (%)", value=15.0) / 100
g2 = st.sidebar.number_input("Rok 2 (%)", value=12.0) / 100
g3 = st.sidebar.number_input("Rok 3 (%)", value=10.0) / 100
g4 = st.sidebar.number_input("Rok 4 (%)", value=8.0) / 100
g5 = st.sidebar.number_input("Rok 5 (%)", value=6.0) / 100
revenue_growth = [g1, g2, g3, g4, g5]

# Fixní parametry (pro jednoduchost, lze z nich také udělat posuvníky)
dna_percent = 0.04
capex_percent = 0.08
nwc_percent = 0.01

# --- HLAVNÍ LOGIKA APLIKACE ---
if st.button("Spočítat Férovou Cenu", type="primary"):
    with st.spinner(f'Stahuji data pro {ticker_symbol}...'):
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Získání dat (s ošetřením, pokud API něco nevrátí)
        current_price = info.get('currentPrice', 0)
        shares_out = info.get('sharesOutstanding', 0)
        total_cash = info.get('totalCash', 0)
        total_debt = info.get('totalDebt', 0)
        ttm_revenue = info.get('totalRevenue', 0)
        
        if ttm_revenue == 0 or shares_out == 0:
            st.error("Chyba: Nepodařilo se stáhnout finanční data. Zkuste jiný ticker.")
        else:
            # Zobrazení stažených dat
            st.subheader(f"Základní data z rozvahy: {ticker_symbol}")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Aktuální cena", f"${current_price}")
            col2.metric("Hotovost (Cash)", f"${total_cash/1e9:.2f} mld")
            col3.metric("Dluh (Debt)", f"${total_debt/1e9:.2f} mld")
            col4.metric("Tržby (TTM)", f"${ttm_revenue/1e9:.2f} mld")
            
            # --- VÝPOČET DCF ---
            years = [1, 2, 3, 4, 5]
            last_revenue = ttm_revenue
            
            sum_pv_ufcf = 0
            final_year_ufcf = 0
            discount_factor_5 = 0
            
            # Tabulka pro zobrazení
            df_display = pd.DataFrame(index=['Tržby', 'EBITDA', 'NOPAT', 'FCF', 'Současná hodnota FCF'], columns=[f"Rok {y}" for y in years])

            for year in years:
                # Tržby a marže
                current_revenue = last_revenue * (1 + revenue_growth[year-1])
                ebitda = current_revenue * ebitda_margin
                dna = current_revenue * dna_percent
                ebit = ebitda - dna
                taxes = ebit * tax_rate
                nopat = ebit - taxes
                
                # Free Cash Flow
                capex = current_revenue * capex_percent
                nwc_change = current_revenue * nwc_percent
                ufcf = nopat + dna - capex - nwc_change
                
                # Diskontování
                discount_factor = 1 / ((1 + wacc) ** (year - 0.5))
                pv_of_ufcf = ufcf * discount_factor
                sum_pv_ufcf += pv_of_ufcf
                
                # Uložení do tabulky (v miliardách pro přehlednost)
                df_display.at['Tržby', f"Rok {y}"] = f"${current_revenue/1e9:.2f}"
                df_display.at['EBITDA', f"Rok {y}"] = f"${ebitda/1e9:.2f}"
                df_display.at['NOPAT', f"Rok {y}"] = f"${nopat/1e9:.2f}"
                df_display.at['FCF', f"Rok {y}"] = f"${ufcf/1e9:.2f}"
                df_display.at['Současná hodnota FCF', f"Rok {y}"] = f"${pv_of_ufcf/1e9:.2f}"
                
                last_revenue = current_revenue
                if year == 5:
                    final_year_ufcf = ufcf
                    discount_factor_5 = discount_factor

            # Terminální hodnota
            terminal_value = (final_year_ufcf * (1 + terminal_growth)) / (wacc - terminal_growth)
            pv_terminal_value = terminal_value * discount_factor_5
            
            # Celková hodnota
            enterprise_value = sum_pv_ufcf + pv_terminal_value
            equity_value = enterprise_value + total_cash - total_debt
            fair_value_per_share = equity_value / shares_out
            
            # --- ZOBRAZENÍ VÝSLEDKŮ ---
            st.divider()
            st.subheader("Výsledek Ocenění")
            
            margin_of_safety = ((fair_value_per_share - current_price) / current_price) * 100
            
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric("Vypočítaná Férová Cena", f"${fair_value_per_share:.2f}")
            res_col2.metric("Aktuální cena na burze", f"${current_price:.2f}")
            
            if margin_of_safety > 0:
                res_col3.metric("Bezpečnostní polštář (Sleva)", f"{margin_of_safety:.1f} %", "Podhodnoceno")
            else:
                res_col3.metric("Přirážka", f"{abs(margin_of_safety):.1f} %", "-Nadhodnoceno")
            
            st.markdown("### Detail pětileté projekce (v miliardách USD)")
            st.dataframe(df_display, use_container_width=True)
