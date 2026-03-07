import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# --- NASTAVENÍ STRÁNKY ---
st.set_page_config(page_title="PRO DCF Model", page_icon="🏦", layout="wide")
st.title("🏦 Profesionální DCF Kalkulátor (Gordon Growth)")
st.markdown("Striktní model vnitřní hodnoty na bázi Unlevered Free Cash Flow (UFCF).")

# --- FUNKCE PRO STAŽENÍ DAT S OCHRANOU PROTI CHYBÁM ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_financials(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        if 'currentPrice' not in info:
            return None # API blokuje nebo ticker neexistuje
        return {
            'price': info.get('currentPrice', 0),
            'shares': info.get('sharesOutstanding', 0),
            'cash': info.get('totalCash', 0),
            'debt': info.get('totalDebt', 0),
            'revenue': info.get('totalRevenue', 0)
        }
    except Exception:
        return None

# --- BOČNÍ PANEL (ZÁKLADNÍ PARAMETRY) ---
with st.sidebar:
    st.header("1. Výběr společnosti")
    ticker_input = st.text_input("Zadejte Ticker (např. AMZN, AAPL):", "AMZN").upper()
    
    st.header("2. Makro parametry")
    wacc = st.number_input("Diskontní sazba (WACC) v %", min_value=1.0, max_value=25.0, value=8.5, step=0.1) / 100
    tgr = st.number_input("Terminální růst (TGR) v %", min_value=0.0, max_value=5.0, value=2.5, step=0.1) / 100
    tax_rate = st.number_input("Efektivní daňová sazba v %", min_value=0.0, max_value=40.0, value=18.0, step=1.0) / 100

# --- NAČTENÍ DAT A MANUÁLNÍ FALLBACK ---
data = fetch_financials(ticker_input)

st.subheader("📊 Základní finanční data (Rozvaha)")
if data is None:
    st.warning("⚠️ Yahoo Finance momentálně blokuje automatické stažení. Zadejte data ručně:")
    col1, col2, col3, col4, col5 = st.columns(5)
    current_price = col1.number_input("Cena akcie ($)", value=175.0)
    shares_out = col2.number_input("Počet akcií", value=10400000000)
    total_cash = col3.number_input("Hotovost ($)", value=86000000000)
    total_debt = col4.number_input("Dluh ($)", value=58000000000)
    ttm_revenue = col5.number_input("Tržby TTM ($)", value=574000000000)
else:
    current_price = data['price']
    shares_out = data['shares']
    total_cash = data['cash']
    total_debt = data['debt']
    ttm_revenue = data['revenue']
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Aktuální cena", f"${current_price:.2f}")
    col2.metric("Počet akcií", f"{shares_out/1e9:.2f} mld")
    col3.metric("Hotovost", f"${total_cash/1e9:.2f} mld")
    col4.metric("Dluh", f"${total_debt/1e9:.2f} mld")
    col5.metric("Tržby TTM", f"${ttm_revenue/1e9:.2f} mld")

# --- INTERAKTIVNÍ TABULKA PŘEDPOKLADŮ (ASSUMPTIONS) ---
st.divider()
st.subheader("⚙️ Projekce na 5 let (Upravte hodnoty v tabulce)")
st.caption("Hodnoty zadávejte v procentech (např. 12 pro 12 %). Tabulka funguje jako Excel.")

# Výchozí hodnoty (např. pro Amazon z předchozí debaty)
default_assumptions = pd.DataFrame({
    "Růst tržeb (%)": [12.0, 11.5, 10.0, 9.0, 8.0],
    "EBITDA Marže (%)": [21.0, 21.5, 22.0, 22.0, 22.5],
    "Odpisy (D&A) % z tržeb": [9.0, 9.0, 9.0, 8.5, 8.5],
    "CapEx % z tržeb": [18.0, 16.0, 14.0, 12.0, 10.0],
    "Změna NWC % z tržeb": [0.0, 0.0, 0.0, 0.0, 0.0]
}, index=["Rok 1", "Rok 2", "Rok 3", "Rok 4", "Rok 5"])

# Zobrazení st.data_editor (Uživatel může přepisovat data)
edited_assumptions = st.data_editor(default_assumptions, use_container_width=True)

# --- VÝPOČTOVÉ JÁDRO DCF ---
if st.button("Spustit DCF Model", type="primary", use_container_width=True):
    # Převod zadaných procent na desetinná čísla
    assump = edited_assumptions / 100 
    
    years = [1, 2, 3, 4, 5]
    dcf_df = pd.DataFrame(index=['Tržby', 'EBITDA', 'D&A', 'EBIT', 'NOPAT', 'CapEx', 'Změna NWC', 'UFCF', 'Diskontní faktor', 'Současná hodnota UFCF'], columns=[f"Rok {y}" for y in years])
    
    last_revenue = ttm_revenue
    sum_pv_ufcf = 0
    
    for i, year in enumerate(years):
        col_name = f"Rok {year}"
        row_idx = f"Rok {year}"
        
        # 1. Provozní výsledky
        current_revenue = last_revenue * (1 + assump.at[row_idx, "Růst tržeb (%)"])
        ebitda = current_revenue * assump.at[row_idx, "EBITDA Marže (%)"]
        dna = current_revenue * assump.at[row_idx, "Odpisy (D&A) % z tržeb"]
        ebit = ebitda - dna
        nopat = ebit * (1 - tax_rate)
        
        # 2. Peněžní toky (Cash Flow)
        capex = current_revenue * assump.at[row_idx, "CapEx % z tržeb"]
        nwc_change = current_revenue * assump.at[row_idx, "Změna NWC % z tržeb"]
        
        # Striktní vzorec pro Unlevered Free Cash Flow
        ufcf = nopat + dna - capex - nwc_change
        
        # 3. Diskontování (Mid-Year Convention)
        discount_factor = 1 / ((1 + wacc) ** (year - 0.5))
        pv_ufcf = ufcf * discount_factor
        sum_pv_ufcf += pv_ufcf
        
        # Zápis do tabulky
        dcf_df.at['Tržby', col_name] = current_revenue
        dcf_df.at['EBITDA', col_name] = ebitda
        dcf_df.at['D&A', col_name] = dna
        dcf_df.at['EBIT', col_name] = ebit
        dcf_df.at['NOPAT', col_name] = nopat
        dcf_df.at['CapEx', col_name] = capex
        dcf_df.at['Změna NWC', col_name] = nwc_change
        dcf_df.at['UFCF', col_name] = ufcf
        dcf_df.at['Diskontní faktor', col_name] = discount_factor
        dcf_df.at['Současná hodnota UFCF', col_name] = pv_ufcf
        
        last_revenue = current_revenue
        
        if year == 5:
            final_year_ufcf = ufcf
            final_discount_factor = discount_factor

    # 4. Terminální hodnota (Gordon Growth)
    terminal_value = (final_year_ufcf * (1 + tgr)) / (wacc - tgr)
    pv_terminal_value = terminal_value * final_discount_factor
    
    # 5. Finální valuace
    enterprise_value = sum_pv_ufcf + pv_terminal_value
    equity_value = enterprise_value + total_cash - total_debt
    fair_value_per_share = equity_value / shares_out
    margin_of_safety = ((fair_value_per_share - current_price) / current_price) * 100

    # --- ZOBRAZENÍ VÝSLEDKŮ ---
    st.divider()
    st.header("🏆 Výsledek Valuace")
    
    # Metriky
    res1, res2, res3 = st.columns(3)
    res1.metric("Vnitřní hodnota (Fair Value)", f"${fair_value_per_share:.2f}")
    res2.metric("Aktuální cena na burze", f"${current_price:.2f}")
    if margin_of_safety > 0:
        res3.metric("Bezpečnostní polštář", f"{margin_of_safety:.1f} %", "Podhodnoceno")
    else:
        res3.metric("Přirážka", f"{abs(margin_of_safety):.1f} %", "-Nadhodnoceno")

    # Rozložení do tabů pro čistý design
    tab1, tab2 = st.tabs(["📈 Vizualizace Hodnoty", "🧮 Detailní finanční model"])
    
    with tab1:
        st.subheader("Z čeho se skládá hodnota podniku (Enterprise Value)?")
        # Plotly Bar Chart
        fig = go.Figure()
        
        # Přidání FCF za roky 1-5
        for year in years:
            val = dcf_df.at['Současná hodnota UFCF', f'Rok {year}']
            fig.add_trace(go.Bar(name=f'Rok {year}', x=['Složení Hodnoty'], y=[val], marker_color='#1f77b4'))
        
        # Přidání Terminální hodnoty
        fig.add_trace(go.Bar(name='Terminální hodnota', x=['Složení Hodnoty'], y=[pv_terminal_value], marker_color='#2ca02c'))
        
        fig.update_layout(barmode='stack', title="Současná hodnota peněžních toků (v USD)", height=500)
        st.plotly_chart(fig, use_container_width=True)
        
        st.info(f"💡 Povšimněte si, že Terminální hodnota (zelená část) tvoří **{(pv_terminal_value/enterprise_value)*100:.1f} %** celkové hodnoty firmy. To je u DCF modelů naprosto běžné.")

    with tab2:
        st.subheader("Detailní výpočet (v miliardách USD)")
        # Formátování tabulky pro hezké zobrazení v miliardách (kromě diskontního faktoru)
        display_df = dcf_df.copy()
        for col in display_df.columns:
            display_df[col] = pd.to_numeric(display_df[col])
            
        for idx in display_df.index:
            if idx != 'Diskontní faktor':
                display_df.loc[idx] = display_df.loc[idx].apply(lambda x: f"${x/1e9:.2f}")
            else:
                display_df.loc[idx] = display_df.loc[idx].apply(lambda x: f"{x:.3f}")
                
        st.dataframe(display_df, use_container_width=True)
