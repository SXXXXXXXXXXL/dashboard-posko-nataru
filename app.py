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
                
                # Bersihkan spasi di nama kolom
                temp_df.columns = temp_df.columns.str.strip()
                
                # Tambahkan identitas moda
                temp_df['Jenis Simpul Transportasi'] = moda
                all_dfs.append(temp_df)
                
        except Exception as e:
            print(f"Gagal load {moda}: {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # --- 1. PREPROCESSING TANGGAL ---
        # Prioritas: 'Tanggal Laporan Posko' (Manual Input) -> 'Timestamp' (Otomatis)
        if 'Tanggal Laporan Posko' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan Posko'], errors='coerce')
        elif 'Timestamp' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        else:
            # Fallback cari kolom lain
            col_lain = next((c for c in df.columns if 'tanggal' in c.lower() or 'tgl' in c.lower()), None)
            if col_lain:
                df['Tanggal Laporan'] = pd.to_datetime(df[col_lain], errors='coerce')
            else:
                df['Tanggal Laporan'] = pd.to_datetime('today')

        # --- 2. PREPROCESSING ANGKA ---
        # Mencari kolom jumlah penumpang/kendaraan
        cols_numeric = []
        keywords_angka = [
            'jumlah penumpang', 'jumlah kendaraan', 'datang', 'berangkat', 
            'masuk', 'keluar', 'kendaraan', 'penumpang'
        ]
        
        for col in df.columns:
            # Lewatkan kolom yang jelas-jelas bukan angka statistik
            if any(x in col.lower() for x in ['tanggal', 'jam', 'tahun', 'nip', 'nim', 'telepon']):
                continue

            # Cek apakah header mengandung keyword angka
            if any(k in col.lower() for k in keywords_angka):
                cols_numeric.append(col)
                
                # BERSIHKAN FORMAT (Hapus titik, koma, teks "orang", dll)
                # Hanya sisakan digit 0-9
                df[col] = (df[col].astype(str)
                           .str.replace(r'[^\d]', '', regex=True) # Hapus non-digit
                           .replace('', '0')) # Kalau kosong jadi 0
                
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

# 1. HEADER & KPI NASIONAL
c_kpi1, c_kpi2, c_kpi3 = st.columns(3)

total_pergerakan = 0
if not df_traffic.empty and numeric_cols:
    total_pergerakan = df_traffic[numeric_cols].sum().sum()

c_kpi1.metric("Total Pergerakan (Nasional)", f"{total_pergerakan:,.0f}")
c_kpi2.metric("Jumlah Laporan Masuk", f"{len(df_traffic)} Laporan")
c_kpi3.metric("Last Update", f"{datetime.now().strftime('%H:%M:%S')}")

st.markdown("---")

# 2. LOOP PER MODA (Tampilkan Semua Sheet)
for mode in SUMBER_DATA_MODA.keys():
    st.header(f"📍 Laporan: {mode}")
    
    # Filter Data untuk Moda ini
    subset = pd.DataFrame()
    if not df_traffic.empty and 'Jenis Simpul Transportasi' in df_traffic.columns:
        subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]

    # --- JIKA DATA KOSONG ---
    if subset.empty:
        st.warning(f"⚠️ Belum ada data laporan masuk untuk **{mode}**.")
        st.caption("Menunggu input data dari petugas di lapangan.")
        st.markdown("---")
        continue 

    # --- JIKA DATA ADA ---
    # Sort berdasarkan Tanggal Laporan Posko
    if 'Tanggal Laporan' in subset.columns:
        subset = subset.sort_values('Tanggal Laporan')
    
    # A. LINE CHART (GRAFIK GARIS)
    # Ambil kolom numerik yang datanya > 0
    cols_active = [c for c in numeric_cols if c in subset.columns and subset[c].sum() > 0]
    
    if cols_active:
        fig = px.line(
            subset,
            x='Tanggal Laporan',
            y=cols_active,
            markers=True,
            title=f"Tren Pergerakan di {mode}",
            template='seaborn',
            labels={'value': 'Jumlah', 'variable': 'Kategori'}
        )
        fig.update_layout(yaxis_title="Jumlah (Orang/Kendaraan)")
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander(f"📄 Detail Data Angka {mode}"):
            st.dataframe(subset[['Tanggal Laporan'] + cols_active], use_container_width=True)
    else:
        st.info(f"Data masuk untuk {mode}, namun angka pergerakan masih 0.")

    # B. TABEL KENDALA & KEJADIAN PENTING (LOGIKA DIPERBAIKI)
    # Kita cari beberapa kemungkinan nama kolom kendala/kejadian
    target_cols = {
        'kendala': next((c for c in subset.columns if 'kendala' in c.lower()), None),
        'kejadian': next((c for c in subset.columns if 'uraian kejadian' in c.lower()), None),
        'solusi': next((c for c in subset.columns if 'solusi' in c.lower() or 'tindak lanjut' in c.lower()), None)
    }
    
    # Filter baris yang punya isi di kolom Kendala ATAU kolom Kejadian
    # Syarat: Tidak kosong, bukan "-", panjang teks > 3
    mask_kendala = pd.Series([False] * len(subset), index=subset.index)
    mask_kejadian = pd.Series([False] * len(subset), index=subset.index)
    
    if target_cols['kendala']:
        mask_kendala = (subset[target_cols['kendala']].astype(str).str.len() > 3) & (subset[target_cols['kendala']] != "-")
    
    if target_cols['kejadian']:
        mask_kejadian = (subset[target_cols['kejadian']].astype(str).str.len() > 3) & (subset[target_cols['kejadian']] != "-")
        
    # Gabungkan (OR): Tampilkan jika ada kendala ATAU ada kejadian
    laporan_penting = subset[mask_kendala | mask_kejadian]
    
    if not laporan_penting.empty:
        st.error(f"📢 **Catatan Penting / Kendala di {mode}:**")
        
        # Tentukan kolom mana yang mau ditampilkan di tabel
        cols_to_show = ['Tanggal Laporan']
        if target_cols['kendala']: cols_to_show.append(target_cols['kendala'])
        if target_cols['kejadian']: cols_to_show.append(target_cols['kejadian'])
        if target_cols['solusi']: cols_to_show.append(target_cols['solusi'])
        
        st.dataframe(laporan_penting[cols_to_show], hide_index=True, use_container_width=True)
    else:
        st.success("✅ Tidak ada kendala atau kejadian khusus yang dilaporkan.")
    
    st.markdown("---")

if st.button("🔄 Refresh Data"):
    st.rerun()
