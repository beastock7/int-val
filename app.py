import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Excel-Matched DCF Engine", layout="wide")

st.markdown("## DCF")

# --- SIDEBAR ---
st.sidebar.markdown("### 1. Výběr akcie")
ticker = st.sidebar.text_input("Ticker", "NVO").upper()

st.sidebar.markdown("### 2. Manuální přepis surových dat")
st.sidebar.markdown("*Nech 0.0 pro automatické stažení z webu*")
shares_over = st.sidebar.number_input("Akcie v oběhu (Mld. ks)", value=0.0, step=0.1)
cash_over = st.sidebar.number_input("Hotovost (Mld. USD)", value=0.0, step=0.1)
debt_over = st.sidebar.number_input("Celkový dluh (Mld. USD)", value=0.0, step=0.1)
rev_over = st.sidebar.number_input("Tržby za 12M (Mld. USD)", value=0.0, step=0.1)

st.sidebar.markdown("### 3. Předpoklady růstu")
g_1_to_5 = st.sidebar.number_input("Růst tržeb (Rok 1-5) %", value=0.0) / 100
g_6_to_10 = st.sidebar.number_input("Růst tržeb (Rok 6-10) %", value=3.0) / 100
ebit_margin = st.sidebar.number_input("Cílová EBIT marže %", value=44.02) / 100
reinv_rate = st.sidebar.number_input("Reinvestiční poměr (z tržeb) %", value=15.0) / 100
tax_rate = st.sidebar.number_input("Efektivní daň (%)", value=21.0) / 100
g_terminal = st.sidebar.number_input("Terminální růst (%)", value=2.5) / 100

st.sidebar.markdown("### 4. Náklady kapitálu (WACC)")
rf_rate = st.sidebar.number_input("Bezriziková sazba %", value=4.2) / 100
erp = st.sidebar.number_input("Prémie za riziko (ERP) %", value=5.5) / 100
cost_of_debt_raw = st.sidebar.number_input("Úroková sazba dluhu %", value=5.0) / 100
beta_over = st.sidebar.number_input("Beta (0.0 = Auto)", value=0.0, step=0.1)

if ticker:
    try:
        with st.spinner(f"Zpracovávám model pro {ticker}..."):
            stock = yf.Ticker(ticker)
            info = stock.info
            bs = stock.balance_sheet
            fin = stock.financials
            
            # --- ZÍSKÁNÍ NEBO PŘEPIS DAT ---
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            
            shares = shares_over * 1e9 if shares_over > 0 else info.get('sharesOutstanding', 1)
            beta = beta_over if beta_over > 0 else info.get('beta', 1.0)
            market_cap = price * shares
            
            if cash_over > 0:
                cash = cash_over * 1e9
            else:
                cash = bs.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in bs.index else 0
                if 'Other Short Term Investments' in bs.index and pd.notna(bs.loc['Other Short Term Investments'].iloc[0]):
                    cash += bs.loc['Other Short Term Investments'].iloc[0]
                    
            debt = debt_over * 1e9 if debt_over > 0 else (bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0)
            revenue = rev_over * 1e9 if rev_over > 0 else (fin.loc['Total Revenue'].iloc[0] if 'Total Revenue' in fin.index else 0)
            
            # 4. VÝPOČET WACC
            ke = rf_rate + (beta * erp)
            kd = cost_of_debt_raw * (1 - tax_rate)
            w_e = market_cap / (market_cap + debt) if (market_cap + debt) > 0 else 1
            w_d = debt / (market_cap + debt) if (market_cap + debt) > 0 else 0
            wacc = (w_e * ke) + (w_d * kd)
            
            # 5. PROJEKCE TRŽEB A FCFF
            proj_data = []
            pv_fcff_total = 0
            current_rev = revenue
            
            for year in range(1, 11):
                if year <= 5:
                    current_rev *= (1 + g_1_to_5)
                else:
                    current_rev *= (1 + g_6_to_10)
                    
                current_ebit = current_rev * ebit_margin
                nopat = current_ebit * (1 - tax_rate)
                reinvestment = current_rev * reinv_rate
                fcff = nopat - reinvestment
                
                discount_factor = (1 + wacc) ** year
                pv_fcff = fcff / discount_factor
                pv_fcff_total += pv_fcff
                
                proj_data.append({"Rok": year, "Tržby": current_rev, "FCFF": fcff, "PV FCFF": pv_fcff})
                
            df_proj = pd.DataFrame(proj_data).set_index("Rok")
            
            # 6. TERMINÁLNÍ HODNOTA A VALUACE
            last_fcff = df_proj.iloc[9]["FCFF"]
            tv = (last_fcff * (1 + g_terminal)) / (wacc - g_terminal)
            pv_tv = tv / ((1 + wacc) ** 10)
            
            enterprise_value = pv_fcff_total + pv_tv
            equity_value = enterprise_value + cash - debt
            fair_value = equity_value / shares
            mos = ((fair_value - price) / fair_value) * 100 if fair_value > 0 else 0
            
            # --- VÝPIS VÝSLEDKŮ ---
            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Aktuální tržní cena", f"${price:,.2f}")
            c2.metric("Vnitřní hodnota (Fair Value)", f"${fair_value:,.2f}", f"{mos:.2f}% Margin of Safety")
            c3.metric("WACC (Diskontní sazba)", f"{wacc*100:.2f}%")
            c4.metric("Použité tržby", f"${revenue/1e9:,.2f} B")

            st.markdown("### 📊 Vstupy po očištění (Pro kontrolu)")
            st.info(f"Akcie v oběhu: **{shares/1e9:,.2f} mld.** | Hotovost: **${cash/1e9:,.2f} mld.** | Dluh: **${debt/1e9:,.2f} mld.** | Beta: **{beta}**")
            
            st.markdown("### 📊 10letá projekce Cash Flow")
            st.dataframe(df_proj.style.format("{:,.0f}"), use_container_width=True)

    except Exception as e:
        st.error(f"Chyba při výpočtu: {e}")
