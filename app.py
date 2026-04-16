import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io

# --- DATE CALCULATION ---
current_date = datetime.now()
emission_date_str = current_date.strftime("%d/%m/%Y")
due_date = current_date + timedelta(days=10)
due_date_str = due_date.strftime("%d/%m/%Y")

# --- CONFIGURATION ---
#WATER_RATE = 2.29
#SEWAGE_RATE = 1.43
#TOTAL_FIXED_FEE_BUILDING = 6.30
TAX_RATE = 0.18 

# URL for the logo
logo_url = "https://manos-vivas.com/wp-content/uploads/2026/03/gwm-logo.jpg"

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
            # Create a dictionary mapping the Month key to its rates and readings
            sedapal_dict = {}
            for _, row in df_sedapal.iterrows():
                mes_key = str(row['Mes']).strip()
                sedapal_dict[mes_key] = {
                    'total_m3': row['Total m3'],
                    'water_rate': row['Agua Costo/m3 S/.'],
                    'sewage_rate': row['Alcantarillado costo/m3 S/.'],
                    'fixed_fee': row['Cargo Fijo']
                }
            return sedapal_dict
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
    """Sorts periods by year desc and month desc using Spanish abbreviations."""
    MONTH_MAP = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12
    }
    
    unique_periods = df_column.unique()
    
    def sort_key(period_str):
        try:
            parts = str(period_str).split()
            if len(parts) == 2:
                month_name = parts[0].upper()
                year = int(parts[1])
                month_num = MONTH_MAP.get(month_name, 0)
                return (year, month_num)
        except (ValueError, IndexError):
            return (0, 0)
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
    own_water_cost = own_consumption_m3 * WATER_RATE
    own_sewage_cost = own_consumption_m3 * SEWAGE_RATE
    own_cost_with_tax = (own_water_cost + own_sewage_cost) * (1 + TAX_RATE)
    
    common_cost = calculate_variable_cost(common_allocation_m3)
    individual_fixed_fee = TOTAL_FIXED_FEE_BUILDING * coef
    
    # Calculations with other variables for now to not screw the current code
    water_cost_common = common_allocation_m3 * WATER_RATE
    sewage_cost_common = common_allocation_m3 * SEWAGE_RATE
    indiv_fixed_fee = TOTAL_FIXED_FEE_BUILDING * coef
    
    common_cost_with_tax = (common_cost + individual_fixed_fee) * (1 + TAX_RATE)
    
    total_billing_m3 = own_consumption_m3 + common_allocation_m3
    variable_cost = (total_billing_m3 * WATER_RATE) + (total_billing_m3 * SEWAGE_RATE)

    monthly_budget = BUDGETS.get(selected_period, 0.0)
    maintenance_fee = monthly_budget * coef

    subtotal_neto = variable_cost + individual_fixed_fee
    tax_amount = subtotal_neto * TAX_RATE
    
    #total_to_pay = subtotal_neto + tax_amount + maintenance_fee
    total_to_pay =  common_cost_with_tax+ own_cost_with_tax + maintenance_fee
    
    invoice_num = f"{selected_period.replace(' ', '')}-{dept}"

    # FIXED: Handling empty owners_html safely to prevent breaking the rendering
    if len(owner_list) > 1:
        owners_html = "".join([f"<div style='margin:0; padding-left:100px;'>{name}</div>" for name in owner_list[1:]])
    else:
        # Use a zero-height container with a non-breaking space to keep HTML valid
        owners_html = "<div style='display:none;'>&nbsp;</div>"
        
    # Note: Using textwrap.dedent logic or avoiding leading spaces is crucial for st.markdown
    receipt_styles = """
<style>
    .receipt-container { 
        font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd; 
        border-radius: 10px; background-color: white; margin-bottom: 30px;
        max-width: 800px; 
        margin-left: auto; margin-right: auto; box-sizing: border-box;
        -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; 
    }
    .header-table { width: 100%; border: none; margin-bottom: 0px; table-layout: fixed; }
    .header-col { vertical-align: middle; }
    .bg-blue { background-color: #00008b !important; color: white !important; }
    .bg-black { background-color: #333 !important; color: white !important; }
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
    .logo-img { max-height: 80px; width: auto; }
    .info-table td { vertical-align: top; padding: 2px 0; }
    .user-code-box { border: 1px solid #333; text-align: center; overflow: hidden; }
    @media print {
        body { margin: 0; padding: 0; }
        .receipt-container { border: none !important; width: 100%; max-width: 100%; page-break-after: always; padding: 10px;}
        tr, td { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    }
</style>
"""

    receipt_body = f"""
<div class="receipt-container">
    <table class="header-table" style="border-radius: 5px 5px 0 0; overflow: hidden;">
        <tr>
            <td class="header-col text-center" style="width: 20%; border: 1px solid #eee;">
                <img src="{logo_url}" class="logo-img" alt="Logo">
            </td>
            <td class="header-col text-center bg-steel" style="width: 55%; padding: 10px 0;">
                <h2 style="margin: 0; font-size: 1.1em; line-height: 1.2; color: white;">
                    JUNTA DE PROPIETARIOS<br>EDIFICIO LA FLORESTA 255
                </h2>
                <p style="margin: 5px 0 0 0; font-weight: bold; color: rgba(255,255,255,0.9); font-size: 0.8em;">
                    Av. De La Floresta Nº 255
                </p>
            </td>
            <td class="header-col text-right invoice-info" style="width: 25%; padding-right: 15px; border: 1px solid #eee;">
                <strong>RECIBO N°</strong><br>{invoice_num}<br><br>
                <strong>EMISIÓN</strong><br>{emission_date_str}
            </td>
        </tr>
    </table>       
    <div style="height: 15px;"></div>
    <table class="info-table" style="width: 100%; font-size: 0.9em; border-collapse: collapse;">
        <tr>
            <td style="width: 75%;">
            <p style="margin:0;"><strong>Departamento:</strong> {dept} | <strong>Periodo:</strong> {selected_period}</p>
            <p style="margin:0;"><strong>Propietario(s):</strong> {owner_list[0]}</p>
            {owners_html}
            <p style="margin:0;"><strong>Coeficiente de Participación:</strong> {coef*100:.2f}%</p>
            </td>
            <td style="width: 25%; vertical-align: middle;">
                <div class="user-code-box">
                    <div class="bg-steel" style="color: white; font-weight: bold; font-size: 0.75em; padding: 4px 0;">
                        <div>CÓDIGO DE</div>
                        <div>USUARIO</div>
                    </div>
                    <div style="font-weight: bold; font-size: 1.1em; letter-spacing: 1px; padding: 5px 0;">FT{dept}</div>
                </div>
            </td>
        </tr>
    </table>
    <hr style="margin: 10px 0;">
    <table style="font-size: 0.9em;">
        <tr class="bg-black"><td>PRESUPUESTO TOTAL DEL MES:</td><td class="text-right p-5">S/. {monthly_budget:.2f}</td></tr>
        <tr class="bg-black"><td colspan="2">CONCEPTOS DE SU CUOTA DEL MES DE {selected_period}</td></tr>
        <tr><td class="p-5 border-b">Cuota de mantenimiento:</td><td class="text-right p-5 border-b">S/. {maintenance_fee:.2f}</td></tr>
        <tr><td class="p-5 border-b">Cuota de Consumo de Agua Propio:</td><td class="text-right p-5 border-b">S/. {own_cost_with_tax:.2f}</td></tr>
        <tr><td class="p-5 border-b">Cuota Áreas Comunes y Fijo (inc. IGV):</td><td class="text-right p-5 border-b">S/. {common_cost_with_tax:.2f}</td></tr>
    </table>
    <br>
    <table style="font-size: 0.9em;">
        <tr class="bg-steel" style="font-weight: bold;"><td class="p-8">CUOTA TOTAL DE MES:</td><td class="text-right p-8">S/. {total_to_pay:.2f}</td></tr>
        <tr class="bg-yellow" style="font-weight: bold;"><td class="p-8">FECHA DE VENCIMIENTO</td><td class="text-right p-8">{due_date_str}</td></tr>
    </table>
    <br>
    <div style="display: flex; gap: 10px;">
        <div style="flex: 1;">
            <table class="border-all" style="font-size: 0.8em;">
                <tr class="bg-black" style="font-weight: bold;"><td colspan="2" style="padding: 5px; text-align: center;">Consumo de Agua (m3)</td></tr>
                <tr><td class="p-5 border-all">Lectura Anterior</td><td class="p-5 border-all text-right">{lectura_anterior:.0f}</td></tr>
                <tr><td class="p-5 border-all">Lectura Actual</td><td class="p-5 border-all text-right">{lectura_actual:.0f}</td></tr>
                <tr><td class="p-5 border-all">Consumo Dpto.</td><td class="p-5 border-all text-right">{own_consumption_m3:.2f}</td></tr>
                <tr><td class="p-5 border-all">Consumo Común</td><td class="p-5 border-all text-right">{common_allocation_m3:.2f}</td></tr>
                <tr style="font-weight: bold; background-color: #f9f9f9 !important;"><td class="p-5 border-all">Total, m3</td><td class="p-5 border-all text-right">{total_billing_m3:.2f}</td></tr>
            </table>
        </div>
        <div style="flex: 1;">
            <table class="border-all" style="font-size: 0.8em;">
                <tr class="bg-gray" style="font-weight: bold;"><td colspan="2" style="padding: 5px; text-align: center;">DEUDA</td></tr>
                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                <tr><td class="p-5 border-all">&nbsp;</td><td class="p-5 border-all text-right">&nbsp;</td></tr>
                <tr style="font-weight: bold; background-color: #f9f9f9 !important;"><td class="p-5 border-all">Total Deuda</td><td class="p-5 border-all text-right">S/. 0.00</td></tr>
            </table>
        </div>
    </div>
      <div style="display: flex; gap: 10px;">
          <div class="bg-steel" style="color: white; font-weight: bold; font-size: 0.75em; padding: 4px 0;">
                        <div>MENSAJE IMPORTANTE</div>
         </div>
         <div>
                       <div> CUENTA BANCARIA, BBVA Ahorros 0011-0132-0200474617<br>
                       CCI 011-132-00-0200474617-84 <br>
                       Cuenta a Nombre de Green World Marketing EIRL <br>
                       RUC 20509450812. <br>
                       Envíe voucher a floresta255@gwm.pe </div>
         </div>
      </div>
</div>
"""
    # --- LÓGICA DE DATOS PARA CSV ---
    # Fórmula solicitada: water_cost_common + sewage_cost_common + indiv_fixed_fee + tax
    subtotal_comunes = water_cost_common + sewage_cost_common + indiv_fixed_fee
    tax_comunes = subtotal_comunes * TAX_RATE
    total_comunes_csv = subtotal_comunes + tax_comunes
    subtotal_propio = own_water_cost + own_sewage_cost
    tax_propio = subtotal_propio * TAX_RATE
    total_propio_csv = subtotal_propio + tax_propio
    grand_total = total_comunes_csv + total_propio_csv
    
    # CSV Data generation for batch reporting
    csv_data = {
        "Dpto": dept,
        "Agua Común (S/.)": round(water_cost_common, 2),
        "Alcantarillado Común (S/.)": round(sewage_cost_common, 2),
        "Cargo Fijo (S/.)": round(indiv_fixed_fee, 2),
        "IGV (S/.)": round(tax_comunes, 2),
        "Total Común": round(total_comunes_csv, 2),
        "Agua Propio (S/.)": round(own_water_cost, 2),
        "Alcantarillado Propio (S/.)": round(own_sewage_cost, 2),
        "IGV (S/.)": round(tax_propio, 2),
        "Total Propio": round(total_propio_csv, 2),
        "Total": round(grand_total, 2)
    }
    
    return receipt_styles, receipt_body, total_to_pay, csv_data
    
# --- MAIN LOGIC ---
df = load_data()
COEFFICIENTS, OWNERS = load_db_info()
BUDGETS = load_budget_info()
SEDAPAL_READINGS = load_sedapal_info()

if not df.empty:
    periods = get_sorted_periods(df['Mes'])
    selected_period = st.selectbox("Periodo (Mes Año)", periods)

    # --- UPDATE GLOBAL RATES BASED ON SELECTED PERIOD ---
    period_data = SEDAPAL_READINGS.get(selected_period, {})
    main_meter_reading = period_data.get('total_m3', 0.0)
    WATER_RATE = period_data.get('water_rate', 2.29)
    SEWAGE_RATE = period_data.get('sewage_rate', 1.43)
    TOTAL_FIXED_FEE_BUILDING = period_data.get('fixed_fee', 6.30)
    
    #main_meter_reading = SEDAPAL_READINGS.get(selected_period, 0.0)
    
    if main_meter_reading == 0.0:
        st.warning(f"No se encontró lectura en la hoja 'Sedapal' para el periodo {selected_period}.")
    else:
        st.info(f"Lectura Medidor General (Sedapal): {main_meter_reading:.2f} m³")

    df_period = df[df['Mes'] == selected_period].copy()
    total_apartments_consumption = (df_period['Consumo'].astype(float).sum()) / 100.0
    common_area_consumption = max(0.0, main_meter_reading - total_apartments_consumption)

    depts_in_period = sorted(df_period['Dpto'].unique())
    options = ["RESUMEN EDIFICIO", "🚀 GENERAR TODO EL EDIFICIO (BATCH)"] + depts_in_period
    selected_dept = st.selectbox("Seleccione Departamento o Resumen", options)

    if selected_dept == "RESUMEN EDIFICIO":
        st.divider()
        st.subheader(f"🏢 Resumen Edificio - {selected_period}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Consumo General", f"{main_meter_reading:.2f} m³")
        c2.metric("Suma Departamentos", f"{total_apartments_consumption:.2f} m³")
        c3.metric("Áreas Comunes", f"{common_area_consumption:.2f} m³")
        st.dataframe(df_period, use_container_width=True)
        
    elif selected_dept == "🚀 GENERAR TODO EL EDIFICIO (BATCH)":
        st.divider()
        st.subheader(f"🚀 Generación Masiva - {selected_period}")
        
        batch_results = []
        csv_rows = []
        full_html_content = ""
        styles = ""
        
        for _, row in df_period.iterrows():
            styles, body, total, c_row = get_receipt_content(row, selected_period, common_area_consumption, COEFFICIENTS, OWNERS, BUDGETS)
            batch_results.append({"Dpto": row['Dpto'], "Total a Pagar": f"S/. {total:.2f}"})
            full_html_content += body
            csv_rows.append(c_row)

        st.table(pd.DataFrame(batch_results))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🖨️ Imprimir Todos los Recibos"):
                escaped_full_body = (styles + full_html_content).replace("`", "\\`").replace("${", "\\${")
                st.components.v1.html(f"""
                    <script>
                    const win = window.open('', '', 'height=700,width=900');
                    win.document.write('<html><head><title>Recibos Edificio {selected_period}</title>');
                    win.document.write('</head><body>');
                    win.document.write(`{escaped_full_body}`);
                    win.document.write('</body></html>');
                    win.document.close();
                    win.setTimeout(function() {{
                        win.focus();
                        win.print();
                        win.close();
                    }}, 1000);
                    </script>
                """, height=0)    
        with col2:
            report_df = pd.DataFrame(csv_rows)
            csv_buffer = io.StringIO()
            report_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="📥 Descargar Reporte CSV de Agua",
                data=csv_buffer.getvalue(),
                file_name=f"Reporte_Agua_{selected_period.replace(' ', '_')}.csv",
                mime="text/csv"
            )
            
    else:
        filtered_df = df_period[df_period['Dpto'] == selected_dept]
        if not filtered_df.empty:
            try:
                row = filtered_df.iloc[0]
                styles, body, total_to_pay, _ = get_receipt_content(row, selected_period, common_area_consumption, COEFFICIENTS, OWNERS, BUDGETS)
                
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("Unidad", selected_dept)
                m2.metric("Periodo", selected_period)
                m3.metric("Total a Pagar", f"S/. {total_to_pay:.2f}")

                with st.expander("Ver detalle del recibo", expanded=True):
                    # Ensure no leading indentation for the strings passed here
                    st.markdown(styles + body, unsafe_allow_html=True)
                    
                    if st.button("🖨️ Imprimir / Guardar PDF"):
                        escaped_body = body.replace("`", "\\`").replace("${", "\\${")
                        escaped_styles = styles.replace("`", "\\`").replace("${", "\\${")
                        
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

st.caption("v3.0 - Fixed HTML rendering in Canvas")
