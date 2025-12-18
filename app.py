import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import plotly.express as px
import time
from datetime import datetime

# --- KONFIGURASI HALAMAN WEBSITE ---
st.set_page_config(
    page_title="Dashboard Posko Nataru",
    page_icon="🚌",
    layout="wide"
)

# Judul Website
st.title("📊 Dashboard Monitoring Posko Nataru 2025/2026")
st.markdown("Data diperbarui secara realtime dari Google Sheets.")

# --- KONEKSI KE GOOGLE SHEETS (MODE AMAN) ---
# Kita mengambil "kunci rahasia" dari sistem Secrets Streamlit (bukan file json fisik)
def connect_to_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. Ambil credentials dari secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # 2. PERBAIKAN OTOMATIS PRIVATE KEY (BAGIAN PENTING!)
    # Kode ini akan mengubah tulisan "\n" menjadi tombol Enter sungguhan
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    # 3. Buat koneksi
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- FUNGSI AMBIL DATA (CACHE) ---
# st.cache_data mencegah script download ulang jika data belum berubah drastis
# ttl=10 artinya data dianggap kadaluarsa setelah 10 detik (auto refresh logic)
@st.cache_data(ttl=10)
def load_data():
    try:
        client = connect_to_sheet()
        # Masukkan ID Spreadsheet Anda DISINI
        sheet_id = '1IOOY8nR4UbNUB77pelUoYYYYByp9PBApl_A5BqYu-3U' 
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.get_worksheet(0)
        
        all_data = worksheet.get_all_values()
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        
        # Preprocessing
        df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'])
        cols_num = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
        for col in cols_num:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"Terjadi kesalahan koneksi: {e}")
        return pd.DataFrame()

# --- TAMPILAN DASHBOARD ---
df = load_data()

if not df.empty:
    # 1. Tampilkan KPI Utama (Kotak Angka Besar)
    total_datang = df['Jumlah Penumpang Datang'].sum()
    total_berangkat = df['Jumlah Penumpang BERANGKAT'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Penumpang Datang", f"{total_datang:,}")
    col2.metric("Total Penumpang Berangkat", f"{total_berangkat:,}")
    col3.metric("Update Terakhir", datetime.now().strftime('%H:%M:%S'))

    st.markdown("---") # Garis Pembatas

    # 2. Proses Data untuk Grafik
    cols_num = ['Jumlah Penumpang Datang', 'Jumlah Penumpang BERANGKAT']
    df_grouped = df.groupby(['Tanggal Laporan', 'Jenis Simpul Transportasi'])[cols_num].sum().reset_index()
    df_melted = df_grouped.melt(id_vars=['Tanggal Laporan', 'Jenis Simpul Transportasi'], 
                                value_vars=cols_num,
                                var_name='Status Penumpang', 
                                value_name='Jumlah')
    df_melted = df_melted.sort_values('Tanggal Laporan')

    # 3. Tampilkan Grafik
    modes = df_melted['Jenis Simpul Transportasi'].unique()
    
    # Bagi layar menjadi 2 kolom agar grafik rapi
    chart_cols = st.columns(2)
    
    for i, mode in enumerate(modes):
        with chart_cols[i % 2]: # Logika ganjil genap untuk kolom
            subset = df_melted[df_melted['Jenis Simpul Transportasi'] == mode]
            fig = px.line(subset, x='Tanggal Laporan', y='Jumlah', color='Status Penumpang',
                          markers=True, title=f'Tren: {mode}', template='plotly_white')
            fig.update_xaxes(tickformat="%d %b")
            st.plotly_chart(fig, use_container_width=True)

    # 4. Tombol Refresh Manual (Selain auto-refresh cache)
    if st.button('Muat Ulang Data Sekarang'):
        st.rerun()
        
else:
    st.warning("Data belum tersedia atau gagal dimuat.")

# Logika Auto Rerun setiap 10 detik agar realtime
time.sleep(10)

st.rerun()
