import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Quant Valuation Model", layout="wide")

st.sidebar.markdown("### Model Parameters")
ticker = st.sidebar.text_input("Ticker", "AAPL").upper()

st.sidebar.markdown("#### Cost of Capital (CAPM)")
rf_rate = st.sidebar.number_input("Risk-Free Rate (%)", value=4.20) / 100
erp = st.sidebar.number_input("Equity Risk Premium (%)", value=5.50) / 100
cost_of_debt = st.sidebar.number_input("Cost of Debt (%)", value=5.00) / 100
tax_rate = st.sidebar.number_input("Effective Tax Rate (%)", value=21.00) / 100

st.sidebar.markdown("#### Growth Assumptions")
g_stage1 = st.sidebar.number_input("Stage 1 Growth (Y1-5) (%)", value=10.0) / 100
g_stage2 = st.sidebar.number_input("Stage 2 Growth (Y6-10) (%)", value=5.0) / 100
g_terminal = st.sidebar.number_input("Terminal Growth (%)", value=2.5) / 100
target_margin = st.sidebar.number_input("Target EBIT Margin (%)", value=25.0) / 100
reinvestment_rate = st.sidebar.number_input("Reinvestment Rate (%)", value=15.0) / 100

if ticker:
    try:
        with st.spinner("Executing quantitative valuation model..."):
            stock = yf.Ticker(ticker)
            info = stock.info
            
            price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            shares = info.get('sharesOutstanding', 1)
            beta = info.get('beta', 1.0)
            
            bs = stock.balance_sheet
            fin = stock.financials
            
            cash = bs.loc['Cash And Cash Equivalents'].iloc[0] if 'Cash And Cash Equivalents' in bs.index else 0
            debt = bs.loc['Total Debt'].iloc[0] if 'Total Debt' in bs.index else 0
            revenue = fin.loc['Total Revenue'].iloc[0]
            
            equity_val_market = price * shares
            total_cap = equity_val_market + debt
            w_e = equity_val_market / total_cap if total_cap > 0 else 1
            w_d = debt / total_cap if total_cap > 0 else 0
            
            ke = rf_rate + (beta * erp)
            kd = cost_of_debt * (1 - tax_rate)
            wacc = (w_e * ke) + (w_d * kd)
            
            years = np.arange(1, 11)
            rev_proj = []
            fcff_proj = []
            
            curr_rev = revenue
            for y in years:
                curr_rev *= (1 + g_stage1) if y <= 5 else (1 + g_stage2)
                ebit = curr_rev * target_margin
                nopat = ebit * (1 - tax_rate)
                reinv = curr_rev * reinvestment_rate
                fcff = nopat - reinv
                
                rev_proj.append(curr_rev)
                fcff_proj.append(fcff)
                
            tv = (fcff_proj[-1] * (1 + g_terminal)) / (wacc - g_terminal)
            
            discount_factors = np.array([(1 + wacc) ** y for y in years])
            pv_fcff = np.sum(np.array(fcff_proj) / discount_factors)
            pv_tv = tv / ((1 + wacc) ** 10)
            
            ev = pv_fcff + pv_tv
            eq_val_intrinsic = ev + cash - debt
            implied_price = eq_val_intrinsic / shares
            mos = (implied_price - price) / implied_price if implied_price > 0 else 0

            st.markdown(f"## {ticker} | Advanced DCF & Sensitivity Analysis")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current Market Price", f"${price:,.2f}")
            c2.metric("Implied Fair Value", f"${implied_price:,.2f}", f"{mos*100:.1f}% MoS")
            c3.metric("Implied WACC", f"{wacc*100:.2f}%", f"Beta: {beta}")
            c4.metric("Enterprise Value", f"${ev/1e9:,.2f}B")
            
            st.markdown("---")
            
            col_chart, col_matrix = st.columns((1, 1))
            
            with col_chart:
                st.markdown("### 10-Year FCFF Projection")
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(x=years, y=fcff_proj, marker_color='#1f77b4', name='FCFF'))
                fig_bar.update_layout(template="plotly_white", margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with col_matrix:
                st.markdown("### Valuation Sensitivity Matrix")
                wacc_range = np.linspace(max(0.01, wacc - 0.02), wacc + 0.02, 5)
                tg_range = np.linspace(max(0.0, g_terminal - 0.01), g_terminal + 0.01, 5)
                
                matrix = np.zeros((5, 5))
                for i, w in enumerate(wacc_range):
                    for j, g in enumerate(tg_range):
                        if w <= g:
                            matrix[i, j] = np.nan
                            continue
                        m_tv = (fcff_proj[-1] * (1 + g)) / (w - g)
                        m_pv_tv = m_tv / ((1 + w) ** 10)
                        m_dfs = np.array([(1 + w) ** y for y in years])
                        m_pv_fcff = np.sum(np.array(fcff_proj) / m_dfs)
                        m_ev = m_pv_fcff + m_pv_tv
                        m_eq = m_ev + cash - debt
                        matrix[i, j] = m_eq / shares
                        
                fig_sens = px.imshow(matrix, 
                                     labels=dict(x="Terminal Growth Rate", y="Discount Rate (WACC)", color="Fair Value"),
                                     x=[f"{g*100:.1f}%" for g in tg_range],
                                     y=[f"{w*100:.1f}%" for w in wacc_range],
                                     text_auto=".2f", aspect="auto", color_continuous_scale="RdYlGn")
                fig_sens.update_layout(margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_sens, use_container_width=True)
            
    except Exception as e:
        st.error(f"Valuation exception triggered. Verify ticker symbol and data availability. Deep log: {e}")
