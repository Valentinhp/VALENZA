from collections import Counter
from copy import deepcopy
import re

import pymupdf

from tools.preview_family_reports import sample_repository
from valenza.gui.family_pdf import final_concepts, write_report
from valenza.gui.app import format_money


def test_document_preserves_all_financial_amounts_and_database(tmp_path):
    repo = sample_repository()
    try:
        for user in ('owner', 'mama'):
            statement = repo.family_statement(user)
            before = deepcopy(statement)
            changes = repo.database.connection.total_changes
            path = tmp_path / f'{user}.pdf'
            write_report(statement, path, issued_at='2026-10-12', repository=repo)
            expected = [statement[key] for key in ('remaining_cents', 'assigned_cents', 'paid_cents')]
            expected += [c['amount_cents'] for row in statement['rows'] for c in final_concepts(row, repo)]
            expected += [r['amount_cents'] for row in statement['rows'] for r in row['receipts']]
            expected += [item['amount_cents'] for item in statement.get('forecasts', []) if item['kind'] in ('MSI', 'SUBSCRIPTION')]
            if statement.get('is_owner'):
                from valenza.gui.personal_result import personal_result
                projection=personal_result(repo)
                expected += [projection['discount_cents'],abs(projection['result_cents'])]
                for row in projection['rows']:
                    expected += [row['cost_cents'],row['family_cents'],abs(row['result_cents'])]
                expected += [sum(r['cost_cents'] for r in projection['rows']),
                             sum(r['family_cents'] for r in projection['rows']),abs(projection['result_cents'])]
            with pymupdf.open(path) as document:
                text = ''.join(page.get_text() for page in document)
                found = Counter(re.findall(r'\$[\d,]+\.\d{2} MXN', text))
                assert found == Counter(format_money(amount) for amount in expected)
                assert all(page.get_images() for page in document)
                assert all(page.rect.width == 612 and page.rect.height == 792 for page in document)
                assert '12/10/2026' in text and 'Emisión: 10/2026' in text
            assert statement == before and repo.family_statement(user) == before
            assert repo.database.connection.total_changes == changes
    finally:
        repo.database.close()
