from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st


@dataclass
class OfxMeta:
    bank_id: str
    account_id: str
    account_type: str
    currency: str
    org: str
    fid: str


def parse_dataframe(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    if uploaded_file.name.lower().endswith(".csv"):
        return pd.read_csv(uploaded_file)
    return pd.read_excel(uploaded_file)


def normalize_amount(series: pd.Series, invert: bool) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if invert:
        values = values * -1
    return values


def parse_date(series: pd.Series, date_format: str) -> pd.Series:
    if date_format.strip():
        return pd.to_datetime(series, format=date_format, errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def generate_fitid(row_index: int, when: datetime, amount: float, memo: str) -> str:
    digest = f"{when:%Y%m%d}-{amount:.2f}-{row_index}"
    if memo:
        digest = f"{digest}-{memo.strip()[:20]}"
    return digest.replace(" ", "")


def render_ofx(
    df: pd.DataFrame,
    meta: OfxMeta,
    date_col: str,
    amount_col: str,
    name_col: Optional[str],
    memo_col: Optional[str],
    invert_amount: bool,
    date_format: str,
) -> str:
    df = df.copy()
    df["__date"] = parse_date(df[date_col], date_format)
    df["__amount"] = normalize_amount(df[amount_col], invert_amount)

    df = df.dropna(subset=["__date", "__amount"])
    df = df.sort_values("__date")

    start_date = df["__date"].min() if not df.empty else datetime.now()
    end_date = df["__date"].max() if not df.empty else datetime.now()

    lines = [
        "OFXHEADER:100",
        "DATA:OFXSGML",
        "VERSION:102",
        "SECURITY:NONE",
        "ENCODING:USASCII",
        "CHARSET:1252",
        "COMPRESSION:NONE",
        "OLDFILEUID:NONE",
        "NEWFILEUID:NONE",
        "",
        "<OFX>",
        "  <SIGNONMSGSRSV1>",
        "    <SONRS>",
        "      <STATUS>",
        "        <CODE>0",
        "        <SEVERITY>INFO",
        "      </STATUS>",
        f"      <DTSERVER>{datetime.now():%Y%m%d%H%M%S}",
        f"      <LANGUAGE>ENG",
        f"      <FI>",
        f"        <ORG>{meta.org}",
        f"        <FID>{meta.fid}",
        f"      </FI>",
        "    </SONRS>",
        "  </SIGNONMSGSRSV1>",
        "  <BANKMSGSRSV1>",
        "    <STMTTRNRS>",
        "      <TRNUID>1",
        "      <STATUS>",
        "        <CODE>0",
        "        <SEVERITY>INFO",
        "      </STATUS>",
        "      <STMTRS>",
        f"        <CURDEF>{meta.currency}",
        "        <BANKACCTFROM>",
        f"          <BANKID>{meta.bank_id}",
        f"          <ACCTID>{meta.account_id}",
        f"          <ACCTTYPE>{meta.account_type}",
        "        </BANKACCTFROM>",
        "        <BANKTRANLIST>",
        f"          <DTSTART>{start_date:%Y%m%d}",
        f"          <DTEND>{end_date:%Y%m%d}",
    ]

    for idx, row in df.iterrows():
        memo = str(row[memo_col]).strip() if memo_col else ""
        name = str(row[name_col]).strip() if name_col else memo
        when = row["__date"]
        amount = float(row["__amount"])
        fitid = generate_fitid(idx, when, amount, memo)
        trn_type = "CREDIT" if amount >= 0 else "DEBIT"
        lines.extend(
            [
                "          <STMTTRN>",
                f"            <TRNTYPE>{trn_type}",
                f"            <DTPOSTED>{when:%Y%m%d}",
                f"            <TRNAMT>{amount:.2f}",
                f"            <FITID>{fitid}",
                f"            <NAME>{name or 'Transaction'}",
                f"            <MEMO>{memo}",
                "          </STMTTRN>",
            ]
        )

    lines.extend(
        [
            "        </BANKTRANLIST>",
            "        <LEDGERBAL>",
            "          <BALAMT>0.00",
            f"          <DTASOF>{end_date:%Y%m%d}",
            "        </LEDGERBAL>",
            "      </STMTRS>",
            "    </STMTTRNRS>",
            "  </BANKMSGSRSV1>",
            "</OFX>",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    st.set_page_config(page_title="CSV/XLSX to OFX Converter", layout="centered")
    st.title("CSV/XLSX to OFX")
    st.write("Upload a CSV or Excel file, map the columns, and download an OFX file.")

    uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"])
    if not uploaded:
        st.info("Choose a file to get started.")
        return

    df = parse_dataframe(uploaded)
    st.subheader("Preview")
    st.dataframe(df.head(20), use_container_width=True)

    st.subheader("Column mapping")
    columns = list(df.columns)
    date_col = st.selectbox("Date column", columns)
    amount_col = st.selectbox("Amount column", columns)
    name_col = st.selectbox("Payee/Name column (optional)", ["(none)"] + columns)
    memo_col = st.selectbox("Memo/Description column (optional)", ["(none)"] + columns)
    date_format = st.text_input("Date format (optional)", help="Example: %Y-%m-%d")
    invert_amount = st.checkbox("Invert amount sign", value=False)

    st.subheader("Account details")
    meta = OfxMeta(
        bank_id=st.text_input("Bank ID", value="0000"),
        account_id=st.text_input("Account ID", value="000000000"),
        account_type=st.selectbox("Account Type", ["CHECKING", "SAVINGS", "CREDITLINE"]),
        currency=st.text_input("Currency", value="USD"),
        org=st.text_input("FI Org", value="UNIMATRIX"),
        fid=st.text_input("FI Fid", value="0000"),
    )

    if st.button("Generate OFX"):
        ofx_text = render_ofx(
            df=df,
            meta=meta,
            date_col=date_col,
            amount_col=amount_col,
            name_col=None if name_col == "(none)" else name_col,
            memo_col=None if memo_col == "(none)" else memo_col,
            invert_amount=invert_amount,
            date_format=date_format,
        )

        filename_root = uploaded.name.rsplit(".", 1)[0]
        st.download_button(
            "Download OFX",
            ofx_text,
            file_name=f"{filename_root}.ofx",
            mime="application/x-ofx",
        )


if __name__ == "__main__":
    main()
