
import streamlit as st
import sqlite3
import zipfile
import tempfile
from pathlib import Path
import re
import pandas as pd

st.set_page_config(page_title="Cek Penjualan Kasir", page_icon="💰", layout="wide")

def rupiah(v):
    try:
        return "Rp{:,.0f}".format(float(v)).replace(",", ".")
    except:
        return "Rp0"

def find_db(uploaded):
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".db":
        p = Path(tempfile.mkdtemp()) / uploaded.name
        p.write_bytes(uploaded.getvalue())
        return p
    if suffix == ".zip":
        folder = Path(tempfile.mkdtemp())
        zpath = folder / uploaded.name
        zpath.write_bytes(uploaded.getvalue())
        with zipfile.ZipFile(zpath) as z:
            z.extractall(folder / "extract")
        dbs = list((folder / "extract").rglob("*.db"))
        if not dbs:
            raise ValueError("File ZIP tidak berisi database .db")
        return dbs[0]
    raise ValueError("Format harus .db atau .zip")

def load_data(db_path):
    con = sqlite3.connect(str(db_path))
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    if "tx_tsale" not in tables:
        con.close()
        raise ValueError("Tabel tx_tsale tidak ditemukan.")
    cols = [r[1] for r in con.execute("PRAGMA table_info(tx_tsale)").fetchall()]
    needed = {"user_id","date_tx","faktur","total_faktur","cash","change_pay"}
    if not needed.issubset(cols):
        con.close()
        raise ValueError("Kolom transaksi yang dibutuhkan tidak lengkap.")
    q = """SELECT user_id, date_tx, faktur, total_faktur, cash, change_pay,
                   card, voucher, wallet, termin
            FROM tx_tsale"""
    df = pd.read_sql_query(q, con)
    con.close()
    for c in ["total_faktur","cash","change_pay","card","voucher","wallet"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["user_id"] = df["user_id"].astype(str).str.strip()
    df["date_tx"] = df["date_tx"].astype(str).str.strip()
    return df

st.title("💰 Cek Nominal Penjualan Kasir")
st.caption("Upload database .DB atau .ZIP → aplikasi otomatis menghitung cash bersih.")

uploaded = st.file_uploader("Kirim database penjualan", type=["db","zip"])

if uploaded:
    try:
        db = find_db(uploaded)
        df = load_data(db)
    except Exception as e:
        st.error(str(e))
        st.stop()

    # Coba deteksi NIK dari nama file
    nik_from_name = None
    nums = re.findall(r"(?<!\d)(\d{6,10})(?!\d)", uploaded.name)
    if nums:
        for n in nums:
            if n in set(df["user_id"]):
                nik_from_name = n
                break

    st.success(f"Database terbaca: {len(df):,} baris transaksi.")

    c1, c2 = st.columns(2)
    with c1:
        niks = sorted([x for x in df["user_id"].unique() if x and x.lower() != "none"])
        default_nik = niks.index(nik_from_name) if nik_from_name in niks else 0
        nik = st.selectbox("NIK Kasir", niks, index=default_nik)
    with c2:
        dates = sorted(df.loc[df["user_id"] == nik, "date_tx"].unique())
        date_default = len(dates)-1 if dates else 0
        tanggal = st.selectbox("Tanggal", dates, index=date_default)

    x = df[(df["user_id"] == nik) & (df["date_tx"] == tanggal)].copy()

    total_penjualan = x["total_faktur"].sum()
    cash_diterima = x["cash"].sum()
    kembalian = x["change_pay"].sum()
    cash_bersih = cash_diterima - kembalian

    st.divider()
    st.subheader("Hasil")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Jumlah Transaksi", f"{len(x):,}".replace(",", "."))
    m2.metric("Total Penjualan", rupiah(total_penjualan))
    m3.metric("Cash Diterima", rupiah(cash_diterima))
    m4.metric("Kembalian", rupiah(kembalian))

    st.success(f"### 💵 NOMINAL CASH BERSIH: {rupiah(cash_bersih)}")
    st.caption(f"Rumus: {rupiah(cash_diterima)} − {rupiah(kembalian)} = {rupiah(cash_bersih)}")

    with st.expander("Lihat rincian faktur"):
        show = x[["faktur","total_faktur","cash","change_pay","card","voucher","wallet","termin"]].copy()
        show.columns = ["Faktur","Total Faktur","Cash","Kembalian","Card","Voucher","Wallet","Termin"]
        for c in ["Total Faktur","Cash","Kembalian","Card","Voucher","Wallet"]:
            show[c] = show[c].map(rupiah)
        st.dataframe(show, use_container_width=True, hide_index=True)

    # Export CSV
    csv = x.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download rincian CSV", csv,
                       file_name=f"penjualan_{nik}_{tanggal.replace('/','-')}.csv",
                       mime="text/csv")
else:
    st.info("Silakan kirim file database .ZIP atau .DB. Contoh: CC21_2026-10-03_26097963_android.zip")
