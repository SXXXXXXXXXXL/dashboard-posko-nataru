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

# --- DATABASE ID SPREADSHEETS ---
SUMBER_DATA_MODA = {
    "Pelabuhan": "1xDlyq5bfGaF3wW8rxwGn2NZnrgLvCcxX_fQr6eQAstE",
    "Terminal": "1uvtIjGi9cg1qbEoGKerV0BKXUs0k0pAhdPw0DYPnkfQ",
    "Stasiun": "13We4ZhiN71lsx2t_ErDwkPb5ucBRG_sYemwOKBqCkvw",
    "Bandara": "1G4sUj3XcDOw0EZ4tDhhfNMvg3_4trs2XfxqOEoK4bLo",
    "Rest Area": "1-bFe3hIO1_Fddf-0d0HAj2gMf-SiQu51oPlRoxPt3UI"
}

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
            st.error("❌ Kunci Rahasia (Secrets) tidak ditemukan!")
            st.stop()

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Gagal login ke Google Sheets: {e}")
        st.stop()

# --- FUNGSI LOAD DATA GABUNGAN ---
@st.cache_data(ttl=10)
def load_traffic_data():
    client = connect_to_sheet()
    all_dfs = []
    
    for moda, sheet_id in SUMBER_DATA_MODA.items():
        try:
            sh = client.open_by_key(sheet_id)
            ws = sh.get_worksheet(0)
            data = ws.get_all_values()
            
            if len(data) > 1:
                temp_df = pd.DataFrame(data[1:], columns=data[0])
                temp_df.columns = temp_df.columns.str.strip()
                temp_df['Jenis Simpul Transportasi'] = moda
                all_dfs.append(temp_df)
                
        except Exception as e:
            print(f"Gagal load {moda}: {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # --- PREPROCESSING TANGGAL ---
        col_tanggal = next((c for c in df.columns if c.lower() in ['tanggal laporan', 'tanggal', 'tgl', 'timestamp', 'waktu']), None)
        if col_tanggal:
            df['Tanggal Laporan'] = pd.to_datetime(df[col_tanggal], errors='coerce')
        else:
            df['Tanggal Laporan'] = pd.to_datetime('today')

        # --- PREPROCESSING ANGKA (SOLUSI FORMAT KOMA/TITIK) ---
        cols_numeric = []
        keywords_angka = ['jumlah', 'pnp', 'penumpang', 'kendaraan', 'datang', 'berangkat', 'naik', 'turun', 'masuk', 'keluar']
        
        for col in df.columns:
            if any(k in col.lower() for k in keywords_angka):
                cols_numeric.append(col)
                
                # --- LOGIKA BARU: HAPUS SEMUA YANG BUKAN ANGKA ---
                # Regex r'[^\d]' artinya: Hapus apa saja yang BUKAN digit (0-9).
                # Jadi "," atau "." atau " orang" akan hilang semua.
                # "10,362" -> "10362"
                # "10.362" -> "10362"
                df[col] = (df[col].astype(str)
                           .str.replace(r'[^\d]', '', regex=True)
                           .replace('', '0')) # Jika kosong jadi 0
                
                # Convert ke angka
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df, cols_numeric
    else:
        return pd.DataFrame(columns=['Jenis Simpul Transportasi', 'Tanggal Laporan']), []

# --- FUNGSI LOAD DATA PETUGAS ---
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

# Load Data
df_traffic, numeric_cols = load_traffic_data()
df_petugas = load_petugas_log()

# 1. HEADER & KPI
c_kpi1, c_kpi2, c_kpi3 = st.columns(3)

total_pergerakan = 0
if not df_traffic.empty and numeric_cols:
    total_pergerakan = df_traffic[numeric_cols].sum().sum()

c_kpi1.metric("Total Pergerakan (Nasional)", f"{total_pergerakan:,.0f}")
c_kpi2.metric("Jumlah Laporan Masuk", f"{len(df_traffic)} Laporan")
c_kpi3.metric("Last Update", f"{datetime.now().strftime('%H:%M:%S')}")

st.markdown("---")

# 2. VISUALISASI PER MODA (Tampilkan Semua walau Kosong)
for mode in SUMBER_DATA_MODA.keys():
    st.header(f"📍 Laporan: {mode}")
    
    # Filter Data
    subset = pd.DataFrame()
    if not df_traffic.empty and 'Jenis Simpul Transportasi' in df_traffic.columns:
        subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]

    # --- JIKA DATA KOSONG ---
    if subset.empty:
        st.warning(f"⚠️ Belum ada data laporan masuk untuk **{mode}**.")
        st.caption("Petugas di lapangan belum menginput data atau sheet masih kosong.")
        st.markdown("---")
        continue 

    # --- JIKA DATA ADA ---
    # Sort Data
    if 'Tanggal Laporan' in subset.columns:
        subset = subset.sort_values('Tanggal Laporan')
    
    # A. LINE CHART (GRAFIK GARIS)
    cols_active = [c for c in numeric_cols if c in subset.columns and subset[c].sum() > 0]
    
    if cols_active:
        fig = px.line(
            subset,
            x='Tanggal Laporan',
            y=cols_active,
            markers=True,
            title=f"Tren Pergerakan di {mode}",
            template='seaborn'
        )
        fig.update_layout(yaxis_title="Jumlah (Orang/Kendaraan)")
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander(f"📄 Detail Data Angka {mode}"):
            st.dataframe(subset[['Tanggal Laporan'] + cols_active], use_container_width=True)
    else:
        st.info(f"Data masuk untuk {mode}, namun belum ada angka pergerakan (Nol).")

    # B. TABEL KENDALA
    col_kendala = next((c for c in subset.columns if 'kendala' in c.lower()), None)
    col_solusi = next((c for c in subset.columns if 'solusi' in c.lower()), None)
    
    if col_kendala:
        laporan_penting = subset[
            (subset[col_kendala].astype(str).str.len() > 3) & (subset[col_kendala] != "-")
        ]
        if not laporan_penting.empty:
            st.error(f"📢 **Kendala Dilaporkan ({mode}):**")
            cols_to_show = ['Tanggal Laporan', col_kendala]
            if col_solusi: cols_to_show.append(col_solusi)
            st.dataframe(laporan_penting[cols_to_show], hide_index=True, use_container_width=True)
    
    st.markdown("---")

if st.button("🔄 Refresh Data"):
    st.rerun()
