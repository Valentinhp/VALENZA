"""Generate synthetic samples through the real Inicio PDF button, never a personal DB."""
from pathlib import Path
import pymupdf
from PySide6.QtWidgets import QFileDialog
from valenza.gui.app import MainWindow, create_application, write_family_pdf
from valenza.ocr.order_import import parse_receipt
from valenza.persistence.database import LocalDatabase
from valenza.persistence.repository import FinanceRepository


def sample_repository():
    db=LocalDatabase.open(':memory:','synthetic-only',allow_synthetic_in_memory=True)
    db.migrate()
    repo=FinanceRepository(db)
    repo.add_person('owner','Yo',is_owner=True)
    repo.add_person('mama','Mamá')
    repo.add_institution('bank','Banco sintético privado')
    repo.add_instrument('card','bank','Tarjeta sintética privada','CREDIT_CARD')
    repo.add_instrument('wallet','bank','Wallet sintética privada','WALLET_BALANCE')
    draft=parse_receipt((Path(__file__).resolve().parents[1]/'tests/fixtures_synthetic/mp_openpdf.txt').read_text(encoding='utf-8'))
    draft['fingerprint']='synthetic-final-family-report'
    for index,description in enumerate(['Vasos','Bolsas','Globos','Blusa','150 mini animales de resina']):
        draft['products'][index]['description']=description
        draft['products'][index]['allocations']={'owner':2000 if index==1 else 0,
                                                'mama':0 if index==1 else draft['products'][index]['unit']}
    repo.create_order(order_id='sample',ordered_at='2026-10-03',merchant='Compra sintética',
        instrument_id='card',original_cents=60287,discount_cents=6029,charged_cents=54258,
        allocations=({'user_id':'owner','amount_cents':2000},{'user_id':'mama','amount_cents':58287}),
        import_evidence=draft,product_refunds=({'product_index':4,'amount_cents':18657,
            'destination_id':'wallet','status':'ACCREDITED','accredited_at':'2026-10-10',
            'final_allocations':{'owner':2122,'mama':12999},'repurchase':{'amount_cents':12999,
                'ordered_at':'2026-10-11','instrument_id':'wallet','apply_surplus':True}},))
    return repo


def generate_samples(output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    app=create_application([])
    repo=sample_repository()
    window=MainWindow(database=repo.database)
    original_dialog=QFileDialog.getSaveFileName
    before=repo.database.connection.total_changes
    try:
        for user,filename in [('mama','mama-sintetico.pdf'),('owner','yo-sintetico.pdf')]:
            destination=output/filename
            QFileDialog.getSaveFileName=lambda *a, target=destination, **kw:(str(target),'PDF (*.pdf)')
            row=next(i for i in range(window.dashboard_people.rowCount()) if window.dashboard_people.item(i,5).text()==user)
            window.dashboard_people.selectRow(row)
            window.dashboard_person_pdf.click()
            assert destination.is_file(), 'The real Inicio export did not create a PDF'
            with pymupdf.open(destination) as doc:
                assert doc.metadata['creator']=='Valenza - PDF familiar 2'
            direct=destination.with_suffix('.check.pdf')
            write_family_pdf(repo.family_statement(user),direct,repository=repo)
            with pymupdf.open(destination) as actual, pymupdf.open(direct) as expected:
                assert len(actual)==len(expected)
                assert all(a.get_pixmap().samples==b.get_pixmap().samples
                           for a,b in zip(actual,expected)), 'Inicio used a different renderer'
            direct.unlink()
        assert repo.database.connection.total_changes==before
    finally:
        QFileDialog.getSaveFileName=original_dialog
    # Separate synthetic long-name stress sample.
    concepts=[dict(description=f'Artículo {i+1:02d}: organizadores reutilizables para cocina con tapas ajustables, diferentes tamaños y accesorios incluidos',
                   amount_cents=100,allocations={'owner':0,'mama':100}) for i in range(60)]
    repo.create_order(order_id='long',ordered_at='2026-10-11',merchant='Ejemplo extenso',instrument_id='card',
        original_cents=6000,discount_cents=0,charged_cents=6000,
        allocations=({'user_id':'owner','amount_cents':0},{'user_id':'mama','amount_cents':6000}),concepts=concepts)
    write_family_pdf(repo.family_statement('mama'),output/'largo-sintetico.pdf',repository=repo,issued_at='2026-10-11')
    window.close()
    app.processEvents()
    for path in output.glob('*.pdf'):
        with pymupdf.open(path) as document:
            for index,page in enumerate(document):
                page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(output/f'{path.stem}-{index+1}.png')
            print(path.name,'pages',len(document))


if __name__=='__main__':
    generate_samples(Path(__file__).resolve().parents[1]/'output/pdf')
