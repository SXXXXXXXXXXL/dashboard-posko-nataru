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
# ttl=10 artinya cache data akan kadaluarsa dalam 10 detik
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
            # Silent error agar loop tetap jalan
            print(f"Gagal load {moda}: {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # --- PREPROCESSING TANGGAL ---
        if 'Tanggal Laporan Posko' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan Posko'], errors='coerce')
        elif 'Timestamp' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        else:
            col_lain = next((c for c in df.columns if 'tanggal' in c.lower() or 'tgl' in c.lower()), None)
            df['Tanggal Laporan'] = pd.to_datetime(df[col_lain], errors='coerce') if col_lain else pd.to_datetime('today')

        # --- PREPROCESSING ANGKA ---
        cols_numeric = []
        keywords_angka = ['jumlah penumpang', 'jumlah kendaraan', 'datang', 'berangkat', 'masuk', 'keluar', 'kendaraan', 'penumpang']
        
        for col in df.columns:
            if any(x in col.lower() for x in ['tanggal', 'jam', 'tahun', 'nip', 'nim', 'telepon']):
                continue
            if any(k in col.lower() for k in keywords_angka):
                cols_numeric.append(col)
                df[col] = (df[col].astype(str).str.replace(r'[^\d]', '', regex=True).replace('', '0'))
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

df_traffic, numeric_cols = load_traffic_data()
df_petugas = load_petugas_log()

# KPI GLOBAL
c1, c2, c3 = st.columns(3)
total_pergerakan = df_traffic[numeric_cols].sum().sum() if not df_traffic.empty and numeric_cols else 0
c1.metric("Total Pergerakan (Nasional)", f"{total_pergerakan:,.0f}")
c2.metric("Total Laporan Masuk", f"{len(df_traffic)} Laporan")

# Tampilkan waktu update + Info Auto Reload
with c3:
    st.metric("Last Update", datetime.now().strftime('%H:%M:%S'))
    st.caption("🔄 Auto-refresh setiap 10 detik")

st.markdown("---")

# --- MEMBUAT TABS ---
tab_trafik, tab_kepadatan = st.tabs(["📊 Trafik & Pergerakan", "🚦 Situasi & Kepadatan (%)"])

# ================= TAB 1: TRAFIK (Line Chart) =================
with tab_trafik:
    st.subheader("Analisis Tren Jumlah Penumpang & Kendaraan")
    
    for mode in SUMBER_DATA_MODA.keys():
        with st.expander(f"📍 Laporan: {mode}", expanded=True):
            subset = pd.DataFrame()
            if not df_traffic.empty and 'Jenis Simpul Transportasi' in df_traffic.columns:
                subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]

            if subset.empty:
                st.warning(f"⚠️ Belum ada data laporan untuk **{mode}**.")
                continue 

            if 'Tanggal Laporan' in subset.columns:
                subset = subset.sort_values('Tanggal Laporan')
            
            # A. LINE CHART
            cols_active = [c for c in numeric_cols if c in subset.columns and subset[c].sum() > 0]
            
            if cols_active:
                fig = px.line(subset, x='Tanggal Laporan', y=cols_active, markers=True, title=f"Tren di {mode}", template='seaborn')
                fig.update_layout(yaxis_title="Jumlah")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"Data masuk untuk {mode}, namun angka pergerakan 0.")

            # B. KENDALA
            target_cols = {
                'kendala': next((c for c in subset.columns if 'kendala' in c.lower()), None),
                'kejadian': next((c for c in subset.columns if 'uraian kejadian' in c.lower()), None),
                'solusi': next((c for c in subset.columns if 'solusi' in c.lower() or 'tindak lanjut' in c.lower()), None)
            }
            
            mask_kendala = (subset[target_cols['kendala']].astype(str).str.len() > 3) & (subset[target_cols['kendala']] != "-") if target_cols['kendala'] else False
            mask_kejadian = (subset[target_cols['kejadian']].astype(str).str.len() > 3) & (subset[target_cols['kejadian']] != "-") if target_cols['kejadian'] else False
            
            # Fix: Pastikan mask berupa Series boolean, bukan scalar boolean
            if isinstance(mask_kendala, bool): mask_kendala = pd.Series([False]*len(subset), index=subset.index)
            if isinstance(mask_kejadian, bool): mask_kejadian = pd.Series([False]*len(subset), index=subset.index)

            laporan_penting = subset[mask_kendala | mask_kejadian]
            
            if not laporan_penting.empty:
                st.error(f"📢 **Catatan / Kendala ({mode}):**")
                cols_show = ['Tanggal Laporan'] + [v for k,v in target_cols.items() if v]
                st.dataframe(laporan_penting[cols_show], hide_index=True, use_container_width=True)

# ================= TAB 2: KEPADATAN (Persentase) =================
with tab_kepadatan:
    st.subheader("Tingkat Kepadatan (% Okupansi)")
    st.caption("Konversi Situasi: Normal ≤20%, Ramai ≤45%, Padat ≤75%, Sangat Padat ≤95%")

    for mode in SUMBER_DATA_MODA.keys():
        st.markdown(f"### 📍 {mode}")
        
        subset = pd.DataFrame()
        if not df_traffic.empty:
            subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]
        
        if subset.empty:
            st.info(f"Belum ada data untuk {mode}")
            st.markdown("---")
            continue

        # Cari Kolom 'Situasi Operasional'
        col_situasi = next((c for c in subset.columns if 'situasi' in c.lower() or 'kondisi' in c.lower()), None)
        
        if col_situasi:
            # --- MAPPING LOGIC (SITUASI -> PERSEN) ---
            # Menggunakan batas atas sebagai nilai plotting
            mapping_persen = {
                "Normal": 20,
                "Lancar": 20,
                "Ramai": 45,
                "Ramai Lancar": 45,
                "Padat": 75,
                "Sangat Padat": 95,
                "Macet": 100
            }
            
            # Buat kolom baru 'Occupancy Rate'
            # Jika kata tidak ditemukan di mapping, anggap 0 atau biarkan (fillna 0)
            subset['Occupancy Rate'] = subset[col_situasi].map(mapping_persen).fillna(0)
            
            # Definisi Warna Bar berdasarkan Nilai Persen
            # 0-20: Hijau, 21-45: Biru/Kuning, 46-75: Orange, >75: Merah
            def get_color(val):
                if val <= 20: return "#28a745" # Hijau
                elif val <= 45: return "#ffc107" # Kuning
                elif val <= 75: return "#fd7e14" # Orange
                else: return "#dc3545" # Merah

            subset['Warna'] = subset['Occupancy Rate'].apply(get_color)

            # Buat Bar Chart
            fig_bar = px.bar(
                subset,
                x='Tanggal Laporan',
                y='Occupancy Rate',
                title=f"Grafik Kepadatan - {mode}",
                labels={'Occupancy Rate': 'Tingkat Kepadatan (%)'},
                text_auto=True, # Tampilkan angka di bar
            )
            
            # Terapkan warna kustom & Range Y-Axis 0-100%
            fig_bar.update_traces(marker_color=subset['Warna'])
            fig_bar.update_layout(yaxis_range=[0, 100], yaxis_title="Okupansi (%)")
            
            st.plotly_chart(fig_bar, use_container_width=True)
            
            # Tabel Ringkas
            with st.expander(f"Lihat Data Detail Situasi {mode}"):
                st.dataframe(subset[['Tanggal Laporan', col_situasi, 'Occupancy Rate']], use_container_width=True)

        else:
            st.warning(f"Kolom 'Situasi Operasional' tidak ditemukan di data {mode}.")
        
        st.markdown("---")

# --- AUTO RELOAD SCRIPT ---
# Script akan berhenti sejenak (10 detik) lalu memuat ulang halaman
time.sleep(10)
st.rerun()
