import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# Nastavení vzhledu stránky
st.set_page_config(page_title="Profi DCF Valuace", layout="wide")
st.title("Mojkatko je prditko)")

# --- BOČNÍ PANEL: VSTUPY A PŘEDPOKLADY ---
st.sidebar.header("1. Výběr společnosti")
ticker = st.sidebar.text_input("Zadej Ticker (např. NVO, AAPL, MSFT)", "NVO").upper()

st.sidebar.header("2. Valuační předpoklady")
st.sidebar.markdown("Změň parametry a sleduj, jak trh reaguje.")

growth_1_5 = st.sidebar.slider("Růst tržeb (Roky 1-5)", min_value=-0.10, max_value=0.50, value=0.08, step=0.01)
growth_6_10 = st.sidebar.slider("Růst tržeb (Roky 6-10)", min_value=-0.05, max_value=0.20, value=0.04, step=0.01)
target_margin = st.sidebar.slider("Cílová EBIT marže", min_value=0.05, max_value=0.60, value=0.35, step=0.01)
wacc = st.sidebar.slider("Diskontní sazba (WACC)", min_value=0.05, max_value=0.15, value=0.08, step=0.005)

tax_rate = 0.21
reinvestment_rate = 0.15
terminal_growth = 0.025

# --- HLAVNÍ ČÁST: STAŽENÍ DAT A VÝPOČET ---
if ticker:
    with st.spinner(f"Stahuji data pro {ticker} a počítám komplexní DCF..."):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            current_price = info.get('currentPrice', 0)
            shares = info.get('sharesOutstanding', 1)
            
            # Bezpečné stažení účetních dat
            bs = stock.balance_sheet
            fin = stock.financials
            
            cash = bs.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in bs.index else 0
            debt = bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0
            revenue = fin.loc['Total Revenue'].iloc[0]
            ebit = fin.loc['EBIT'].iloc[0]
            
            # Výpočet DCF
            years = list(range(1, 11))
            revenues = []
            fcffs = []
            pv_fcffs = []
            
            proj_revenue = revenue
            for year in years:
                if year <= 5:
                    proj_revenue *= (1 + growth_1_5)
                else:
                    proj_revenue *= (1 + growth_6_10)
                
                proj_ebit = proj_revenue * target_margin
                nopat = proj_ebit * (1 - tax_rate)
                reinvestment = proj_revenue * reinvestment_rate
                fcff = nopat - reinvestment
                
                pv = fcff / ((1 + wacc) ** year)
                
                revenues.append(proj_revenue)
                fcffs.append(fcff)
                pv_fcffs.append(pv)
            
            # Terminální hodnota
            tv = (fcffs[-1] * (1 + terminal_growth)) / (wacc - terminal_growth)
            pv_tv = tv / ((1 + wacc) ** 10)
            
            # Finální cena
            enterprise_value = sum(pv_fcffs) + pv_tv
            equity_value = enterprise_value + cash - debt
            fair_value = equity_value / shares
            
            margin_of_safety = ((fair_value - current_price) / fair_value) * 100
            
            # --- VYKRESLENÍ VÝSLEDKŮ ---
            col1, col2, col3 = st.columns(3)
            col1.metric("Aktuální tržní cena", f"${current_price:,.2f}")
            col2.metric("Tvoje Vnitřní hodnota (Fair Value)", f"${fair_value:,.2f}", f"{margin_of_safety:.1f}% Margin of Safety")
            col3.metric("Očekávané tržby v 10. roce", f"${revenues[-1]/1e9:,.1f} Mld.")

            # Interaktivní graf (Plotly)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=years, y=fcffs, name="Volné Cash Flow (FCFF)", marker_color='#2ca02c'))
            fig.add_trace(go.Scatter(x=years, y=revenues, name="Projekce Tržeb", mode='lines+markers', yaxis='y2', line=dict(color='#1f77b4', width=3)))
            
            fig.update_layout(
                title=f"Projekce růstu a hotovosti na 10 let ({ticker})",
                xaxis=dict(title="Roky do budoucnosti"),
                yaxis=dict(title="Cash Flow (USD)", side='left'),
                yaxis2=dict(title="Tržby (USD)", side='right', overlaying='y'),
                hovermode="x unified",
                template="plotly_white"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.success("Tento model bere v úvahu obří komplexitu: 2-fázový růst tržeb, kompresi marží, reinvestiční potřeby, daně a časovou hodnotu peněz. To vše přepočítáno v reálném čase.")

        except Exception as e:
            st.error(f"Chyba při stahování dat: Omlouváme se, některá účetní data chybí nebo je Ticker špatně zadán. Detaily: {e}")
