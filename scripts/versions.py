from bs4 import BeautifulSoup

# Load your HTML (replace this with the actual HTML content)
with open("versions_html/4.html") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Collect all the data rows
rows = soup.select("div.dataMapOdd, div.dataMapEven")

items_width = [19, 20, 1, 5, 4, 4, 4, 4]

version_modules_str_fmt = r"\multirow{{4}}{{*}}{{{:>2}}} & \multirow{{4}}{{*}}{{{:>3}}}"

latex_rows = []
for row in rows:
    cells = row.find_all("div")
    version_ls, modules_ls = ([cell.get_text(), None, None, None] for cell in cells[:2])

    processed_cells = []
    for unsplited_cell in cells[2:]:
        processed_unsplited_cells = unsplited_cell.get_text(separator="\\newline").strip().split("\\newline")
        processed_unsplited_cells_ls = []
        for cell in processed_unsplited_cells:
            processed_unsplited_cells_ls.append(cell.strip().replace(",", ""))
        processed_cells.append(processed_unsplited_cells_ls)

    ecc_level_ls, data_bits_mixed_ls, numeric_ls, alphanumeric_ls, binary_ls, kanji_ls = processed_cells

    for idx, (version, modules, ecc_level, data_bits_mixed, numeric, alphanumeric, binary, kanji) in enumerate(zip(version_ls, modules_ls, ecc_level_ls, data_bits_mixed_ls, numeric_ls, alphanumeric_ls, binary_ls, kanji_ls, strict=True)):
        match idx:
            case 0:
                op = version_modules_str_fmt.format(version, modules.split("x")[0])
            case _:
                op = " & ".join(" " * width for width in items_width[:2])

        op_items = []
        for width, item in zip(items_width[2:], [ecc_level, data_bits_mixed, numeric, alphanumeric, binary, kanji], strict=True):
            op_items.append(item.ljust(width))

        op += " & " + " & ".join(op_items) + r" \\ "

        match idx:
            case 3:
                op += r"\hline"
            case _:
                op += r"\cline{3-8}"

        latex_rows.append(op)

latex_table = r"""\begin{table}[H]
\centering
\resizebox{\columnwidth}{!}{%
\begin{tabular}{|c|c|c|c|c|c|c|c|}
\hline
Version &
  \begin{tabular}[c]{@{}c@{}}Modules\\ (x, y)\end{tabular} &
  \begin{tabular}[c]{@{}c@{}}ECC\\ Level\end{tabular} &
  \begin{tabular}[c]{@{}c@{}}Data bits\\ (mixed)\end{tabular} &
  Numeric &
  Alphanumeric &
  Binary &
  Kanji \\ \hline
""" + "\n".join(latex_rows) + r"""
\end{tabular}%
}
\end{table}
"""

print(latex_table)