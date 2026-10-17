"""Independent preparation calculator; saved files never create money movements."""
from datetime import date, datetime, timezone
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QScrollArea, QWidget, QProgressBar, QFileDialog,
)

from valenza.gui.person_receipts import cents
from valenza.gui.warm_finance import apply_warm_surface, format_money
from valenza.gui.preparation_record import FORMAT, MAX_CENTS, save_record, load_record


def monthly_products(products, amount):
    """Planning allocation in integer cents; never an allocation of real receipts."""
    total = sum(p['amount_cents'] for p in products)
    if not total:
        return []
    shares = [p['amount_cents']*amount//total for p in products]
    residual = amount-sum(shares)
    ranked = sorted(range(len(products)), key=lambda i: -(products[i]['amount_cents']*amount % total))
    for index in ranked[:residual]:
        shares[index] += 1
    return [dict(p, total_share_cents=p.get('total_share_cents',p['amount_cents']), amount_cents=shares[i])
            for i,p in enumerate(products)]


def product_installment_schedule(products, count):
    """Plan-only breakdown preserving both product and installment margins."""
    if type(count) is not int or not 1 <= count <= 60:
        raise ValueError('Número de mensualidades inválido.')
    total = sum(p['amount_cents'] for p in products)
    each, residue = divmod(total, count)
    remaining = [dict(p) for p in products]
    schedule = []
    for number in range(count):
        row = (monthly_products(remaining, each + (number < residue))
               if sum(p['amount_cents'] for p in remaining) else [dict(p) for p in remaining])
        schedule.append([dict(p, total_share_cents=products[i]['amount_cents']) for i,p in enumerate(row)])
        for i,p in enumerate(row):
            remaining[i]['amount_cents'] -= p['amount_cents']
    return schedule


def preparation_items(repository, instrument_id, *, as_of=None):
    """Use existing adjusted participations and receipt applications, once each."""
    connection = repository.database.connection
    as_of = as_of or date.today()
    participations = repository.list_collection_items()
    planned = repository.upcoming_obligations(participations=participations)
    orders = {r['id']: r['instrument_id'] for r in connection.execute(
        'SELECT id,instrument_id FROM order_record')}
    purchases = {r['id']: r['instrument_id'] for r in connection.execute(
        'SELECT id,instrument_id FROM purchase')}
    result, seen = [], set()
    for item in participations:
        key = item['receivable_id']
        source = (orders.get(item['order_id']) if item.get('order_id')
                  else purchases.get(item.get('purchase_id')))
        if (source != instrument_id or item['participant_role'] not in ('FAMILY', 'PERSONAL')
                or key in seen or not (item['sale_cents'] or item['paid_cents'])):
            continue
        seen.add(key)
        item = dict(item)
        products = []
        if item.get('order_id'):
            order = repository.get_order(item['order_id'])
            source_products = order['manual_concepts'] or (order['import_evidence'] or {}).get('products', [])
            for index, product in enumerate(source_products):
                shares = product.get('allocations', {})
                if isinstance(shares, list):
                    shares = {s['user_id']: s['amount_cents'] for s in shares}
                share = shares.get(item['user_id'], 0)
                if share > 0:
                    products.append(dict(product_id=f'product:{index}', description=product['description'],
                                         quantity=product.get('quantity'), amount_cents=share))
        elif item.get('purchase_id'):
            products = [dict(r) for r in connection.execute(
                'SELECT p.id AS product_id,p.description,p.quantity,a.share_cents AS amount_cents '
                'FROM purchase_product p JOIN purchase_allocation a ON a.product_id=p.id '
                'WHERE p.purchase_id=? AND a.user_id=? AND a.share_cents>0 ORDER BY p.id',
                (item['purchase_id'], item['user_id']))]
        if products:
            item['products'] = products
        if item.get('order_id') and (order.get('purchase_mode') == 'MSI' or order.get('financing_plan')):
            installments = order.get('installments', [])
            entries = [f for f in planned if f['kind'] == 'MSI' and f['source_id'] == item['order_id']
                       and f['user_id'] == item['user_id']]
            for installment in installments:
                due = installment['due_date']
                if not due or due[:7] != as_of.strftime('%Y-%m'):
                    continue
                entry = next((e for e in entries if e['due_date'] == due), None)
                if not entry:
                    continue  # Already covered by the existing receipt application rule.
                current = entry['amount_cents']
                monthly_item = dict(item, is_msi=True, preparation_period=as_of.strftime('%Y-%m'),
                    original_receivable_id=key, receivable_id=f"{key}:msi:{installment['id']}",
                    installment_id=installment['id'], installment_number=installment['number'],
                    installment_count=len(installments), installment_due=due,
                    source_name=f"{item['source_name']} · Mensualidad {installment['number']}/{len(installments)}",
                    total_sale_cents=item['sale_cents'], total_paid_cents=item['paid_cents'],
                    total_remaining_cents=item['remaining_cents'],
                    sale_cents=current, paid_cents=0, remaining_cents=current, msi_dates_missing=False)
                if products:
                    if sum(p['amount_cents'] for p in products) == item['sale_cents']:
                        schedule = product_installment_schedule(products, len(installments))
                        gross_products = schedule[installment['number'] - 1]
                        monthly_item['products'] = monthly_products(gross_products, current)
                    else:
                        monthly_item.pop('products', None)
                        monthly_item['msi_product_mismatch'] = True
                result.append(monthly_item)
            undated = not installments or any(e['due_date'] is None for e in entries)
            if undated:
                item.update(is_msi=True, preparation_period=as_of.strftime('%Y-%m'),
                            total_sale_cents=item['sale_cents'], total_paid_cents=item['paid_cents'],
                            total_remaining_cents=item['remaining_cents'],
                            sale_cents=0, paid_cents=0, remaining_cents=0, msi_dates_missing=True)
                item.pop('products', None)
                result.append(item)
            continue
        result.append(item)
    return result


class PaymentPreparationDialog(QDialog):
    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.rows = []
        self.setWindowTitle('Preparar pago del mes')
        self.resize(760, 650)
        apply_warm_surface(self, 'paymentPreparation')
        layout = QVBoxLayout(self)
        title = QLabel('Preparar pago del mes')
        title.setObjectName('sectionTitle')
        layout.addWidget(title)
        notice = QLabel(f"MSI: solo el pendiente de las mensualidades de {date.today():%Y-%m}. "
                        'Despliega persona → pedido → productos. Marca artículos o usa «Incluir pedido» para seleccionar todos. '
                        'Sin productos se usa el pendiente del pedido. Es una calculadora; no registra cobros ni pagos reales.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        header = QHBoxLayout()
        self.card = QComboBox()
        self.card.setAccessibleName('Tarjeta para preparar el pago')
        for item in repository.list_all_instruments():
            if item['instrument_type'] in ('CREDIT_CARD', 'CREDIT_LINE'):
                self.card.addItem(f"{item['institution_name']} · {item['alias']}", item['id'])
        header.addWidget(self.card, 1)
        header.addWidget(QLabel('Objetivo (MXN)'))
        self.target = QLineEdit()
        self.target.setPlaceholderText('Escribe cuánto quieres reunir')
        self.target.setAccessibleName('Objetivo manual del pago en MXN')
        header.addWidget(self.target)
        layout.addLayout(header)
        record_header = QHBoxLayout()
        self.record_name = QLineEdit('Preparación del pago')
        self.record_name.setAccessibleName('Nombre del corte de preparación')
        self.record_date = QLineEdit(date.today().isoformat())
        self.record_date.setAccessibleName('Fecha del corte de preparación AAAA-MM-DD')
        record_header.addWidget(QLabel('Nombre'))
        record_header.addWidget(self.record_name, 1)
        record_header.addWidget(QLabel('Fecha'))
        record_header.addWidget(self.record_date)
        layout.addLayout(record_header)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        own = QHBoxLayout()
        own.addWidget(QLabel('Dinero extra (MXN)'))
        self.own = QLineEdit('0.00')
        self.own.setAccessibleName('Dinero adicional, sin repetir lo seleccionado en mis pedidos')
        self.own.setToolTip('Tu parte ya aparece en tus pedidos. Usa este campo solo para dinero adicional que no hayas incluido arriba.')
        own.addWidget(self.own)
        layout.addLayout(own)
        hint = QLabel('Tu parte aparece junto a las demás personas. Dinero extra solo suma aportaciones adicionales. '
                      'Cobros como referencia, sin cambios contables. Guarda antes de salir; '
                      'al abrir un corte se recupera su fotografía, sin movimientos posteriores.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.record_status = QLabel('Sin guardar · el archivo de preparación se guarda como JSON legible.')
        self.record_status.setWordWrap(True)
        layout.addWidget(self.record_status)
        actions = QHBoxLayout()
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.reject)
        open_button = QPushButton('Abrir corte')
        open_button.clicked.connect(self.open_cut)
        self.save_button = QPushButton('Guardar corte')
        self.save_button.clicked.connect(self.save_cut)
        self.continue_button = QPushButton('Ir a Tarjetas')
        self.continue_button.setObjectName('primaryAction')
        self.continue_button.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(open_button)
        actions.addWidget(self.save_button)
        actions.addStretch()
        actions.addWidget(self.continue_button)
        layout.addLayout(actions)
        self.card.currentIndexChanged.connect(self.load_card)
        self.target.textChanged.connect(self.recalculate)
        self.own.textChanged.connect(self.recalculate)
        self.record_name.textChanged.connect(self.recalculate)
        self.record_date.textChanged.connect(self.recalculate)
        self.load_card()

    def load_card(self):
        # A card change starts a fresh preparation: funds cannot leak across cards.
        self._msi_basis = 'installment-rows-v2'
        self.rows = []
        self.target.clear()
        self.own.setText('0.00')
        self.render_items(preparation_items(self.repository, self.card.currentData()))

    def render_items(self, items):
        self.rows = []
        body = QWidget()
        groups = QVBoxLayout(body)
        people = {}
        for item in items:
            people.setdefault(item['user_id'], []).append(item)
        for items in people.values():
            personal = ' · Mi parte' if any(i.get('participant_role') == 'PERSONAL' for i in items) else ''
            toggle = QPushButton(f"{items[0]['user_name']}{personal} · {len(items)} pedidos ▸")
            toggle.setCheckable(True)
            groups.addWidget(toggle)
            person = QWidget()
            person_layout = QVBoxLayout(person)
            person.hide()
            toggle.toggled.connect(person.setVisible)
            groups.addWidget(person)
            for item in items:
                heading = QHBoxLayout()
                quick = QCheckBox('Incluir mensualidad' if item.get('is_msi') else 'Incluir pedido')
                quick.setAccessibleName(f"Incluir pedido {item['source_name']} de {item['user_name']}")
                heading.addWidget(quick)
                basis = item['sale_cents'] if item.get('products') else max(0, item['remaining_cents'])
                basis_label = 'Sus productos' if item.get('products') else 'Pendiente'
                if item.get('is_msi'):
                    basis_label = f"MSI {item['preparation_period']}"
                order_toggle = QPushButton(f"{item['source_name']} · {basis_label}: {format_money(basis)} · Ver detalle ▸")
                order_toggle.setCheckable(True)
                heading.addWidget(order_toggle, 1)
                person_layout.addLayout(heading)
                box = QWidget()
                box.hide()
                order_toggle.toggled.connect(box.setVisible)
                order_layout = QVBoxLayout(box)
                label = QLabel(f"Le corresponde: {format_money(item['sale_cents'])} · "
                               f"Entregado: {format_money(item['paid_cents'])} · "
                               f"Pendiente de cobrar: {format_money(item['remaining_cents'])}")
                label.setWordWrap(True)
                if item.get('is_msi'):
                    label.setText(f"MSI · {item['preparation_period']} · "
                                  f"{'Vence: '+item['installment_due']+' · ' if item.get('installment_due') else ''}"
                                  f"Pendiente de esta mensualidad: {format_money(item['remaining_cents'])}. "
                                  'No incluye el resto de la compra.')
                order_layout.addWidget(label)
                row = dict(item=item, contributions=[], layout=order_layout, quick=quick)
                quick.clicked.connect(lambda included, r=row: self.toggle_order(r, included))
                self.rows.append(row)
                row['available'] = QLabel()
                order_layout.addWidget(row['available'])
                if item.get('msi_dates_missing'):
                    warning = QLabel('Hay cuotas sin fecha: configura sus vencimientos para identificar la mensualidad de este mes. No se incluye el principal completo.')
                    warning.setWordWrap(True)
                    order_layout.addWidget(warning)
                    quick.setEnabled(False)
                if item.get('msi_product_mismatch'):
                    warning = QLabel('El desglose de productos no cuadra con la participación ajustada. Se muestra solo la mensualidad del pedido, sin inventar repartos por producto.')
                    warning.setWordWrap(True)
                    order_layout.addWidget(warning)
                products = item.get('products', [])
                if products:
                    quick.setToolTip('Marca todos los productos de esta persona; los cobros no se reparten entre ellos.')
                    product_total = sum(p['amount_cents'] for p in products)
                    row['mismatch'] = product_total != item['sale_cents']
                    note = QLabel('Productos: importes correspondientes a esta persona. Los cobros del pedido '
                                  'no se distribuyen automáticamente entre productos.')
                    if item.get('is_msi'):
                        note.setText('Productos: reparto proporcional para preparar el pendiente MSI del mes, '
                                     'con centavos ajustados al total. Los cobros ya se contemplan en el pendiente mensual; '
                                     'este desglose no asigna cobros reales a productos.')
                    note.setWordWrap(True)
                    order_layout.addWidget(note)
                    if row['mismatch']:
                        warning = QLabel(f"Desglose: {format_money(product_total)} · Diferencia con la participación: "
                                         f"{format_money(item['sale_cents']-product_total)}. "
                                         'Revisa los productos individualmente; marcar todo está deshabilitado.')
                        warning.setWordWrap(True)
                        order_layout.addWidget(warning)
                        quick.setEnabled(False)
                    for product in products:
                        self.add_contribution(row, product)
                else:
                    order_layout.addWidget(QLabel('Mensualidad sin desglose de productos' if item.get('is_msi')
                                                 else 'Importe sin desglose de productos'))
                    add = QPushButton('Añadir aportación parcial')
                    add.clicked.connect(lambda checked=False, r=row: self.add_contribution(r))
                    add.setEnabled(not item.get('msi_dates_missing'))
                    order_layout.addWidget(add)
                    self.add_contribution(row)
                person_layout.addWidget(box)
        if not people:
            groups.addWidget(QLabel('No hay participaciones registradas para esta tarjeta.'))
        groups.addStretch()
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(body)
        self.recalculate()

    def toggle_order(self, row, included):
        if row['item'].get('products'):
            if row.get('mismatch'):
                return
            for checked, _, _ in row['contributions']:
                with QSignalBlocker(checked):
                    checked.setChecked(included)
            self.recalculate()
            return
        if not included:
            for checked, _, _ in row['contributions']:
                checked.setChecked(False)
        else:
            if not row['contributions']:
                self.add_contribution(row)
            checked, amount, _ = row['contributions'][0]
            try:
                value = cents(amount.text())
            except ValueError:
                value = 0
            if value == 0:
                pending = max(0, row['item']['remaining_cents'])
                amount.setText(f'{pending//100}.{pending%100:02d}')
            checked.setChecked(True)
        self.recalculate()

    def add_contribution(self, row, product=None):
        line = QHBoxLayout()
        checked = QCheckBox('Incluir')
        value = product['amount_cents'] if product else 0
        amount = QLineEdit(f'{value//100}.{value%100:02d}')
        if product:
            description = QLabel(product['description'] +
                                 (f" · Cantidad del producto: {product['quantity']}" if product.get('quantity') else '') +
                                 f" · {'Este mes' if row['item'].get('is_msi') else 'Su parte'}: {format_money(value)}")
            description.setWordWrap(True)
            description.setTextFormat(Qt.TextFormat.PlainText)
            row['layout'].addWidget(description)
            checked.setAccessibleName(f"Incluir producto {product['description']} de {row['item']['user_name']}")
        amount.setAccessibleName(f"Importe para calcular de {row['item']['user_name']} · {row['item']['source_name']}")
        remove = QPushButton('Quitar')
        line.addWidget(checked)
        line.addWidget(amount, 1)
        line.addWidget(remove)
        if product:
            remove.hide()
        row['layout'].addLayout(line)
        contribution = (checked, amount, remove)
        row['contributions'].append(contribution)
        checked.toggled.connect(self.recalculate)
        amount.textChanged.connect(self.recalculate)
        remove.clicked.connect(lambda: self.remove_contribution(row, contribution, line))
        if row['item'].get('msi_dates_missing'):
            checked.setEnabled(False)
            amount.setEnabled(False)
        self.recalculate()

    def remove_contribution(self, row, contribution, line):
        row['contributions'].remove(contribution)
        for widget in contribution:
            widget.deleteLater()
        row['layout'].removeItem(line)
        self.recalculate()

    def recalculate(self):
        errors = []
        family = 0
        for row in self.rows:
            selected = 0
            valid = True
            for index, (checked, amount, _) in enumerate(row['contributions']):
                try:
                    value = cents(amount.text())
                    if value > MAX_CENTS:
                        raise ValueError()
                    products = row['item'].get('products', [])
                    if products and value > products[index]['amount_cents']:
                        raise ValueError()
                    if checked.isChecked():
                        selected += value
                except ValueError:
                    valid = False
            if row['item'].get('is_msi') and selected > row['item']['remaining_cents']:
                valid = False
            if not valid:
                errors.append(f"{row['item']['user_name']} · {row['item']['source_name']}: "
                              'usa importes no negativos con hasta dos decimales; '
                              'un parcial no puede superar la parte del producto ni el pendiente MSI del mes.')
                selected = 0
            family += selected
            with QSignalBlocker(row['quick']):
                states = [c.isChecked() for c, _, _ in row['contributions']]
                if row['item'].get('products'):
                    row['quick'].setCheckState(Qt.CheckState.Checked if states and all(states) else
                                              Qt.CheckState.PartiallyChecked if any(states) else Qt.CheckState.Unchecked)
                else:
                    row['quick'].setChecked(any(states))
            row['available'].setText('Incluido en estas cuentas: ' + format_money(selected) +
                                     ' · Falta de la participación: ' + format_money(max(0, row['item']['sale_cents']-selected)))
        try:
            own = cents(self.own.text())
            if own > MAX_CENTS:
                raise ValueError()
        except ValueError:
            own = 0
            errors.append('Revisa Dinero extra: usa un importe no negativo con hasta dos decimales.')
        try:
            target = cents(self.target.text()) if self.target.text().strip() else None
            if target is not None and target > MAX_CENTS:
                raise ValueError()
        except ValueError:
            target = None
            errors.append('Revisa el objetivo: usa un importe no negativo con hasta dos decimales.')
        total = family + own
        self.total_cents = total
        self.summary.setText(f"Total incluido: {format_money(total)} · Por pedidos: {format_money(family)} · Dinero extra: {format_money(own)}\n"
                             + ('Escribe un objetivo manual para calcular el faltante.' if target is None else
                                f"Objetivo: {format_money(target)} · Faltante: {format_money(max(0, target-total))} · "
                                f"Sobrante: {format_money(max(0, total-target))}"))
        self.progress.setValue(min(100, total*100//target) if target else 0)
        try:
            date.fromisoformat(self.record_date.text().strip())
            if not self.record_name.text().strip():
                raise ValueError()
        except ValueError:
            errors.append('Escribe un nombre y una fecha válida para el corte (AAAA-MM-DD).')
        self.error.setText('\n'.join(errors))
        self.continue_button.setEnabled(not errors and target is not None and self.card.currentData() is not None)
        self.save_button.setEnabled(self.continue_button.isEnabled())
        self.record_status.setText('Cambios sin guardar · guarda en un archivo JSON legible para conservar estas cuentas.')

    def cut_record(self):
        return dict(format=FORMAT, msi_basis=self._msi_basis, name=self.record_name.text().strip(), date=self.record_date.text().strip(),
                    saved_at=datetime.now(timezone.utc).isoformat(), card_id=self.card.currentData(),
                    card_label=self.card.currentText(), target_cents=cents(self.target.text()),
                    own_cents=cents(self.own.text()), rows=[dict(item=row['item'], contributions=[
                        dict(amount_cents=cents(amount.text()), included=checked.isChecked())
                        for checked, amount, _ in row['contributions']]) for row in self.rows])

    def save_cut(self):
        self.recalculate()
        if not self.save_button.isEnabled():
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar corte de preparación',
            f'preparacion-{self.record_date.text()}.json', 'Corte de preparación (*.json)')
        if not path:
            return
        try:
            save_record(path, self.cut_record())
            self.record_status.setText(f'Corte guardado: {path}')
        except (OSError, ValueError) as error:
            self.error.setText(f'No se pudo guardar el corte: {error}')

    def open_cut(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Abrir corte de preparación', '',
                                             'Corte de preparación (*.json)')
        if not path:
            return
        try:
            record = load_record(path)
        except (OSError, ValueError) as error:
            self.error.setText(f'No se pudo abrir el corte: {error}')
            return
        converted = False
        if record.get('msi_basis') != 'installment-rows-v2':
            msi_ids = {r[0] for r in self.repository.database.connection.execute(
                "SELECT o.id FROM order_record o WHERE o.purchase_mode='MSI' OR EXISTS "
                '(SELECT 1 FROM financing_plan f WHERE f.order_id=o.id)')}
            old_msi = [r for r in record['rows'] if r['item'].get('is_msi') or r['item'].get('order_id') in msi_ids]
            if old_msi:
                source_ids = {r['item'].get('order_id') for r in old_msi}
                new_rows = [r for r in record['rows'] if r not in old_msi]
                for item in preparation_items(self.repository, record['card_id']):
                    if item.get('order_id') not in source_ids or not item.get('is_msi'):
                        continue
                    amounts = ([p['amount_cents'] for p in item['products']] if item.get('products')
                               else [item['remaining_cents']])
                    new_rows.append(dict(item=item, contributions=[dict(amount_cents=a, included=False) for a in amounts]))
                record = dict(record, rows=new_rows)
                converted = True
            record = dict(record, msi_basis='installment-rows-v2')
        with QSignalBlocker(self.card):
            index = self.card.findData(record['card_id'])
            if index < 0:
                self.card.addItem(record['card_label'], record['card_id'])
                index = self.card.count() - 1
            self.card.setCurrentIndex(index)
        self.render_items([r['item'] for r in record['rows']])
        self._msi_basis = record.get('msi_basis', 'legacy')
        saved_rows = {r['item']['receivable_id']: r for r in record['rows']}
        for row in self.rows:
            saved = saved_rows[row['item']['receivable_id']]
            if row['item'].get('products'):
                for (checked, amount, _), contribution in zip(row['contributions'], saved['contributions']):
                    value = contribution['amount_cents']
                    amount.setText(f'{value//100}.{value%100:02d}')
                    checked.setChecked(contribution['included'])
                continue
            # The initial empty contribution is only a convenience for new rows.
            first = row['contributions'][0]
            first[2].click()
            for contribution in saved['contributions']:
                self.add_contribution(row)
                checked, amount, _ = row['contributions'][-1]
                amount.setText(f"{contribution['amount_cents']//100}.{contribution['amount_cents']%100:02d}")
                checked.setChecked(contribution['included'])
        self.record_name.setText(record['name'])
        self.record_date.setText(record['date'])
        self.target.setText(f"{record['target_cents']//100}.{record['target_cents']%100:02d}")
        self.own.setText(f"{record['own_cents']//100}.{record['own_cents']%100:02d}")
        self.recalculate()
        self.record_status.setText(f"Fotografía guardada el {record['saved_at']} · {path}")
        if converted:
            self.record_status.setText('MSI del corte anterior separados en las mensualidades actuales. '
                                      'Revisa y marca sus casillas de nuevo. El archivo original no cambió; guarda si quieres conservar esta versión.')

    def done(self, result):
        # Explicitly discard the entire temporary draft on every exit path.
        super().done(result)
        self.rows.clear()
        body = self.scroll.takeWidget()
        if body is not None:
            body.deleteLater()
        self.target.clear()
        self.own.setText('0.00')
        self.recalculate()
        self.total_cents = 0
