"""Private, read-only family reports. No financial records are changed here."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from valenza.gui import pdf_theme as theme


def final_concepts(row, repository=None):
    if repository is None or not row.get('order_id'):
        if row.get('concept_adjustment_cents'):
            return [dict(description='Compra registrada', amount_cents=row['sale_cents'])] if row['sale_cents'] else []
        return row['concepts'] or ([dict(description='Compra registrada',amount_cents=row['sale_cents'])] if row['sale_cents'] else [])
    order = repository.get_order(row['order_id'])
    if not order:
        raise ValueError('No se encontró el pedido del reporte.')
    # Funded replacement participation is zero; it must not appear as another debt.
    if row['sale_cents'] == 0:
        return []
    products = order['manual_concepts'] or (order['import_evidence'] or {}).get('products', [])
    if not products:
        return [dict(description='Compra registrada', amount_cents=row['sale_cents'])]
    user = row['user_id']
    refunds = {r['product_index']: r for r in order['product_refunds'] if r['status']=='ACCREDITED'}
    result = []
    for index, product in enumerate(products):
        allocations = product.get('allocations', {})
        if isinstance(allocations, list):
            allocations = {a['user_id']:a['amount_cents'] for a in allocations}
        amount = allocations.get(user, 0)
        description = product['description']
        refund = refunds.get(index)
        if refund:
            adjustment = next((a for a in refund['adjustments'] if a['user_id']==user), None)
            if adjustment:
                amount = adjustment.get('effective_final_cents', adjustment['final_cents'])
                if row['participant_role']=='PERSONAL' and not allocations.get(user, 0):
                    description = 'Diferencia asumida'
        if amount:
            result.append(dict(description=description, amount_cents=amount))
    fee = (row.get('financial_detail') or {}).get('subscription')
    if fee:
        result.extend(c for c in row['concepts'] if c['description']=='Recargo de suscripción acordado')
    if sum(c['amount_cents'] for c in result) != row['sale_cents']:
        # Unknown historical projection: retain the exact final amount, never guess a product.
        return [dict(description='Compra registrada', amount_cents=row['sale_cents'])]
    return result


def write_report(statement, path, *, issued_at=None, repository=None):
    import pymupdf
    amount = lambda cents: f'${Decimal(cents)/Decimal(100):,.2f} MXN'
    def dated(value):
        try:
            return date.fromisoformat(str(value)[:10]).strftime('%d/%m/%Y')
        except ValueError:
            return 'Fecha no registrada'
    document = pymupdf.open()
    dark=theme.INK; muted=theme.MUTED; blue=theme.TERRACOTTA
    left,right,bottom=theme.LEFT,theme.RIGHT,theme.BOTTOM
    issued = issued_at or date.today().isoformat()
    period = date.fromisoformat(str(issued)[:10]).strftime('%m/%Y')
    page=None; y=0
    def text(x, baseline, value, size=10, font='helv', color=dark):
        page.insert_text((x,baseline),str(value),fontsize=size,fontname=font,color=color)
    def new_page():
        nonlocal page,y
        page=document.new_page(width=theme.PAGE_WIDTH,height=theme.PAGE_HEIGHT)
        theme.page_header(page, 'ESTADO DE CUENTA', 'Emisión: '+period, dated(issued))
        y=108
    def room(height):
        if y+height>bottom:
            new_page()
    def wrap(value,width,size=10,font='helv'):
        words=' '.join(str(value).split()).split(' ')
        lines=[]; line=''
        for word in words:
            while pymupdf.get_text_length(word,fontsize=size,fontname=font)>width:
                if line: lines.append(line); line=''
                cut=1
                while cut<len(word) and pymupdf.get_text_length(word[:cut+1],fontsize=size,fontname=font)<=width: cut+=1
                lines.append(word[:cut]); word=word[cut:]
            candidate=(line+' '+word).strip()
            if line and pymupdf.get_text_length(candidate,fontsize=size,fontname=font)>width:
                lines.append(line); line=word
            else: line=candidate
        if line: lines.append(line)
        return lines or ['']
    def heading(label):
        nonlocal y
        room(65)
        text(left,y,label,12,'hebo'); y+=24
    def table_header():
        nonlocal y
        page.draw_rect(pymupdf.Rect(left,y,right,y+25),color=None,fill=theme.CREAM)
        text(left+10,y+17,'Concepto',9,'hebo')
        text(right-90,y+17,'Importe',9,'hebo')
        y+=25
    def table_row(label,value):
        nonlocal y
        lines=wrap(label,right-left-146)
        full_height=max(32,len(lines)*14+12)
        if full_height <= bottom-108-25 and y+full_height>bottom:
            new_page(); table_header()
        # Break exceptionally long descriptions at line boundaries, repeating headers.
        while lines:
            if y+32>bottom:
                new_page(); table_header()
            count=min(len(lines),max(1,int((bottom-y-12)//14)))
            chunk,lines=lines[:count],lines[count:]
            height=max(32,len(chunk)*14+12)
            for index,line in enumerate(chunk): text(left+10,y+18+index*14,line)
            if not lines:
                value_text=amount(value)
                x=right-10-pymupdf.get_text_length(value_text,fontsize=10)
                text(x,y+18,value_text)
            page.draw_line((left,y+height),(right,y+height),color=theme.RULE,width=.5)
            y+=height
    try:
        new_page()
        for line in wrap(statement['person'],right-left,24,'hebo'):
            room(29)
            text(left,y,line,24,'hebo'); y+=29
        text(left,y+3,'Preparado el '+dated(issued),10,color=muted)
        y+=25
        room(120)
        page.draw_rect(pymupdf.Rect(left,y,right,y+74),color=None,fill=theme.CREAM)
        text(left+14,y+22,'Te falta pagar',11,color=blue)
        text(left+14,y+53,amount(statement['remaining_cents']),24,'hebo',blue)
        y+=95
        text(left,y,'Total a tu cargo: '+amount(statement['assigned_cents']),10)
        text(315,y,'Ya pagaste: '+amount(statement['paid_cents']),10); y+=35
        heading('Tus conceptos')
        table_header()
        shown=0
        for row in statement['rows']:
            for concept in final_concepts(row,repository):
                table_row(concept['description'],concept['amount_cents']); shown+=concept['amount_cents']
        if shown != statement['assigned_cents']:
            raise ValueError('Los conceptos finales no coinciden con el estado de cuenta.')
        if not shown:
            table_row('Sin importes a tu cargo',0)
        y+=25
        grouped = {}
        for row in statement['rows']:
            for receipt in row['receipts']:
                identity = receipt.get('payment_id') or ('legacy', len(grouped))
                if identity not in grouped:
                    grouped[identity] = dict(receipt, amount_cents=0)
                grouped[identity]['amount_cents'] += receipt['amount_cents']
        receipts=list(grouped.values())
        if receipts:
            heading('Tus pagos registrados'); table_header()
            for receipt in receipts:
                table_row('Pago del '+dated(receipt['received_at']),receipt['amount_cents'])
            y+=25
        forecasts=statement.get('forecasts',[])
        for kind,title in [('MSI','Tus próximas mensualidades'),('SUBSCRIPTION','Próximas suscripciones')]:
            items=[item for item in forecasts if item['kind']==kind]
            if items:
                heading(title)
                text(left,y,'Ya incluidas en lo que debes.' if kind=='MSI' else 'Todavía no incluidas en lo que debes.',9,color=muted)
                y+=18; table_header()
                for item in items: table_row(dated(item['due_date'])+' - '+item['description'],item['amount_cents'])
                y+=25
        for number,p in enumerate(document,1):
            theme.page_footer(p,number,len(document))
        document.set_metadata({'title':'Estado de cuenta - '+statement['person'],'creator':'Valenza - PDF familiar 2'})
        Path(path).write_bytes(document.tobytes(deflate=True))
    finally:
        document.close()
