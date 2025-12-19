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

# --- DATABASE ID SPREADSHEETS (Dari Link yang Anda Berikan) ---
# Dictionary: Nama Moda -> ID Sheet
SUMBER_DATA_MODA = {
    "Pelabuhan": "1xDlyq5bfGaF3wW8rxwGn2NZnrgLvCcxX_fQr6eQAstE",
    "Terminal": "1uvtIjGi9cg1qbEoGKerV0BKXUs0k0pAhdPw0DYPnkfQ",
    "Stasiun": "13We4ZhiN71lsx2t_ErDwkPb5ucBRG_sYemwOKBqCkvw",
    "Bandara": "1G4sUj3XcDOw0EZ4tDhhfNMvg3_4trs2XfxqOEoK4bLo",
    "Rest Area": "1-bFe3hIO1_Fddf-0d0HAj2gMf-SiQu51oPlRoxPt3UI"
}

# ID Sheet Utama (Log Identitas Petugas)
ID_SHEET_UTAMA = "1ym4LXF5qqmaN_NTb4Zsn2SwHP0KsdoYqvbeIw9lQLqI"

# --- KONEKSI GOOGLE SHEETS ---
def connect_to_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "json_mentah" in st.secrets:
            creds_dict = json.loads(st.secrets["json_mentah"])
        elif "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        else:
            st.error("❌ Kunci Rahasia tidak ditemukan!")
            st.stop()

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Gagal login: {e}")
        st.stop()

# --- FUNGSI LOAD DATA GABUNGAN (MODA) ---
@st.cache_data(ttl=10)
def load_traffic_data():
    client = connect_to_sheet()
    all_dfs = []
    
    # Loop membuka setiap Sheet Moda
    for moda, sheet_id in SUMBER_DATA_MODA.items():
        try:
            # Buka sheet berdasarkan ID
            sh = client.open_by_key(sheet_id)
            # Ambil worksheet pertama
            ws = sh.get_worksheet(0)
            data = ws.get_all_values()
            
            if len(data) > 1:
                temp_df = pd.DataFrame(data[1:], columns=data[0])
                # Tandai data ini milik siapa (Penting!)
                temp_df['Jenis Simpul Transportasi'] = moda
                all_dfs.append(temp_df)
                
        except Exception as e:
            # Jika satu sheet error, jangan matikan semua dashboard. Cukup beri peringatan.
            st.warning(f"⚠️ Gagal membaca data {moda}: {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # --- PREPROCESSING ---
        if 'Tanggal Laporan' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'])
        
        # Normalisasi Kolom Angka (Datang/Berangkat/Kendaraan)
        # Kita cari kolom yang mengandung kata 'Datang', 'Berangkat', 'Masuk', 'Keluar'
        cols_numeric = []
        for col in df.columns:
            # Cek jika kolom mengandung angka penumpang atau kendaraan
            if any(x in col.lower() for x in ['jumlah', 'penumpang', 'kendaraan', 'datang', 'berangkat']):
                cols_numeric.append(col)
                # Bersihkan angka
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                
        return df, cols_numeric
    else:
        return pd.DataFrame(), []

# --- FUNGSI LOAD DATA PETUGAS (MAIN LINK) ---
@st.cache_data(ttl=30)
def load_petugas_log():
    try:
        client = connect_to_sheet()
        sh = client.open_by_key(ID_SHEET_UTAMA)
        data = sh.get_worksheet(0).get_all_values()
        if len(data) > 1:
            return pd.DataFrame(data[1:], columns=data[0])
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ================= TAMPILAN DASHBOARD =================

# 1. LOAD DATA
df_traffic, numeric_cols = load_traffic_data()
df_petugas = load_petugas_log()

# 2. HEADER & LOG AKTIVITAS
c_kpi1, c_kpi2, c_kpi3 = st.columns(3)

# Hitung Total (Cari kolom yang relevan secara otomatis)
total_pergerakan = 0
if not df_traffic.empty:
    # Menjumlahkan semua kolom angka yang ditemukan
    total_pergerakan = df_traffic[numeric_cols].sum().sum()

c_kpi1.metric("Total Pergerakan (Semua Moda)", f"{total_pergerakan:,.0f}")
c_kpi2.metric("Jumlah Laporan Masuk", f"{len(df_traffic)} Laporan")
c_kpi3.metric("Status Sistem", "🟢 Online", f"Update: {datetime.now().strftime('%H:%M:%S')}")

# Tampilkan Sekilas Siapa yang Lapor (Dari Link Utama)
with st.expander("📋 Lihat Log Petugas Piket (Data Link Utama)"):
    if not df_petugas.empty:
        st.dataframe(df_petugas.tail(5), hide_index=True, use_container_width=True)
    else:
        st.info("Belum ada data petugas di Link Utama.")

st.markdown("---")

# 3. VISUALISASI PER MODA
if not df_traffic.empty:
    modes = df_traffic['Jenis Simpul Transportasi'].unique()
    
    for mode in modes:
        st.header(f"📍 Laporan: {mode}")
        # Clean column names by removing leading/trailing whitespace
        df_traffic.columns = df_traffic.columns.str.strip()

# OPTIONAL: Debugging line to see the actual column names in your app
# st.write("Available columns:", df_traffic.columns.tolist())
        subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode].sort_values('Tanggal Laporan')
        
        # A. GRAFIK
        # Cari kolom angka spesifik untuk moda ini (karena Rest Area beda dengan Bandara)
        # Kita filter kolom numerik yang nilainya > 0 di subset ini agar grafik relevan
        sort_col = 'Tanggal Laporan'

# Check if the column exists before sorting
        if sort_col in df_traffic.columns:
            subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode].sort_values(sort_col)
        else:
    # Fallback: If column is missing, show an error or just filter without sorting
            st.error(f"Column '{sort_col}' not found. Available columns: {df_traffic.columns.tolist()}")
            subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]

        # B. TABEL KENDALA (Fleksibel mencari kolom kendala)
        # Mencari kolom yang mengandung kata 'Kendala' dan 'Solusi'
        col_kendala = next((c for c in subset.columns if 'kendala' in c.lower()), None)
        col_solusi = next((c for c in subset.columns if 'solusi' in c.lower()), None)
        
        if col_kendala and col_solusi:
            laporan_penting = subset[
                (subset[col_kendala].str.len() > 3) & (subset[col_kendala] != "-")
            ][['Tanggal Laporan', col_kendala, col_solusi]]
            
            if not laporan_penting.empty:
                st.info(f"📢 **Catatan Lapangan ({mode}):**")
                st.dataframe(laporan_penting, hide_index=True, use_container_width=True)
            else:
                st.success("✅ Tidak ada kendala signifikan.")
        
        st.markdown("---")

else:
    st.info("Sedang mengambil data dari 5 Spreadsheet berbeda...")

# Auto Refresh
if st.button("🔄 Refresh Data"):
    st.rerun()

time.sleep(15) # Refresh rate sedikit diperlambat karena membuka 6 sheet sekaligus
st.rerun()
