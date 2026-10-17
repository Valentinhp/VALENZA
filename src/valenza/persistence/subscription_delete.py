"""Explicit deletion of a subscription and its exclusively owned records."""
import copy
import hashlib
import json


def preview(repo,identity):
    c=repo.database.connection
    sub=c.execute('SELECT * FROM subscription WHERE id=?',(identity,)).fetchone()
    if sub is None:raise ValueError('La suscripción ya no existe.')
    orders=[r[0] for r in c.execute('SELECT order_id FROM subscription_charge WHERE subscription_id=? ORDER BY order_id',(identity,))]
    accounts=[];payments=set();blocked=[]
    for order in orders:
        accounts.extend(r[0] for r in c.execute('SELECT id FROM receivable WHERE order_id=?',(order,)))
        if c.execute('SELECT 1 FROM imported_product_refund WHERE order_id=?',(order,)).fetchone() or c.execute('SELECT 1 FROM product_refund_repurchase WHERE order_id=?',(order,)).fetchone():
            blocked.append('Hay devoluciones o recompras vinculadas; no se borrarán automáticamente.')
        if c.execute('SELECT 1 FROM financing_plan WHERE order_id=?',(order,)).fetchone():
            blocked.append('Hay cuotas MSI vinculadas; no se borrarán automáticamente.')
    for account in accounts:
        payments.update(r[0] for r in c.execute('SELECT payment_id FROM receipt_application WHERE receivable_id=?',(account,)))
    for payment in sorted(payments):
        if any(r[0] not in accounts for r in c.execute('SELECT receivable_id FROM receipt_application WHERE payment_id=?',(payment,))):
            blocked.append('Un abono también cubre otros pedidos. No se puede eliminar sin revisar ese reparto.')
    state=dict(subscription=dict(sub),orders=orders,accounts=sorted(accounts),payments=sorted(payments),blocked=sorted(set(blocked)))
    # Include all persisted state: fail closed if anything changed after review/backup.
    state['token']=hashlib.sha256(json.dumps([
        [r[0],[list(row) for row in c.execute('SELECT * FROM "'+r[0]+'" ORDER BY rowid')]]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    ],sort_keys=True).encode()).hexdigest()
    return state


def _clean_review(value,orders,accounts):
    data=copy.deepcopy(value)
    def related(key):
        return isinstance(key,str) and any(key==a or key.startswith(a+':msi:') for a in accounts)
    if 'manual_counts' in data:
        data['manual_counts']=[e for e in data['manual_counts'] if not related(e['receivable_id'])]
    if 'entries' in data:
        data['entries']=[e for e in data['entries'] if not related(json.loads(e['key'])[1])]
    if 'checked_products' in data:
        data['checked_products']=[k for k in data['checked_products'] if not any(related(v) for v in json.loads(k))]
    if data.get('resumed_cut'):
        data['resumed_cut']['rows']=[r for r in data['resumed_cut']['rows']
            if r['item'].get('order_id') not in orders and not related(r['item']['receivable_id'])]
    return data


def delete(repo,identity,*,expected_token,backup_path):
    c=repo.database.connection
    if c.in_transaction:raise ValueError('Finaliza la operación actual antes de eliminar.')
    plan=preview(repo,identity)
    if plan['blocked']:raise ValueError(plan['blocked'][0])
    if plan['token']!=expected_token:raise ValueError('Los datos cambiaron; vuelve a revisar la eliminación.')
    repo.database.create_backup(backup_path)
    repo.database.verify_backup(backup_path)
    with repo.database.transaction():
        c.execute('BEGIN IMMEDIATE')
        current=preview(repo,identity)
        if current['token']!=expected_token:raise ValueError('Los datos cambiaron; vuelve a revisar la eliminación.')
        ids={identity,*plan['orders'],*plan['accounts'],*plan['payments']}
        for event in c.execute('SELECT rowid,* FROM audit_event').fetchall():
            if event['entity_id'] in ids:
                c.execute('DELETE FROM audit_event WHERE rowid=?',(event['rowid'],));continue
            if event['entity_type']=='cash_review':
                for column in ('old_value','new_value'):
                    if event[column] is None:continue
                    original=json.loads(event[column])
                    cleaned=_clean_review(original,plan['orders'],plan['accounts'])
                    if cleaned!=original:
                        c.execute('UPDATE audit_event SET '+column+'=? WHERE rowid=?',(json.dumps(cleaned,ensure_ascii=False),event['rowid']))
        for account in plan['accounts']:
            c.execute('DELETE FROM receipt_application WHERE receivable_id=?',(account,))
            c.execute('DELETE FROM receivable WHERE id=?',(account,))
        for payment in plan['payments']:c.execute('DELETE FROM user_payment WHERE id=?',(payment,))
        for key in ids:
            c.execute('DELETE FROM match_suggestion WHERE source_a_id=? OR source_b_id=?',(key,key))
        for order in plan['orders']:
            c.execute('DELETE FROM subscription_surcharge WHERE order_id=?',(order,))
        c.execute('DELETE FROM subscription_charge WHERE subscription_id=?',(identity,))
        for order in plan['orders']:
            c.execute('DELETE FROM order_allocation WHERE order_id=?',(order,))
            c.execute('DELETE FROM order_record WHERE id=?',(order,))
        c.execute('DELETE FROM subscription_allocation WHERE subscription_id=?',(identity,))
        c.execute('DELETE FROM subscription WHERE id=?',(identity,))
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('No se puede completar: quedarían vínculos inconsistentes.')
    return plan
