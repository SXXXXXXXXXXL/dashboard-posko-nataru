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

# --- KONEKSI GOOGLE SHEETS (AUTO DETECT) ---
def connect_to_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # LOGIKA CERDAS: Cek kunci mana yang tersedia di Secrets
        if "json_mentah" in st.secrets:
            # Jika user pakai cara copy-paste JSON mentah
            creds_dict = json.loads(st.secrets["json_mentah"])
            
        elif "gcp_service_account" in st.secrets:
            # Jika user pakai cara Script Colab (yang terakhir berhasil)
            creds_dict = dict(st.secrets["gcp_service_account"])
            # Pastikan private key terbaca enter-nya dengan benar
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        else:
            st.error("❌ Kunci Rahasia tidak ditemukan di Secrets!")
            st.stop()

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Gagal login: {e}")
        st.stop()

# --- FUNGSI LOAD DATA ---
@st.cache_data(ttl=10)
def load_data():
    try:
        client = connect_to_sheet()
        # ID SPREADSHEET (Pastikan ini benar)
        sheet_id = '1IOOY8nR4UbNUB77pelUoYYYYByp9PBApl_A5BqYu-3U'
        
        sheet = client.open_by_key(sheet_id)
        all_data = sheet.get_worksheet(0).get_all_values()
        
        if len(all_data) < 2:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        
        # Preprocessing Tanggal
        if 'Tanggal Laporan' in df.columns:
            df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'])
            
        # Preprocessing Angka
        cols_num = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
        for col in cols_num:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"Error Data: {e}")
        return pd.DataFrame()

# --- TAMPILAN UTAMA ---
df = load_data()

if not df.empty:
    # --- 1. KPI UTAMA ---
    total_datang = df['Jumlah Penumpang Datang'].sum() if 'Jumlah Penumpang Datang' in df.columns else 0
    total_berangkat = df['Jumlah Penumpang BERANGKAT'].sum() if 'Jumlah Penumpang BERANGKAT' in df.columns else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Penumpang Datang", f"{total_datang:,.0f}")
    c2.metric("Total Penumpang Berangkat", f"{total_berangkat:,.0f}")
    c3.metric("Status API", "🟢 Terhubung", f"Update: {datetime.now().strftime('%H:%M:%S')}")
    
    st.markdown("---")
    
    # --- 2. GRAFIK & LAPORAN PER MODA ---
    if 'Jenis Simpul Transportasi' in df.columns:
        modes = df['Jenis Simpul Transportasi'].unique()
        
        # Loop untuk setiap moda transportasi
        for mode in modes:
            st.header(f"🚆 Laporan: {mode}")
            
            # Filter Data per Moda
            subset = df[df['Jenis Simpul Transportasi'] == mode].sort_values('Tanggal Laporan')
            
            # -- BAGIAN A: GRAFIK --
            cols_target = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
            df_melt = subset.melt(id_vars=['Tanggal Laporan'], 
                                value_vars=[c for c in cols_target if c in subset.columns],
                                var_name='Status', value_name='Jumlah')
            
            fig = px.line(df_melt, x='Tanggal Laporan', y='Jumlah', color='Status', 
                          markers=True, template='plotly_white', height=350)
            st.plotly_chart(fig, use_container_width=True)
            
            # -- BAGIAN B: TABEL KENDALA & SOLUSI --
            # Cek apakah kolom kendala/solusi ada (sesuaikan nama kolom persis seperti di Google Sheet Anda)
            col_kendala = 'Kendala di Lapangan :' # Sesuaikan nama kolom di sheet
            col_solusi = 'Usulan Solusi :'       # Sesuaikan nama kolom di sheet
            
            if col_kendala in subset.columns and col_solusi in subset.columns:
                # Filter hanya yang punya isi kendala (tidak kosong/strip)
                laporan_penting = subset[
                    (subset[col_kendala].str.len() > 2) & 
                    (subset[col_kendala] != "-")
                ][['Tanggal Laporan', 'Lokasi Penugasan', col_kendala, col_solusi]]
                
                if not laporan_penting.empty:
                    st.info(f"📢 **Catatan Lapangan ({mode}):**")
                    # Tampilkan tabel yang rapi
                    st.dataframe(
                        laporan_penting,
                        hide_index=True,
                        column_config={
                            "Tanggal Laporan": st.column_config.DateColumn("Tanggal", format="DD/MM/YYYY"),
                            col_kendala: "⚠️ Kendala Ditemukan",
                            col_solusi: "✅ Tindak Lanjut / Solusi"
                        },
                        use_container_width=True
                    )
                else:
                    st.success("✅ Tidak ada kendala signifikan yang dilaporkan.")
            else:
                st.warning(f"Kolom '{col_kendala}' atau '{col_solusi}' tidak ditemukan di Google Sheet.")
            
            st.markdown("---") # Garis pemisah antar moda

    # Tombol Refresh
    if st.button("🔄 Refresh Data Manual"):
        st.rerun()

else:
    st.info("Sedang menghubungkan ke Google Sheets...")

# Auto Refresh
time.sleep(10)
st.rerun()
