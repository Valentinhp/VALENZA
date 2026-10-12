from pathlib import Path
import pymupdf
from valenza.gui.family_pdf import final_concepts
from tools.preview_family_reports import sample_repository, generate_samples


def test_final_family_concepts_are_exact_read_only_and_person_specific():
    repo=sample_repository()
    before=repo.database.connection.total_changes
    mama=repo.family_statement('mama')
    owner=repo.family_statement('owner')
    items=lambda statement:[c for row in statement['rows'] for c in final_concepts(row,repo)]
    assert [(c['description'],c['amount_cents']) for c in items(mama)]==[
        ('Vasos',14900),('Globos',7905),('Blusa',14703),('150 mini animales de resina',12999)]
    assert [(c['description'],c['amount_cents']) for c in items(owner)]==[('Bolsas',2000),('Diferencia asumida',2122)]
    assert mama['assigned_cents']==50507 and owner['assigned_cents']==4122
    assert repo.database.connection.total_changes==before
    repo.database.close()


def test_inicio_button_exports_current_generator_exact_private_reports(tmp_path):
    generate_samples(tmp_path)
    for name,total,forbidden in [('mama-sintetico.pdf','$505.07 MXN','Bolsas'),
                                 ('yo-sintetico.pdf','$41.22 MXN','Vasos')]:
        with pymupdf.open(tmp_path/name) as doc:
            text=''.join(page.get_text() for page in doc)
            assert doc.metadata['creator']=='Valenza - PDF familiar 2'
            assert total in text and forbidden not in text
            assert all(term.casefold() not in text.casefold() for term in
                       ('Wallet','Descuento','Banco','Compensación','Recompra','Cambio por devolución'))
            for page in doc:
                for x0,y0,x1,y1,*_ in page.get_text('blocks'):
                    assert 30<=x0<x1<=582 and 20<=y0<y1<=782
    with pymupdf.open(tmp_path/'largo-sintetico.pdf') as doc:
        assert len(doc)>1
        assert sum(page.get_text().count('accesorios incluidos') for page in doc)==60
        for page in doc:
            assert page.get_text().count('Artículo ')==page.get_text().count('accesorios incluidos')
