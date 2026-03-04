import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="Institutional Valuation Engine", layout="wide")

st.markdown("## ⚙️ Institutional DCF Engine")
st.markdown("Žádné grafy, jen tvrdá data. 3-Stage Fade, SBC úpravy a Duální terminální hodnota.")

# --- SIDEBAR: PROFI NASTAVENÍ ---
st.sidebar.markdown("### 1. Vstupy & Účetnictví")
ticker = st.sidebar.text_input("Ticker", "MSFT").upper()
shares_override = st.sidebar.number_input("Akcie v oběhu (Mld. ks) - 0 pro auto", value=0.0)

st.sidebar.markdown("### 2. Valuační Předpoklady")
g_year_1 = st.sidebar.number_input("Růst tržeb (Rok 1) %", value=15.0) / 100
target_margin = st.sidebar.number_input("Cílová EBIT marže (Rok 10) %", value=35.0) / 100
sbc_penalty = st.sidebar.number_input("SBC jako % z tržeb (Náklad)", value=2.0) / 100
tax_rate = st.sidebar.number_input("Efektivní daň (%)", value=18.0) / 100
reinvestment_rate = st.sidebar.number_input("Reinvestiční poměr (CapEx-D&A) %", value=15.0) / 100

st.sidebar.markdown("### 3. Kapitál & Riziko (WACC)")
rf_rate = st.sidebar.number_input("Bezriziková sazba (10Y Bond) %", value=4.2) / 100
erp = st.sidebar.number_input("Market Risk Premium %", value=5.5) / 100
cost_of_debt = st.sidebar.number_input("Náklad na dluh %", value=5.0) / 100

st.sidebar.markdown("### 4. Terminální Hodnota")
g_terminal = st.sidebar.number_input("Perpetuity Growth Rate %", value=2.5) / 100
exit_multiple = st.sidebar.number_input("Exit EV/EBITDA Multiple", value=18.0)
tv_weight_pgr = st.sidebar.slider("Váha PGR modelu vůči Exit Multiple", 0.0, 1.0, 0.5)

if ticker:
    try:
        with st.spinner("Sestavuji datový model..."):
            # 1. STAŽENÍ DAT
            stock = yf.Ticker(ticker)
            info = stock.info
            
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            beta = info.get('beta', 1.0)
            shares = shares_override * 1e9 if shares_override > 0 else info.get('sharesOutstanding', 1)
            
            bs = stock.balance_sheet
            fin = stock.financials
            
            # Ošetření chybějících dat
            cash = bs.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in bs.index else 0
            if 'Other Short Term Investments' in bs.index and pd.notna(bs.loc['Other Short Term Investments'].iloc[0]):
                cash += bs.loc['Other Short Term Investments'].iloc[0]
                
            debt = bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0
            revenue = fin.loc['Total Revenue'].iloc[0]
            ebit = fin.loc['EBIT'].iloc[0]
            ebitda = fin.loc['EBITDA'].iloc[0] if 'EBITDA' in fin.index else ebit * 1.2 
            
            current_margin = ebit / revenue if revenue > 0 else target_margin
            
            # 2. VÝPOČET WACC
            equity_val_market = price * shares
            total_cap = equity_val_market + debt
            w_e = equity_val_market / total_cap if total_cap > 0 else 1
            w_d = debt / total_cap if total_cap > 0 else 0
            
            ke = rf_rate + (beta * erp)
            kd = cost_of_debt * (1 - tax_rate)
            wacc = (w_e * ke) + (w_d * kd)
            
            # 3. TVORBA 10LETÉ PROJEKCE (Fade Model)
            years = np.arange(1, 11)
            
            growth_rates = np.linspace(g_year_1, g_terminal, 10)
            margins = np.linspace(current_margin, target_margin, 10)
            
            proj_data = []
            curr_rev = revenue
            
            for y, g, m in zip(years, growth_rates, margins):
                curr_rev *= (1 + g)
                curr_ebit = curr_rev * m
                adj_ebit = curr_ebit - (curr_rev * sbc_penalty)
                
                nopat = adj_ebit * (1 - tax_rate)
                reinv = curr_rev * reinvestment_rate
                fcff = nopat - reinv
                
                proj_data.append({
                    "Rok": y,
                    "Růst (%)": g * 100,
                    "Tržby (Mld.)": curr_rev / 1e9,
                    "EBIT Marže (%)": m * 100,
                    "EBITDA (Mld.)": (curr_ebit * 1.2) / 1e9,
                    "NOPAT (Mld.)": nopat / 1e9,
                    "FCFF (Mld.)": fcff / 1e9
                })
                
            df_proj = pd.DataFrame(proj_data)
            df_proj.set_index("Rok", inplace=True)
            
            # 4. DISKONTOVÁNÍ A TERMINÁLNÍ HODNOTA
            fcff_array = df_proj["FCFF (Mld.)"].values * 1e9
            discount_factors = np.array([(1 + wacc) ** y for y in years])
            pv_fcff = np.sum(fcff_array / discount_factors)
            
            tv_pgr = (fcff_array[-1] * (1 + g_terminal)) / (wacc - g_terminal)
            
            final_ebitda = df_proj["EBITDA (Mld.)"].values[-1] * 1e9
            tv_mult = final_ebitda * exit_multiple
            
            tv_blended = (tv_pgr * tv_weight_pgr) + (tv_mult * (1 - tv_weight_pgr))
            pv_tv = tv_blended / ((1 + wacc) ** 10)
            
            # 5. ENTERPRISE A EQUITY VALUE
            ev = pv_fcff + pv_tv
            eq_val = ev + cash - debt
            implied_price = eq_val / shares
            mos = (implied_price - price) / implied_price if implied_price > 0 else 0
            
            # --- VÝPIS VÝSLEDKŮ ---
            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Aktuální Cena", f"${price:,.2f}")
            c2.metric("Vnitřní Hodnota (Blended)", f"${implied_price:,.2f}", f"{mos*100:.1f}% Margin of Safety")
            c3.metric("WACC (Diskontní sazba)", f"{wacc*100:.2f}%", f"Beta: {beta}")
            c4.metric("Enterprise Value", f"${ev/1e9:,.2f} B")
            
            st.markdown("### 📊 10-Year Financial Projection Matrix")
            # Tady byla ta chyba. Odstranil jsem background_gradient.
            st.dataframe(df_proj.style.format("{:.2f}"), use_container_width=True)
            
            st.markdown("### 🔬 Rozpad Terminální Hodnoty (Terminal Value Breakdown)")
            t1, t2, t3 = st.columns(3)
            t1.metric("Hodnota přes PGR Model", f"${(tv_pgr / ((1 + wacc)**10))/1e9:,.2f} B", f"Váha: {tv_weight_pgr*100}%")
            t2.metric("Hodnota přes Exit Multiple", f"${(tv_mult / ((1 + wacc)**10))/1e9:,.2f} B", f"Váha: {(1-tv_weight_pgr)*100}%")
            t3.metric("Současná hodnota hotovosti 1-10 let", f"${pv_fcff/1e9:,.2f} B")
            
    except Exception as e:
        st.error(f"Chyba při výpočtu. Data pro tento ticker možná chybí v DB. Log: {e}")
