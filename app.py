import streamlit as st
import pandas as pd

st.set_page_config(page_title="Excel-Matched DCF", layout="wide")

st.title("DCF")

def parse_input(val):
    try:
        # Odstraní mezery a nahradí české čárky za tečky
        return float(val.replace(" ", "").replace(",", "."))
    except:
        return 0.0

# --- SIDEBAR: VSTUPY ---
st.sidebar.header("Data")
st.sidebar.caption("Zadávej celá čísla včetně nul (např. 3370000000).")

price_input = st.sidebar.text_input("Aktuální cena", "38.33")
shares_input = st.sidebar.text_input("Akcie v oběhu", "3370000000")
cash_input = st.sidebar.text_input("Hotovost a ekv.", "4260000000")
debt_input = st.sidebar.text_input("Celkový dluh", "20680000000")
rev_input = st.sidebar.text_input("Tržby za 12M", "46790000000")
beta_input = st.sidebar.text_input("Beta", "0.76")

st.sidebar.header("2. Předpoklady (Zadávej v %)")
g_1_to_5 = st.sidebar.number_input("Růst tržeb (Rok 1-5) %", value=0.0) / 100
g_6_to_10 = st.sidebar.number_input("Růst tržeb (Rok 6-10) %", value=3.0) / 100
ebit_margin = st.sidebar.number_input("Cílová EBIT marže %", value=44.02) / 100
reinv_rate = st.sidebar.number_input("Reinvestiční poměr %", value=15.0) / 100
tax_rate = st.sidebar.number_input("Efektivní daň %", value=21.0) / 100
g_terminal = st.sidebar.number_input("Terminální růst %", value=2.5) / 100

st.sidebar.header("3. WACC parametry")
rf_rate = st.sidebar.number_input("Bezriziková sazba %", value=4.2) / 100
erp = st.sidebar.number_input("Prémie za riziko %", value=5.5) / 100
cost_of_debt_raw = st.sidebar.number_input("Úroková sazba dluhu %", value=5.0) / 100

# --- VÝPOČET ---
price = parse_input(price_input)
shares = parse_input(shares_input)
cash = parse_input(cash_input)
debt = parse_input(debt_input)
revenue = parse_input(rev_input)
beta = parse_input(beta_input)

if shares > 0 and revenue > 0:
    # WACC
    market_cap = price * shares
    ke = rf_rate + (beta * erp)
    kd = cost_of_debt_raw * (1 - tax_rate)
    
    w_e = market_cap / (market_cap + debt)
    w_d = debt / (market_cap + debt)
    wacc = (w_e * ke) + (w_d * kd)
    
    # PROJEKCE
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
        
        pv_fcff = fcff / ((1 + wacc) ** year)
        pv_fcff_total += pv_fcff
        
        proj_data.append({
            "Rok": year, 
            "Tržby": current_rev, 
            "FCFF": fcff, 
            "PV FCFF": pv_fcff
        })
        
    df_proj = pd.DataFrame(proj_data).set_index("Rok")
    
    # TERMINÁLNÍ HODNOTA A FINÁLNÍ CENA
    last_fcff = df_proj.iloc[9]["FCFF"]
    tv = (last_fcff * (1 + g_terminal)) / (wacc - g_terminal)
    pv_tv = tv / ((1 + wacc) ** 10)
    
    enterprise_value = pv_fcff_total + pv_tv
    equity_value = enterprise_value + cash - debt
    fair_value = equity_value / shares
    mos = ((fair_value - price) / fair_value) * 100 if fair_value > 0 else 0
    
    # --- VÝSTUP ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zadaná cena z Excelu", f"${price:,.2f}")
    c2.metric("Vnitřní hodnota (Fair Value)", f"${fair_value:,.2f}", f"{mos:.2f}% Margin of Safety")
    c3.metric("WACC (Diskontní sazba)", f"{wacc*100:.2f}%")
    c4.metric("Market Cap", f"${market_cap/1e9:,.2f} B")
    
    st.markdown("### 📊 10letá projekce Cash Flow")
    st.dataframe(df_proj.style.format("{:,.0f}"), use_container_width=True)

else:
    st.warning("Zadej do levého panelu platná čísla z Excelu, aby mohl výpočet začít.")
