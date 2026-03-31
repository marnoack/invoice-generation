import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import textwrap

# --- DATE CALCULATION ---
current_date = datetime.now()
emission_date_str = current_date.strftime("%d/%m/%Y")
due_date = current_date + timedelta(days=10)
due_date_str = due_date.strftime("%d/%m/%Y")

# --- CONFIGURATION ---
WATER_RATE = 2.29
SEWAGE_RATE = 1.43
TOTAL_FIXED_FEE_BUILDING = 6.30
TAX_RATE = 0.18 

# URL for the logo
logo_url = "https://manos-vivas.com/wp-content/uploads/2026/03/gwm-logo.jpg"

st.set_page_config(page_title="Calculadora de Recibo de Agua", page_icon="💧", layout="wide")

st.title("💧 Generador de Recibo de Dptos")
st.markdown("Cálculo de consumos individuales y áreas comunes.")

# --- DATA CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_db_info():
    try:
        df_db = conn.read(worksheet="DB", ttl="0")
        if df_db is not None and not df_db.empty:
            df_db['Dpto'] = df_db['Dpto'].astype(str).str.replace(r'\.0$', '', regex=True)
            coefs = pd.Series(df_db.Coeficiente.values, index=df_db.Dpto).to_dict()
            owners = {}
            for _, row in df_db.iterrows():
                dpto = str(row['Dpto'])
                names = []
                for col in ['Propietario', 'Propietario 1', 'Propietario 2']:
                    if col in df_db.columns and pd.notna(row[col]) and str(row[col]).strip() != "":
                        names.append(str(row[col]).strip())
                owners[dpto] = names if names else ["N/A"]
            return coefs, owners
    except Exception as e:
        st.sidebar.error(f"Error cargando DB: {e}")
    return {}, {}

@st.cache_data(ttl=300)
def load_budget_info():
    try:
        df_budget = conn.read(worksheet="Presupuesto", ttl="0")
        if df_budget is not None and not df_budget.empty:
            return pd.Series(df_budget.Total.values, index=df_budget.Mes).to_dict()
    except Exception as e:
        st.sidebar.error(f"Error cargando Presupuesto: {e}")
    return {}

@st.cache_data(ttl=300)
def load_sedapal_info():
    try:
        df_sedapal = conn.read(worksheet="Sedapal", ttl="0")
        if df_sedapal is not None and not df_sedapal.empty:
            return pd.Series(df_sedapal['Total m3'].values, index=df_sedapal['Mes']).to_dict()
    except Exception as e:
        st.sidebar.error(f"Error cargando Sedapal: {e}")
    return {}
    
def load_data():
    try:
        df = conn.read(worksheet="Consumos", ttl="0")
        if df is not None:
            if 'Dpto' in df.columns:
                df['Dpto'] = df['Dpto'].astype(str).str.replace(r'\.0$', '', regex=True)
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def calculate_variable_cost(consumption):
    return (consumption * WATER_RATE) + (consumption * SEWAGE_RATE)

def get_sorted_periods(df_column):
    MONTH_MAP = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12
    }
    unique_periods = df_column.unique()
    def sort_key(period_str):
        try:
            parts = str(period_str).split()
            if len(parts) == 2:
                month_num = MONTH_MAP.get(parts[0].upper(), 0)
                return (int(parts[1]), month_num)
        except: return (0, 0)
        return (0, 0)
    return sorted(unique_periods, key=sort_key, reverse=True)

# Reusable receipt template logic
def get_receipt_content(row, selected_period, common_area_consumption, COEFFICIENTS, OWNERS, BUDGETS):
    dept = str(row['Dpto'])
    own_consumption_m3 = float(row['Consumo']) / 100.0
    lectura_anterior = float(row['Lectura Anterior']) / 100.0
    lectura_actual = float(row['Lectura Actual'])  / 100.0

    coef = COEFFICIENTS.get(dept, 0.05)
    owner_list = OWNERS.get(dept, ["N/A"])
    common_allocation_m3 = common_area_consumption * coef
    
    own_cost = calculate_variable_cost(own_consumption_m3)
    common_cost = calculate_variable_cost(common_allocation_m3)
    individual_fixed_fee = TOTAL_FIXED_FEE_BUILDING * coef
    common_cost_with_tax = (common_cost + individual_fixed_fee) * (1 + TAX_RATE)
    
    total_billing_m3 = own_consumption_m3 + common_allocation_m3
    variable_cost = (total_billing_m3 * WATER_RATE) + (total_billing_m3 * SEWAGE_RATE)

    monthly_budget = BUDGETS.get(selected_period, 0.0)
    maintenance_fee = monthly_budget * coef

    subtotal_neto = variable_cost + individual_fixed_fee
    tax_amount = subtotal_neto * TAX_RATE
    total_to_pay = subtotal_neto + tax_amount + maintenance_fee
    
    invoice_num = f"{selected_period.replace(' ', '')}-{dept}"
    owners_html = "".join([f"<p style='margin:0; padding-left:100px;'>{name}</p>" for name in owner_list[1:]])

    receipt_styles = """
    <style>
        .receipt-container { 
            font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; 
            border-radius: 10px; background-color: white; margin-bottom: 30px;
            max-width: 800px; margin-left: auto; margin-right: auto; color: #333;
        }
        .bg-steel { background-color: #4682B4 !important; color: white !important; }
        .bg-black { background-color: #333 !important; color: white !important; }
        .bg-yellow { background-color: #ffb300 !important; color: black !important; }
        .bg-gray { background-color: #f2f2f2 !important; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .border-b { border-bottom: 1px solid #eee; }
        .border-all { border: 1px solid #ccc; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 10px; color: inherit; }
    </style>
    """

    receipt_body = f"""
    <div class="receipt-container">
        <table style="width: 100%;">
            <tr>
                <td class="text-center" style="width: 20%; border: 1px solid #eee;"><img src="{logo_url}" style="max-height: 80px;"></td>
                <td class="text-center bg-steel" style="width: 55%;">
                    <h2 style="margin: 0; font-size: 1.1em; color: white;">JUNTA DE PROPIETARIOS<br>EDIFICIO LA FLORESTA 255</h2>
                </td>
                <td class="text-right" style="width: 25%; font-size: 0.8em; padding-right: 10px; border: 1px solid #eee;">
                    <strong>RECIBO N°</strong><br>{invoice_num}<br><strong>EMISIÓN</strong><br>{emission_date_str}
                </td>
            </tr>
        </table>
        <div style="margin-top:15px; font-size: 0.9em;">
            <p style="margin:0;"><strong>Departamento:</strong> {dept} | <strong>Periodo:</strong> {selected_period}</p>
            <p style="margin:0;"><strong>Propietario(s):</strong> {owner_list[0]}</p>
            {owners_html}
            <p style="margin:0;"><strong>Coeficiente:</strong> {coef*100:.2f}% | <strong>Código:</strong> FT{dept}</p>
        </div>
        <hr>
        <table style="font-size: 0.9em;">
            <tr class="bg-black"><td style="padding:5px;">CONCEPTO</td><td class="text-right" style="padding:5px;">IMPORTE</td></tr>
            <tr><td class="border-b">Cuota mantenimiento:</td><td class="text-right border-b">S/. {maintenance_fee:.2f}</td></tr>
            <tr><td class="border-b">Consumo Agua Propio:</td><td class="text-right border-b">S/. {own_cost:.2f}</td></tr>
            <tr><td class="border-b">Áreas Comunes + Fijo (inc. IGV):</td><td class="text-right border-b">S/. {common_cost_with_tax:.2f}</td></tr>
            <tr class="bg-steel" style="font-weight: bold;"><td>TOTAL MES:</td><td class="text-right">S/. {total_to_pay:.2f}</td></tr>
            <tr class="bg-yellow"><td>VENCIMIENTO:</td><td class="text-right">{due_date_str}</td></tr>
        </table>
        <div style="display: flex; gap: 10px; margin-top: 10px;">
            <table class="border-all" style="font-size: 0.75em; flex: 1;">
                <tr class="bg-black text-center"><td colspan="2">Consumo m3</td></tr>
                <tr><td>Lectura Ant.</td><td class="text-right">{lectura_anterior:.0f}</td></tr>
                <tr><td>Lectura Act.</td><td class="text-right">{lectura_actual:.0f}</td></tr>
                <tr><td>Total m3</td><td class="text-right">{total_billing_m3:.2f}</td></tr>
            </table>
            <table class="border-all" style="font-size: 0.75em; flex: 1;">
                <tr class="bg-gray text-center"><td colspan="2">Estado de Deuda</td></tr>
                <tr><td>Meses Pend.</td><td class="text-right">0</td></tr>
                <tr><td>Total Deuda</td><td class="text-right">S/. 0.00</td></tr>
            </table>
        </div>
    </div>
    """
    return receipt_styles, receipt_body, total_to_pay
    
# --- MAIN LOGIC ---
df = load_data()
COEFFICIENTS, OWNERS = load_db_info()
BUDGETS = load_budget_info()
SEDAPAL_READINGS = load_sedapal_info()

if not df.empty:
    periods = get_sorted_periods(df['Mes'])
    selected_period = st.selectbox("Periodo (Mes Año)", periods)
    main_meter_reading = SEDAPAL_READINGS.get(selected_period, 0.0)
    
    df_period = df[df['Mes'] == selected_period].copy()
    total_apartments_consumption = (df_period['Consumo'].astype(float).sum()) / 100.0
    common_area_consumption = max(0.0, main_meter_reading - total_apartments_consumption)

    options = ["RESUMEN EDIFICIO", "🚀 GENERAR TODO EL EDIFICIO (BATCH)"] + sorted(df_period['Dpto'].unique())
    selected_dept = st.selectbox("Seleccione Departamento o Resumen", options)

    if selected_dept == "RESUMEN EDIFICIO":
        st.subheader(f"🏢 Resumen - {selected_period}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Medidor General", f"{main_meter_reading:.2f} m³")
        c2.metric("Suma Dptos", f"{total_apartments_consumption:.2f} m³")
        c3.metric("Áreas Comunes", f"{common_area_consumption:.2f} m³")
        st.dataframe(df_period)
        
    elif selected_dept == "🚀 GENERAR TODO EL EDIFICIO (BATCH)":
        full_html = ""
        styles = ""
        for _, row in df_period.iterrows():
            s, b, _ = get_receipt_content(row, selected_period, common_area_consumption, COEFFICIENTS, OWNERS, BUDGETS)
            styles = s
            full_html += b
        
        st.markdown(styles, unsafe_allow_html=True)
        st.markdown(full_html, unsafe_allow_html=True)
        
        if st.button("🖨️ Imprimir Todo"):
            st.components.v1.html(f"<script>const w=window.open(); w.document.write(`{styles}{full_html}`); w.print(); w.close();</script>", height=0)
            
    else:
        row = df_period[df_period['Dpto'] == selected_dept].iloc[0]
        styles, body, total = get_receipt_content(row, selected_period, common_area_consumption, COEFFICIENTS, OWNERS, BUDGETS)
        
        st.markdown(styles, unsafe_allow_html=True)
        st.markdown(body, unsafe_allow_html=True)
        
        if st.button("🖨️ Imprimir Recibo"):
            st.components.v1.html(f"<script>const w=window.open(); w.document.write(`{styles}{body}`); w.print(); w.close();</script>", height=0)

else:
    st.error("No se pudo cargar la información.")
