import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import time
import json
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Dashboard Posko Nataru", page_icon="🚌", layout="wide")
st.title("📊 Dashboard Monitoring Posko Nataru 2025/2026")

# --- KONEKSI SANGAT AMAN (ANTI ERROR PADDING) ---
def connect_to_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. Kita ambil data mentah JSON dari secrets
    # Pastikan nama di secrets nanti adalah "json_mentah"
    try:
        json_str = st.secrets["json_mentah"]
        # Parse text string menjadi Dictionary Python yang valid
        creds_dict = json.loads(json_str)
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Gagal memproses Credentials: {e}")
        st.stop()

# --- FUNGSI LOAD DATA ---
@st.cache_data(ttl=10)
def load_data():
    try:
        client = connect_to_sheet()
        # ID Spreadsheet Anda
        sheet_id = '1IOOY8nR4UbNUB77pelUoYYYYByp9PBApl_A5BqYu-3U'
        
        sheet = client.open_by_key(sheet_id)
        # Menggunakan get_all_values agar aman dari duplikat header
        all_data = sheet.get_worksheet(0).get_all_values()
        
        if len(all_data) < 2:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        
        # Preprocessing
        df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'])
        cols_num = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"Terjadi kesalahan saat menarik data: {e}")
        return pd.DataFrame()

# --- TAMPILAN DASHBOARD ---
df = load_data()

if not df.empty:
    # KPI
    total_datang = df['Jumlah Penumpang Datang'].sum() if 'Jumlah Penumpang Datang' in df.columns else 0
    total_berangkat = df['Jumlah Penumpang BERANGKAT'].sum() if 'Jumlah Penumpang BERANGKAT' in df.columns else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Penumpang Datang", f"{total_datang:,.0f}")
    c2.metric("Penumpang Berangkat", f"{total_berangkat:,.0f}")
    c3.metric("Status", "🟢 Online")
    
    st.markdown("---")
    
    # Grafik
    if 'Jenis Simpul Transportasi' in df.columns:
        modes = df['Jenis Simpul Transportasi'].unique()
        cols = st.columns(2)
        
        # Siapkan data melt
        cols_target = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
        df_melt = df.melt(id_vars=['Tanggal Laporan', 'Jenis Simpul Transportasi'], 
                          value_vars=[c for c in cols_target if c in df.columns],
                          var_name='Status', value_name='Jumlah')
        
        for i, mode in enumerate(modes):
            with cols[i % 2]:
                subset = df_melt[df_melt['Jenis Simpul Transportasi'] == mode].sort_values('Tanggal Laporan')
                fig = px.line(subset, x='Tanggal Laporan', y='Jumlah', color='Status', 
                              title=f"{mode}", markers=True, template='plotly_white')
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Kolom 'Jenis Simpul Transportasi' tidak ditemukan.")

    if st.button("Refresh Data"):
        st.rerun()
else:
    st.info("Menunggu data... atau gagal terhubung.")

time.sleep(10)
st.rerun()
