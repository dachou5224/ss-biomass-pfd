"""pytest 入口：复用 pdf_reference_data 中的本地 PDF 参考数据标记。"""

from pdf_reference_data import (  # noqa: F401
    HAS_DBI_MASS_BALANCE_CSV,
    HAS_DBI_STREAM_TABLE_CSV,
    HAS_INCI_STREAMS_CSV,
    PDF_REFERENCE_DIR,
    pdf_reference_file,
    requires_dbi_mass_balance_csv,
    requires_dbi_stream_table_csv,
    requires_inci_streams_csv,
)
