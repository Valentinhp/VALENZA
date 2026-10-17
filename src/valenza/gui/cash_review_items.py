"""Monthly references for the independent cash checklist, without ledger writes."""
from datetime import date
from valenza.gui.payment_preparation import product_installment_schedule


def cash_review_items(repository,card_id,*,as_of=None):
    period=(as_of or date.today()).strftime('%Y-%m')
    connection=repository.database.connection
    cards={r['id']:r['instrument_id'] for r in connection.execute('SELECT id,instrument_id FROM order_record')}
    purchases={r['id']:r['instrument_id'] for r in connection.execute('SELECT id,instrument_id FROM purchase')}
    orders={};result=[]
    for original in repository.list_collection_items():
        order_id=original.get('order_id')
        instrument=cards.get(order_id) if order_id else purchases.get(original.get('purchase_id'))
        if instrument!=card_id:continue
        if not order_id:
            result.append(dict(original));continue
        if order_id not in orders:orders[order_id]=repository.get_order(order_id)
        order=orders[order_id]
        if not (order.get('financing_plan') or order.get('purchase_mode')=='MSI'):
            result.append(dict(original));continue
        installments=order.get('installments',[])
        if not installments or any(not i['due_date'] for i in installments):
            result.append(dict(original,is_msi=True,msi_dates_missing=True,
                preparation_period=period,original_receivable_id=original['receivable_id'],
                receivable_id=original['receivable_id']+':msi:undated:'+period,
                source_name=original['source_name']+' · MSI sin fecha: mensualidad por confirmar',
                sale_cents=0,remaining_cents=0,total_sale_cents=original['sale_cents'],
                total_paid_cents=original['paid_cents'],total_remaining_cents=original['remaining_cents']))
            if not installments:continue
        # Same integer-cent distribution as the existing family schedule;
        # reference remains visible even when receipts already cover it.
        each,residue=divmod(original['sale_cents'],len(installments))
        paid=original['paid_cents']
        source_products=order['manual_concepts'] or (order['import_evidence'] or {}).get('products',[])
        products=[]
        for index,product in enumerate(source_products):
            shares=product.get('allocations',{})
            if isinstance(shares,list):shares={a['user_id']:a['amount_cents'] for a in shares}
            amount=shares.get(original['user_id'],0)
            if amount:products.append(dict(product_id=f'product:{index}',description=product['description'],
                quantity=product.get('quantity'),amount_cents=amount))
        schedule=(product_installment_schedule(products,len(installments))
                  if products and sum(p['amount_cents'] for p in products)==original['sale_cents'] else [])
        for index,installment in enumerate(installments):
            amount=each+(index<residue);used=min(paid,amount);paid-=used
            if not installment['due_date'] or installment['due_date'][:7]!=period:continue
            item=dict(original,is_msi=True,preparation_period=period,msi_dates_missing=False,
                original_receivable_id=original['receivable_id'],
                receivable_id=f"{original['receivable_id']}:msi:{installment['id']}",
                installment_id=installment['id'],installment_number=installment['number'],
                installment_count=len(installments),installment_due=installment['due_date'],
                source_name=f"Mensualidad {installment['number']}/{len(installments)} · {period}\n{original['source_name']}",
                total_sale_cents=original['sale_cents'],total_paid_cents=original['paid_cents'],
                total_remaining_cents=original['remaining_cents'],sale_cents=amount,
                paid_cents=used,remaining_cents=max(0,amount-used))
            if schedule:item['products']=schedule[index]
            result.append(item)
    return result
