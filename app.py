import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import time
import json
from datetime import datetime, timedelta

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
# ttl=15 detik agar memberi jeda lebih aman ke Google API
@st.cache_data(ttl=15, show_spinner="Sedang menarik data dari Google Sheets...")
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
            # Print error ke console untuk debugging, tapi jangan hentikan app
            print(f"⚠️ Gagal load {moda} (Mungkin Rate Limit): {e}")
            continue

    if all_dfs:
        df = pd.concat(all_dfs, ignore_index=True)
        
        # Preprocessing Tanggal
        if 'Tanggal Laporan Posko' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan Posko'], errors='coerce')
        elif 'Timestamp' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        else:
            col_lain = next((c for c in df.columns if 'tanggal' in c.lower() or 'tgl' in c.lower()), None)
            df['Tanggal Laporan'] = pd.to_datetime(df[col_lain], errors='coerce') if col_lain else pd.to_datetime('today')

        # Preprocessing Angka
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

# --- HITUNG WAKTU WIB (UTC + 7) ---
waktu_sekarang_wib = datetime.utcnow() + timedelta(hours=7)
str_waktu = waktu_sekarang_wib.strftime('%H:%M:%S')

# KPI GLOBAL
c1, c2, c3 = st.columns(3)
total_pergerakan = df_traffic[numeric_cols].sum().sum() if not df_traffic.empty and numeric_cols else 0
c1.metric("Total Pergerakan (Nasional)", f"{total_pergerakan:,.0f}")
c2.metric("Total Laporan Masuk", f"{len(df_traffic)} Laporan")

with c3:
    st.metric("Last Update (WIB)", str_waktu)
    st.caption("🔄 Auto-refresh: 15 detik")

st.markdown("---")

# --- MEMBUAT 3 TABS ---
tab_trafik, tab_kepadatan, tab_insiden = st.tabs(["📊 Trafik & Pergerakan", "🚦 Situasi & Kepadatan", "⚠️ Insiden & Kejadian"])

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
            
            # Line Chart
            cols_active = [c for c in numeric_cols if c in subset.columns and subset[c].sum() > 0]
            if cols_active:
                fig = px.line(subset, x='Tanggal Laporan', y=cols_active, markers=True, title=f"Tren di {mode}", template='seaborn')
                fig.update_layout(yaxis_title="Jumlah")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Data masuk tapi angka pergerakan 0.")

# ================= TAB 2: KEPADATAN (% Okupansi) =================
with tab_kepadatan:
    st.subheader("Tingkat Kepadatan (% Okupansi)")
    st.caption("Konversi: Normal ≤20%, Ramai ≤45%, Padat ≤75%, Sangat Padat ≤95%")

    for mode in SUMBER_DATA_MODA.keys():
        st.markdown(f"### 📍 {mode}")
        
        subset = pd.DataFrame()
        if not df_traffic.empty:
            subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]
        
        if subset.empty:
            st.info(f"Belum ada data untuk {mode}")
            st.markdown("---")
            continue

        col_situasi = next((c for c in subset.columns if 'situasi' in c.lower() or 'kondisi' in c.lower()), None)
        
        if col_situasi:
            mapping_persen = {"Normal": 20, "Lancar": 20, "Ramai": 45, "Ramai Lancar": 45, "Padat": 75, "Sangat Padat": 95, "Macet": 100}
            subset['Occupancy Rate'] = subset[col_situasi].map(mapping_persen).fillna(0)
            
            def get_color(val):
                if val <= 20: return "#28a745"
                elif val <= 45: return "#ffc107"
                elif val <= 75: return "#fd7e14"
                else: return "#dc3545"

            subset['Warna'] = subset['Occupancy Rate'].apply(get_color)

            fig_bar = px.bar(subset, x='Tanggal Laporan', y='Occupancy Rate', title=f"Kepadatan - {mode}", text_auto=True)
            fig_bar.update_traces(marker_color=subset['Warna'])
            fig_bar.update_layout(yaxis_range=[0, 100], yaxis_title="Okupansi (%)")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("Kolom Situasi tidak ditemukan.")
        st.markdown("---")

# ================= TAB 3: INSIDEN (Bar Chart Kejadian) =================
with tab_insiden:
    st.subheader("📊 Statistik Kejadian Khusus / Insiden")
    st.caption("Menghitung jumlah laporan yang memiliki status 'Ada' pada kolom Kejadian Khusus.")

    for mode in SUMBER_DATA_MODA.keys():
        st.markdown(f"### 📍 {mode}")
        
        subset = pd.DataFrame()
        if not df_traffic.empty:
            subset = df_traffic[df_traffic['Jenis Simpul Transportasi'] == mode]
        
        if subset.empty:
            st.info(f"Belum ada data untuk {mode}")
            st.markdown("---")
            continue
        
        col_insiden_flag = next((c for c in subset.columns if 'kejadian khusus' in c.lower() or 'insiden' in c.lower()), None)
        col_uraian = next((c for c in subset.columns if 'uraian kejadian' in c.lower()), None)

        if col_insiden_flag:
            insiden_df = subset[subset[col_insiden_flag].astype(str).str.contains("Ada", case=False, na=False)]
            
            if not insiden_df.empty:
                df_count = insiden_df.groupby('Tanggal Laporan').size().reset_index(name='Jumlah Insiden')
                
                fig_insiden = px.bar(
                    df_count, 
                    x='Tanggal Laporan', 
                    y='Jumlah Insiden',
                    title=f"Frekuensi Insiden - {mode}",
                    text_auto=True,
                    color_discrete_sequence=['#dc3545']
                )
                fig_insiden.update_layout(yaxis_title="Jumlah Kejadian")
                st.plotly_chart(fig_insiden, use_container_width=True)
                
                with st.expander(f"🚨 Lihat Detail Kejadian di {mode} ({len(insiden_df)} kejadian)"):
                    cols_show = ['Tanggal Laporan', col_insiden_flag]
                    if col_uraian: cols_show.append(col_uraian)
                    st.dataframe(insiden_df[cols_show], hide_index=True, use_container_width=True)
            else:
                st.success(f"✅ Alhamdulillah, nihil kejadian/insiden di {mode} sejauh ini.")
        else:
            st.warning("Kolom 'Kejadian Khusus/Insiden' tidak ditemukan di data ini.")
        
        st.markdown("---")

# --- MANUAL REFRESH (CLEAR CACHE) ---
if st.button("🔄 Paksa Tarik Data Baru (Clear Cache)"):
    st.cache_data.clear()
    st.rerun()

# --- AUTO RELOAD SCRIPT ---
time.sleep(15) # Diubah ke 15 detik agar lebih aman dari limit Google
st.rerun()
