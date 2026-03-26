import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

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

st.set_page_config(page_title="Calculadora de Recibo de Agua", page_icon="💧")

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

df = load_data()
COEFFICIENTS, OWNERS = load_db_info()
BUDGETS = load_budget_info()
SEDAPAL_READINGS = load_sedapal_info()

if not df.empty:
    periods = sorted(df['Mes'].unique(), reverse=True)
    selected_period = st.selectbox("Periodo (Mes Año)", periods)
    main_meter_reading = SEDAPAL_READINGS.get(selected_period, 0.0)
    
    if main_meter_reading == 0.0:
        st.warning(f"No se encontró lectura en la hoja 'Sedapal' para el periodo {selected_period}.")
    else:
        st.info(f"Lectura Medidor General (Sedapal): {main_meter_reading:.2f} m³")

    df_period = df[df['Mes'] == selected_period].copy()
    total_apartments_consumption = (df_period['Consumo'].astype(float).sum()) / 100.0
    common_area_consumption = max(0.0, main_meter_reading - total_apartments_consumption)

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
    else:
        filtered_df = df_period[df_period['Dpto'] == selected_dept]
        if not filtered_df.empty:
            try:
                raw_row = filtered_df.iloc[0]
                own_consumption_m3 = float(raw_row['Consumo']) / 100.0
                lectura_anterior = float(raw_row['Lectura Anterior'])
                lectura_actual = float(raw_row['Lectura Actual'])
            
                coef = COEFFICIENTS.get(selected_dept, 0.05)
                owner_list = OWNERS.get(selected_dept, ["N/A"])
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
                
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("Consumo Propio", f"{own_consumption_m3:.2f} m³")
                m2.metric("Cuota Áreas Comunes", f"{common_allocation_m3:.2f} m³")
                m3.metric("Total a Pagar", f"S/. {total_to_pay:.2f}")

                owners_html = "".join([f"<p style='margin:0; padding-left:100px;'>{name}</p>" for name in owner_list[1:]])

                # Generate a simple receipt number based on period and dept
                invoice_num = f"{selected_period.replace(' ', '')}-{selected_dept}"
                
                # Definimos los estilos CSS por separado para reusarlos
                receipt_styles = """
                <style>
                    .receipt-container { 
                        font-family: Arial, sans-serif; 
                        padding: 20px; 
                        border: 1px solid #ddd; 
                        border-radius: 10px; 
                        background-color: white; 
                        -webkit-print-color-adjust: exact !important; 
                        print-color-adjust: exact !important; 
                    }
                    .header-table { width: 100%; border: none; margin-bottom: 0px; table-layout: fixed; }
                    .header-col { vertical-align: middle; }
                    .bg-blue { background-color: #00008b !important; color: white !important; }
                    .bg-steel { background-color: #4682B4 !important; color: white !important; }
                    .bg-yellow { background-color: #ffb300 !important; color: black !important; }
                    .bg-gray { background-color: #f2f2f2 !important; }
                    table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
                    .text-right { text-align: right; }
                    .text-center { text-align: center; }
                    .p-5 { padding: 5px; }
                    .p-8 { padding: 8px; }
                    .border-b { border-bottom: 1px solid #eee; }
                    .border-all { border: 1px solid #ccc; }
                    .invoice-info { font-size: 0.85em; color: #333; line-height: 1.2; }
                    @media print {
                        .receipt-container { border: none !important; width: 100%; }
                        tr, td { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                    }
                </style>
                """

                # Cuerpo del recibo
                receipt_body = f"""
                <div class="receipt-container">
                    <table class="header-table" style="border-radius: 5px 5px 0 0;">
                        <tr>
                            <td class="header-col text-center" style="width: 25%;">
                                <!-- Logo Placeholder -->
                                <div style="color: #ccc; font-size: 0.7em;">[LOGO]</div>
                            </td>
                            <td class="header-col text-center bg-steel" style="width: 50%; padding: 15px 0;">
                                <h2 style="margin: 0; font-size: 1.1em; line-height: 1.3; color: white; text-align: center;">
                                    JUNTA DE PROPIETARIOS<br>EDIFICIO LA FLORESTA 255
                                </h2>
                            </td>
                            <td class="header-col text-right invoice-info" style="width: 25%; padding-right: 15px;">
                                <strong>RECIBO N°</strong><br>
                                {invoice_num}<br>
                                <strong>EMISIÓN</strong><br>
                                {emission_date_str}
                            </td>
                        </tr>
                    </table>
                    <div class="text-center" style="padding: 5px; border-bottom: 2px solid #4682B4; margin-bottom: 15px;">
                        <p style="margin: 0; font-weight: bold; color: #333; font-size: 0.9em;">Av. De La Floresta Nº 255</p>
                    </div>
                    <p><strong>Departamento:</strong> {selected_dept} | <strong>Periodo:</strong> {selected_period}</p>
                    <p><strong>Propietario(s):</strong> {owner_list[0]}</p>
                    {owners_html}
                    <p><strong>Coeficiente de Participación:</strong> {coef*100:.2f}%</p>
                    <hr>
                    <table>
                        <tr class="bg-blue">
                            <td class="p-5">PRESUPUESTO TOTAL DEL MES:</td>
                            <td class="text-right p-5">S/. {monthly_budget:.2f}</td>
                        </tr>
                        <tr class="bg-blue">
                            <td colspan="2" style="padding: 10px 5px 5px 5px;"><strong>CONCEPTOS DE SU CUOTA DEL MES DE {selected_period}</strong></td>
                        </tr>
                        <tr><td class="p-5 border-b">Cuota de mantenimiento:</td><td class="text-right p-5 border-b">S/. {maintenance_fee:.2f}</td></tr>
                        <tr><td class="p-5 border-b">Cuota de Consumo de Agua Propio:</td><td class="text-right p-5 border-b">S/. {own_cost:.2f}</td></tr>
                        <tr><td class="p-5 border-b">Cuota Áreas Comunes y Fijo (inc. IGV):</td><td class="text-right p-5 border-b">S/. {common_cost_with_tax:.2f}</td></tr>
                    </table>
                    <br>
                    <table>
                        <tr class="bg-blue" style="font-weight: bold;">
                            <td class="p-8">CUOTA TOTAL DE MES:</td>
                            <td class="text-right p-8">S/. {total_to_pay:.2f}</td>
                        </tr>
                        <tr class="bg-yellow" style="font-weight: bold;">
                            <td class="p-8">FECHA DE VENCIMIENTO</td>
                            <td class="text-right p-8">{due_date_str}</td>
                        </tr>
                    </table>
                    <br>
                    <div style="display: flex; gap: 10px;">
                        <div style="flex: 1;">
                            <table class="border-all" style="font-size: 0.85em;">
                                <tr class="bg-blue" style="font-weight: bold;">
                                    <td colspan="2" style="padding: 5px; text-align: center;">Consumo de Agua, Metros Cúbicos</td>
                                </tr>
                                <tr><td class="p-5 border-all">Lectura Contometro (Anterior)</td><td class="p-5 border-all text-right">{lectura_anterior:.0f}</td></tr>
                                <tr><td class="p-5 border-all">Lectura Contometro (Actual)</td><td class="p-5 border-all text-right">{lectura_actual:.0f}</td></tr>
                                <tr><td class="p-5 border-all">Consumo Dpto.</td><td class="p-5 border-all text-right">{own_consumption_m3:.2f}</td></tr>
                                <tr><td class="p-5 border-all">Consumo Común</td><td class="p-5 border-all text-right">{common_allocation_m3:.2f}</td></tr>
                                <tr style="font-weight: bold; background-color: #f9f9f9 !important;"><td class="p-5 border-all">Consumo Total, m3</td><td class="p-5 border-all text-right">{own_consumption_m3 + common_allocation_m3:.2f}</td></tr>
                            </table>
                        </div>
                        <div style="flex: 1;">
                            <table class="border-all" style="font-size: 0.85em;">
                                <tr class="bg-gray" style="font-weight: bold;">
                                    <td colspan="2" style="padding: 5px; text-align: center;">DEUDA</td>
                                </tr>
                                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                                <tr style="font-weight: bold; background-color: #f9f9f9 !important;"><td class="p-5 border-all">Total Deuda</td><td class="p-5 border-all text-right">S/. 0.00</td></tr>
                            </table>
                        </div>
                    </div>
                </div>
                """
            
                with st.expander("Ver detalle del cálculo", expanded=True):
                    # Mostramos el HTML combinado (estilos + cuerpo)
                    st.markdown(receipt_styles + receipt_body, unsafe_allow_html=True)
                    
                    if st.button("🖨️ Imprimir / Guardar PDF"):
                        # Inyectamos directamente el contenido en el script para evitar problemas de búsqueda en el DOM
                        escaped_body = receipt_body.replace("`", "\\`").replace("${", "\\${")
                        escaped_styles = receipt_styles.replace("`", "\\`").replace("${", "\\${")
                        
                        st.components.v1.html(f"""
                            <script>
                            const win = window.open('', '', 'height=700,width=900');
                            win.document.write('<html><head><title>Recibo Dpto {selected_dept}</title>');
                            win.document.write(`{escaped_styles}`);
                            win.document.write('</head><body>');
                            win.document.write(`{escaped_body}`);
                            win.document.write('</body></html>');
                            win.document.close();
                            win.setTimeout(function() {{
                                win.focus();
                                win.print();
                                win.close();
                            }}, 1000);
                            </script>
                        """, height=0)

            except Exception as e:
                st.error(f"Error al procesar el cálculo: {e}")
else:
    st.error("No se pudo cargar la información de consumos.")

st.caption("v2.5 - Fixed Detail Visibility & Direct Print Sync")
