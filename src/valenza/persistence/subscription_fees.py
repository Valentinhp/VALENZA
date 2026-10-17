"""Explicit, atomic reductions of previously posted subscription surcharges."""
import copy
import hashlib
import json
from datetime import datetime,timezone
from uuid import uuid4
from . import cash_review


def refresh_resumed_cut(repo,record,saved_data=None):
    """Refresh only proven fee reductions; never rewrite the historical source."""
    record=copy.deepcopy(record)
    saved_data=copy.deepcopy(saved_data)
    live={s['receivable_id']:s for s in repo.list_collection_items()}
    events=repo.database.connection.execute("""SELECT entity_id,old_value,new_value
        FROM audit_event WHERE entity_type='order'
        AND action='SUBSCRIPTION_SURCHARGE_REDUCED' ORDER BY rowid""").fetchall()
    for row in record['rows']:
        item=row['item'];current=live.get(item['receivable_id'])
        if not current:continue
        original=item['sale_cents'];value=original
        for event in events:
            if event['entity_id']!=item.get('order_id'):continue
            old=json.loads(event['old_value']);new=json.loads(event['new_value'])
            if old.get('user_id')==item['user_id'] and old.get('sale_cents')==value:
                value=new['sale_cents']
        if value==original or value!=current['sale_cents']:continue
        item.update(sale_cents=value,paid_cents=current['paid_cents'],remaining_cents=current['remaining_cents'])
        for contribution in row['contributions']:
            if contribution['included'] and contribution['amount_cents']==original:
                contribution['amount_cents']=value
        if saved_data is not None:
            for entry in saved_data.get('manual_counts',[]):
                if (entry['receivable_id']==item['receivable_id'] and
                    entry.get('selection_mode')!='PARTIAL' and entry['amount_cents']==original):
                    entry.update(amount_cents=value,selection_mode='FULL')
    return record,saved_data


def preview(repo,subscription_id,fees):
    if any(type(v) is not int or v<0 for v in fees.values()):
        raise ValueError('Los recargos deben ser importes no negativos.')
    connection=repo.database.connection
    shares={s['receivable_id']:s for s in repo.list_collection_items()}
    changes=[]
    rows=connection.execute('''SELECT sc.order_id,sc.cycle_date,o.merchant,o.instrument_id,
        ss.user_id,p.name,ss.amount_cents,r.id AS receivable_id,r.sale_cents
        FROM subscription_surcharge ss JOIN subscription_charge sc ON sc.order_id=ss.order_id
        JOIN order_record o ON o.id=sc.order_id JOIN person p ON p.id=ss.user_id
        LEFT JOIN receivable r ON r.order_id=ss.order_id AND r.user_id=ss.user_id
        WHERE sc.subscription_id=? AND o.order_status='ACTIVE'
        ORDER BY sc.cycle_date,sc.order_id,ss.user_id''',(subscription_id,)).fetchall()
    for row in rows:
        old=row['amount_cents'];new=min(old,fees.get(row['user_id'],0))
        if new==old:continue
        share=shares.get(row['receivable_id'])
        delta=new-old
        blocked=''
        if share is None:blocked='No se encuentra la cuenta por cobrar de este cargo.'
        elif row['sale_cents']+delta<0 or share['sale_cents']+delta<share['paid_cents']:
            blocked='Tiene abonos que superarían el nuevo importe; requiere revisar ese excedente.'
        changes.append(dict(order_id=row['order_id'],cycle_date=row['cycle_date'],merchant=row['merchant'],
            card_id=row['instrument_id'],user_id=row['user_id'],name=row['name'],receivable_id=row['receivable_id'],
            old_fee=old,new_fee=new,delta_cents=delta,
            old_sale=share['sale_cents'] if share else 0,new_sale=share['sale_cents']+delta if share else 0,
            paid_cents=share['paid_cents'] if share else 0,blocked=blocked))
    cash_updates=[]
    for card in sorted({c['card_id'] for c in changes}):
        revision,data=cash_review.latest(repo,card)
        if not data or 'manual_counts' not in data:continue
        updated=copy.deepcopy(data)
        by_id={c['receivable_id']:c for c in changes if c['card_id']==card}
        for entry in updated['manual_counts']:
            change=by_id.get(entry['receivable_id'])
            if change and entry['amount_cents']==change['old_sale'] and entry.get('selection_mode')!='PARTIAL':
                entry['amount_cents']=change['new_sale']
                entry['selection_mode']='FULL'
        updated['manual_counts']=[e for e in updated['manual_counts'] if e['amount_cents']>0]
        for row in updated.get('resumed_cut',{}).get('rows',[]):
            item=row['item'];change=by_id.get(item['receivable_id'])
            if not change:continue
            item.update(sale_cents=change['new_sale'],paid_cents=change['paid_cents'],
                remaining_cents=change['new_sale']-change['paid_cents'])
            for contribution in row['contributions']:
                if contribution['included'] and contribution['amount_cents']==change['old_sale']:
                    contribution['amount_cents']=max(0,change['new_sale'])
        if updated!=data:
            if not any(c['blocked'] for c in changes):cash_review.validate_snapshot(updated)
            cash_updates.append(dict(card_id=card,revision=revision,old=data,new=updated))
    state=dict(changes=changes,cash_updates=cash_updates)
    state['token']=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    return state


def apply(repo,plan,actor):
    connection=repo.database.connection
    blocked=[c for c in plan['changes'] if c['blocked']]
    if blocked:
        first=blocked[0]
        raise ValueError(first['name']+' · '+first['merchant']+': '+first['blocked'])
    for change in plan['changes']:
        if change['new_fee']:
            connection.execute('UPDATE subscription_surcharge SET amount_cents=? WHERE order_id=? AND user_id=?',
                (change['new_fee'],change['order_id'],change['user_id']))
        else:
            connection.execute('DELETE FROM subscription_surcharge WHERE order_id=? AND user_id=?',
                (change['order_id'],change['user_id']))
        connection.execute('UPDATE receivable SET sale_cents=sale_cents+? WHERE id=?',
            (change['delta_cents'],change['receivable_id']))
        repo._insert_person_audit(connection,change['order_id'],'SUBSCRIPTION_SURCHARGE_REDUCED',actor,
            dict(user_id=change['user_id'],surcharge_cents=change['old_fee'],sale_cents=change['old_sale']),
            dict(user_id=change['user_id'],surcharge_cents=change['new_fee'],sale_cents=change['new_sale']),
            entity_type='order')
    for update in plan['cash_updates']:
        connection.execute('''INSERT INTO audit_event
            (id,entity_type,entity_id,action,occurred_at,actor,reason,old_value,new_value)
            VALUES (?,'cash_review',?,'SAVED',?,?,?,?,?)''',
            (str(uuid4()),update['card_id'],datetime.now(timezone.utc).isoformat(),actor,
             'Actualización explícita de recargos; conserva parciales y versiones anteriores',
             json.dumps(update['old'],sort_keys=True),json.dumps(update['new'],sort_keys=True)))
