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
            st.error("❌ Kunci Rahasia tidak ditemukan!")
            st.stop()

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Gagal login: {e}")
        st.stop()

# --- FUNGSI LOAD DATA GABUNGAN (PERBAIKAN) ---
@st.cache_data(ttl=10)
def load_traffic_data():
    client = connect_to_sheet()
    all_dfs = []
    
    for moda, sheet_id in SUMBER_DATA_MODA.items():
        try:
            sh = client.open_by_key(sheet_id)
            # Coba ambil data, jika sheet kosong lewatkan
            ws = sh.get_worksheet(0)
            data = ws.get_all_values()
            
            if len(data) > 1:
                # Membuat DataFrame
                temp_df = pd.DataFrame(data[1:], columns=data[0])
                
                # Bersihkan spasi di nama kolom (PENTING)
                temp_df.columns = temp_df.columns.str.strip()
                
                # Tandai data
                temp_df['Jenis Simpul Transportasi'] = moda
                all_dfs.append(temp_df)
            else:
                # Jika sheet ada tapi isinya cuma header atau kosong
                print(f"Sheet {moda} kosong atau hanya header.")
                
        except Exception as e:
            # Tampilkan warning di console/log saja agar UI tidak penuh error
            print(f"Gagal load {moda}: {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # --- PREPROCESSING TANGGAL ---
        # Cari kolom tanggal dengan berbagai variasi nama
        col_tanggal = next((c for c in df.columns if c.lower() in ['tanggal laporan', 'tanggal', 'tgl', 'timestamp', 'waktu']), None)
        
        if col_tanggal:
            df['Tanggal Laporan'] = pd.to_datetime(df[col_tanggal], errors='coerce')
        else:
            # Jika tidak ada kolom tanggal, buat dummy agar tidak error
            df['Tanggal Laporan'] = pd.to_datetime('today')

        # --- PREPROCESSING ANGKA (PERBAIKAN UTAMA) ---
        # Mencari kolom yang berpotensi berisi angka
        cols_numeric = []
        keywords_angka = ['jumlah', 'pnp', 'penumpang', 'kendaraan', 'datang', 'berangkat', 'naik', 'turun', 'masuk', 'keluar']
        
        for col in df.columns:
            # Logic: Jika nama kolom mengandung keyword angka
            if any(k in col.lower() for k in keywords_angka):
                cols_numeric.append(col)
                # BERSIHKAN FORMAT: Hapus titik (separator ribuan Indo) lalu convert
                # Contoh: "1.200" -> "1200" -> 1200
                df[col] = (df[col].astype(str)
                           .str.replace('.', '', regex=False)  # Hapus titik ribuan
                           .str.replace(',', '.', regex=False) # Ubah koma jadi titik desimal (jika ada)
                           .str.extract(r'(\d+)', expand=False) # Ambil hanya angkanya
                           .fillna(0))
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df, cols_numeric
    else:
        return pd.DataFrame(), []

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

# 2. DEBUGGER (HANYA MUNCUL JIKA DATA KOSONG)
# Gunakan ini untuk mengecek kenapa Terminal/Rest Area tidak muncul
with st.expander("🛠️ Debug Data (Klik disini jika data hilang)"):
    if not df_traffic.empty:
        st.write("Moda yang berhasil ditarik:", df_traffic['Jenis Simpul Transportasi'].unique())
        st.write("Kolom Numerik Terdeteksi:", numeric_cols)
        st.dataframe(df_traffic.head())
    else:
        st.error("Data Frame Kosong. Cek koneksi atau nama sheet.")

# 3. VISUALISASI PER MODA
if not df_traffic.empty:
    modes = df_traffic['Jenis Simpul Transportasi'].unique()
    
    for mode in modes:
        st.header(f"📍 Laporan: {mode}")
        
        # Filter Data
        subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]
        
        # Sort Data Aman
        if 'Tanggal Laporan' in subset.columns:
            subset = subset.sort_values('Tanggal Laporan')
        
        # --- A. GRAFIK BATANG (BAR CHART) ---
        # Kita cari kolom numerik spesifik yang ada di Moda ini (bukan nol semua)
        cols_active = [c for c in numeric_cols if c in subset.columns and subset[c].sum() > 0]
        
        if cols_active:
            # Tampilkan Grafik
            fig = px.bar(
                subset,
                x='Tanggal Laporan',
                y=cols_active,
                barmode='group',
                title=f"Grafik Pergerakan di {mode}",
                template='seaborn'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tampilkan Tabel Angka
            with st.expander(f"📄 Lihat Data Detail {mode}"):
                st.dataframe(subset[['Tanggal Laporan'] + cols_active], use_container_width=True)
        else:
            st.warning(f"⚠️ Data angka belum terdeteksi untuk {mode}. Cek penulisan header kolom di Google Sheet.")
            st.caption("Pastikan header kolom mengandung kata: 'Jumlah', 'Penumpang', 'Datang', 'Berangkat', atau 'Kendaraan'.")

        # --- B. TABEL KENDALA ---
        col_kendala = next((c for c in subset.columns if 'kendala' in c.lower()), None)
        col_solusi = next((c for c in subset.columns if 'solusi' in c.lower()), None)
        
        if col_kendala:
            laporan_penting = subset[
                (subset[col_kendala].astype(str).str.len() > 3) & (subset[col_kendala] != "-")
            ]
            if not laporan_penting.empty:
                st.info(f"📢 **Catatan Lapangan ({mode}):**")
                cols_to_show = ['Tanggal Laporan', col_kendala]
                if col_solusi: cols_to_show.append(col_solusi)
                st.dataframe(laporan_penting[cols_to_show], hide_index=True, use_container_width=True)
        
        st.markdown("---")

else:
    st.info("⏳ Sedang mengambil data...")

if st.button("🔄 Refresh Data"):
    st.rerun()
