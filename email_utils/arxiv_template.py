def get_paper_block_html(
    title: str,
    rate: str,
    arxiv_id: str,
    summary: str,
    pdf_url: str,
) -> str:
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%"
           style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px;
                  padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #57606a; padding: 8px 0;">
            <strong>arXiv ID:</strong> {arxiv_id}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>TLDR:</strong> {summary}
        </td>
    </tr>
    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}"
               style="display: inline-block; text-decoration: none; font-size: 14px;
                      font-weight: bold; color: #fff; background-color: #b31b1b;
                      padding: 8px 16px; border-radius: 6px;">PDF</a>
        </td>
    </tr>
</table>
"""
    return block_template.format(
        title=title,
        rate=rate,
        arxiv_id=arxiv_id,
        summary=summary,
        pdf_url=pdf_url,
    )
