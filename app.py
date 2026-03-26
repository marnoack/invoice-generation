import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- CONFIGURATION ---
# Fixed Rates (per m3)
#WATER_RATE = 2.28684864
#SEWAGE_RATE = 1.4342
WATER_RATE = 2.29
SEWAGE_RATE = 1.43


# Updated Fees
TOTAL_FIXED_FEE_BUILDING = 6.30
TAX_RATE = 0.18 # 18% IGV

st.set_page_config(page_title="Calculadora de Recibo de Agua", page_icon="💧")

st.title("💧 Generador de Recibo de Dptos")
st.markdown("Cálculo de consumos individuales y áreas comunes.")

# --- DATA CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_db_info():
    """Reads ownership coefficients and multiple owner names from the 'DB' worksheet."""
    try:
        df_db = conn.read(worksheet="DB", ttl="0")
        if df_db is not None and not df_db.empty:
            # Ensure Dpto is string and clean it
            df_db['Dpto'] = df_db['Dpto'].astype(str).str.replace(r'\.0$', '', regex=True)
            
            # Create dictionary mapping Dpto -> Coeficiente
            coefs = pd.Series(df_db.Coeficiente.values, index=df_db.Dpto).to_dict()
            
            # Create dictionary mapping Dpto -> Formatted Owners String
            owners = {}
            for _, row in df_db.iterrows():
                dpto = str(row['Dpto'])
                names = []
                # Check for multiple owner columns (e.g., Propietario, Propietario 1, Propietario 2)
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
    """Reads the budget from the 'Presupuesto' worksheet."""
    try:
        df_budget = conn.read(worksheet="Presupuesto", ttl="0")
        if df_budget is not None and not df_budget.empty:
            # Create dictionary mapping Mes -> Total
            return pd.Series(df_budget.Total.values, index=df_budget.Mes).to_dict()
    except Exception as e:
        st.sidebar.error(f"Error cargando Presupuesto: {e}")
    return {}

@st.cache_data(ttl=300)
def load_sedapal_info():
    """Reads the general meter reading from the 'Sedapal' worksheet."""
    try:
        df_sedapal = conn.read(worksheet="Sedapal", ttl="0")
        if df_sedapal is not None and not df_sedapal.empty:
            # Create dictionary mapping Mes (e.g. 'Ene 2024') -> Total m3
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
    """Calculates the combined water and sewage cost based on total consumption."""
    water_cost = consumption * WATER_RATE
    sewage_cost = consumption * SEWAGE_RATE
    return water_cost + sewage_cost

df = load_data()
COEFFICIENTS, OWNERS = load_db_info()
BUDGETS = load_budget_info()
SEDAPAL_READINGS = load_sedapal_info()

if not df.empty:
    # --- FILTERS ---
    periods = sorted(df['Mes'].unique(), reverse=True)
    selected_period = st.selectbox("Periodo (Mes Año)", periods)
    
    # Automatically get main meter reading from Sedapal sheet
    main_meter_reading = SEDAPAL_READINGS.get(selected_period, 0.0)
    
    if main_meter_reading == 0.0:
        st.warning(f"No se encontró lectura en la hoja 'Sedapal' para el periodo {selected_period}. Se usará 0.0 m³.")
    else:
        st.info(f"Lectura Medidor General (Sedapal): {main_meter_reading:.2f} m³")

    # Pre-process period data
    df_period = df[df['Mes'] == selected_period].copy()
    
    # Calculate totals for the building to determine common areas
    total_apartments_consumption = (df_period['Consumo'].astype(float).sum()) / 100.0
    common_area_consumption = max(0.0, main_meter_reading - total_apartments_consumption)

    # Selection
    depts_in_period = sorted(df_period['Dpto'].unique())
    options = ["RESUMEN EDIFICIO"] + depts_in_period
    selected_dept = st.selectbox("Seleccione Departamento o Resumen", options)

    if selected_dept == "RESUMEN EDIFICIO":
        st.divider()
        st.subheader(f"🏢 Resumen Edificio - {selected_period}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Consumo General", f"{main_meter_reading:.2f} m³")
        c2.metric("Suma Departamentos", f"{total_apartments_consumption:.2f} m³")
        c3.metric("Áreas Comunes", f"{common_area_consumption:.2f} m³")

        with st.expander("Ver detalle de costos del edificio"):
            total_var_cost = sum([calculate_variable_cost(float(r)/100.0) for r in df_period['Consumo']])
            st.write(f"**Costo Variable Total (Agua + Desagüe):** S/. {total_var_cost:.2f}")
            st.write(f"**Cargo Fijo Total Edificio:** S/. {TOTAL_FIXED_FEE_BUILDING:.2f}")
            st.info(f"El cargo fijo y el consumo de áreas comunes se distribuyen según el coeficiente de cada departamento.")
            
    else:
        # --- INDIVIDUAL CALCULATION ---
        filtered_df = df_period[df_period['Dpto'] == selected_dept]

        if not filtered_df.empty:
            try:
                # 1. Individual Consumption
                raw_consumption = float(filtered_df.iloc[0]['Consumo'])
                own_consumption_m3 = raw_consumption / 100.0
                
                # 2. Common Area Allocation
                coef = COEFFICIENTS.get(selected_dept, 0.05) # Default to 5% if not found
                owner_list = OWNERS.get(selected_dept, ["N/A"])
                common_allocation_m3 = common_area_consumption * coef
                
                # 3. Total Billing Consumption
                total_billing_m3 = own_consumption_m3 + common_allocation_m3
                
                # 4. Costs
                own_cost = calculate_variable_cost(own_consumption_m3)
                common_cost = calculate_variable_cost(common_allocation_m3)

                # 5. Fixed Fee divided by coefficient
                individual_fixed_fee = TOTAL_FIXED_FEE_BUILDING * coef
                
                # Apply tax to the common cost as requested (18%)
                common_cost_with_tax = common_cost * (1 + TAX_RATE) +  individual_fixed_fee * (1 + TAX_RATE)
                
                water_component = total_billing_m3 * WATER_RATE
                sewage_component = total_billing_m3 * SEWAGE_RATE
                variable_cost = water_component + sewage_component

                # 6. Budget for the month
                monthly_budget = BUDGETS.get(selected_period, 0.0)
                
                # 7. Cuota de mantenimiento calculation
                maintenance_fee = monthly_budget * coef

                # 8. Totals (Subtotal + Tax + Maintenance Fee)
                subtotal_neto = variable_cost + individual_fixed_fee
                tax_amount = subtotal_neto * TAX_RATE
                total_to_pay = subtotal_neto + tax_amount + maintenance_fee
                #total_to_pay = common_cost_with_tax + maintenance_fee
                
                st.divider()
                st.subheader(f"Recibo: Dpto {selected_dept} - {selected_period}")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Consumo Propio", f"{own_consumption_m3:.2f} m³")
                m2.metric("Cuota Áreas Comunes", f"{common_allocation_m3:.2f} m³")
                m3.metric("Total a Pagar", f"S/. {total_to_pay:.2f}")

                # Create the HTML content for printing
                owners_html = "".join([f"<p style='margin:0; padding-left:100px;'>{name}</p>" for name in owner_list[1:]])
                receipt_html = f"""
                <div id="receipt-content" style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <h2 style="text-align: center; color: #1f4e79;">RECIBO DE AGUA - LA FLORESTA 255</h2>
                    <hr>
                    <p><strong>Departamento:</strong> {selected_dept} | <strong>Periodo:</strong> {selected_period}</p>
                    <p><strong>Propietario(s):</strong> {owner_list[0]}</p>
                    {owners_html}
                    <p><strong>Coeficiente de Participación:</strong> {coef*100:.2f}%</p>
                    <hr>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td>Presupuesto total del mes:</td><td style="text-align: right;">S/. {monthly_budget:.2f}</td></tr>
                        <tr><td colspan="2" style="padding-top:10px;"><strong>Conceptos de su Cuota del mes de {selected_period}</strong></td></tr>
                        <tr><td>Cuota de mantenimiento:</td><td style="text-align: right;">S/. {maintenance_fee:.2f}</td></tr>
                        <tr><td>Cuota de Consumo de Agua Propio:</td><td style="text-align: right;">S/. {own_cost:.2f}</td></tr>
                        <tr><td>Cuota Áreas Comunes y Fijo (inc. IGV):</td><td style="text-align: right;">S/. {common_cost_with_tax:.2f}</td></tr>
                    </table>
                    <br>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr style="font-weight: bold; border-bottom: 1px dotted #ccc;">
                            <td style="padding: 10px 0;">Consumo Total Facturable:</td>
                            <td style="text-align: right; padding: 10px 0;">{total_billing_m3:.2f} m³</td>
                        </tr>
                        <tr style="font-weight: bold; font-size: 1.2em; border-top: 2px solid #000;">
                            <td style="padding-top: 15px;">TOTAL A PAGAR:</td>
                            <td style="text-align: right; padding-top: 15px;">S/. {total_to_pay:.2f}</td>
                        </tr>
                    </table>
                </div>
                """

                with st.expander("Ver detalle del cálculo (Consumo + Comunes + IGV)", expanded=True):
                    st.markdown(receipt_html, unsafe_allow_html=True)
                    
                    # Print button using JavaScript
                    if st.button("🖨️ Imprimir / Guardar PDF"):
                        st.components.v1.html(f"""
                            <script>
                            const printContent = document.getElementById('receipt-content');
                            const win = window.open('', '', 'height=700,width=900');
                            win.document.write('<html><head><title>Recibo Dpto {selected_dept}</title>');
                            win.document.write('</head><body>');
                            win.document.write(window.parent.document.getElementById('receipt-content').innerHTML);
                            win.document.write('</body></html>');
                            win.document.close();
                            win.print();
                            </script>
                        """, height=0)

            except Exception as e:
                st.error(f"Error al procesar el cálculo: {e}")
else:
    st.error("No se pudo cargar la información de consumos.")

st.caption("v2.2 - Sincronizado con Lectura Sedapal y Cuota de Mantenimiento")
