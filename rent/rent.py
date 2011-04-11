# -*- encoding: utf-8 -*-
#
# OpenERP Rent - Renting Module
# Copyright (C) 2010-2011 Thibaut DIRLIK <thibaut.dirlik@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import time
import logging
import math
import netsvc
import datetime

import openlib

from osv import osv, fields
from tools.translate import _
from tools.misc import cache, DEFAULT_SERVER_DATETIME_FORMAT
from decimal_precision import get_precision

_logger = logging.getLogger('rent')

UNITIES = (
    ('day', _('Day')),
    ('month', _('Month')),
    ('year', _('Year')),
)

UNITIES_FACTORS = {
    'day' : {
        'day' : 1.0,
        'month' : 30.0,
        'year' : 365.0,
    },
    'month' : {
        'day' : 1.0/30,
        'month' : 1.0,
        'year' : 12.0,
    },
    'year' : {
        'day' : 1.0/365,
        'month' : 1.0/30,
        'year' : 1,
    }
}

STATES = (
    ('draft', _('Quotation')), # Default state
    ('confirmed', _('Confirmed')), # Confirmed, have to generate invoices
    ('ongoing', _('Ongoing')), # Invoices generated, waiting for confirmation
    ('done', _('Done')), # All invoices have been confirmed
    ('cancelled', _('Cancelled')), # The order has been cancelled
)

PRODUCT_TYPE = (
    ('rent', _('Rent')),
    ('service', _('Service')),
)

class RentOrder(osv.osv):

    # A Rent Order is almost like a Sale Order except that the way we generate invoices
    # is really different, and there is a notion of duration. I decided to not inherit
    # sale.order because there were a lot of useless things for a Rent Order.

    @classmethod
    def register_invoice_period(cls, name, showed_name, method_name):

        """
        Register an invoice period and associate it a function.

        The method must accept these arguments :
            def get_invoices_for_monthly_period(self, cursor, user_id, order)
        And must return a dict of dates of invoices to generate.

        The order argument is the order object returned by a browse(). You can access it's data for checks.
        If there is any problem, the function can raise an osv.except_osc exception, which will abort invoice generation.
        """

        if not hasattr(cls, method_name):
            raise RuntimeError('Unkown method %s in register_invoice_period().' % method_name)

        cls._periods[name] = (showed_name, method_name)

    def on_client_changed(self, cursor, user_id, ids, client_id):

        """
        Called when the client has changed : we update all addresses fields :
        Order address, invoice address and shipping address.
        """

        result = {}
        client = self.pool.get('res.partner').browse(cursor, user_id, client_id)

        for address in client.address:
            
            if address.type == 'default':
                result = {
                    'partner_order_address_id' : address.id,
                    'partner_invoice_address_id' : address.id,
                    'partner_shipping_address_id' : address.id,
                }
            elif address.type == 'invoice':
                result['partner_invoice_address_id'] = address.id
            elif address.type == 'delivery':
                result['partner_shipping_address_id'] = address.id

        if not result:
            raise osv.except_osv (
                _('Client has not any address'), _('You must define a least one default address for this client.'))

        if client.property_account_position.id:
            result['fiscal_position'] = client.property_account_position.id



        return { 'value' : result }

    def on_draft_clicked(self, cursor, user_id, ids, context=None):

        """
        This method is called when the rent order is in cancelled state and the user clicked on 'Go back to draft'.
        """

        orders = self.browse(cursor, user_id, ids, context=context)
        wkf_service = netsvc.LocalService("workflow")

        # Update records
        self.write(cursor, user_id, ids, {
            'state' : 'draft',
        })

        for order in orders:

            # Delete and re-create the workflow
            wkf_service.trg_delete(user_id, 'rent.order', order.id, cursor)
            wkf_service.trg_create(user_id, 'rent.order', order.id, cursor)

        for id, name in self.name_get(cursor, user_id, ids):
            self.log(cursor, user_id, order.id, _('The Rent Order "%s" has been reset.') % name)

        return True

    def on_show_invoices_clicked(self, cursor, user_id, ids, context=None):

        """
        Show the invoices which have been generated.
        """

        order = self.browse(cursor, user_id, ids, context=context)[0]
        view_id = self.pool.get('ir.model.data').get_object_reference(cursor, user_id, 'account', 'invoice_form')
        view_id = view_id and view_id[1] or False
        view_xml_id = self.pool.get('ir.ui.view').get_xml_id(cursor, user_id, [view_id])[view_id]

        action = {
            'name': '%s Invoice(s)' % order.ref,
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'domain': [('origin', '=', order.ref)],
            'context' : {'form_view_ref' : view_xml_id}
        }

        if len(order.invoices_ids) == 1:
            action['res_id'] = order.invoices_ids[0].id
            action['view_mode'] = 'form,tree'
        
        return action

    def action_generate_out_move(self, cursor, user_id, orders_ids):

        """
        Create the stock moves of the specified orders objects. For each order, two picking are created :
            - An output picking, to send the product to the customer.
            - An input picking, to get the products back.
        """

        orders = self.browse(cursor, user_id, orders_ids)
        move_pool, picking_pool = map(
            self.pool.get, ('stock.move', 'stock.picking'))
        workflow = netsvc.LocalService("workflow")

        for order in orders:

            if order.out_picking_id:
                _logger.warning("Trying to create out move whereas it already exists.")
                continue

            out_picking_id = False

            warehouse_stock_id = order.shop_id.warehouse_id.lot_stock_id.id
            if order.partner_shipping_address_id.partner_id.property_stock_customer.id:
                customer_output_id = order.partner_shipping_address_id.partner_id.property_stock_customer.id
            else:
                customer_output_id = order.shop_id.warehouse_id.lot_output_id.id

            for line in order.rent_line_ids:

                if line.product_id.product_tmpl_id.type not in ('product', 'consu'):
                    _logger.info("Ignored product %s, not stockable." % line.product_id.name)
                    continue

                # We create picking only if there is at least one product to move.
                # That's why we do it after checking the product type, because it could be
                # service rent only.
                if not out_picking_id:

                    out_picking_id = picking_pool.create(cursor, user_id, {
                        'origin' : order.ref,
                        'type' : 'out',
                        'state' : 'auto',
                        'move_type' : 'one',
                        'invoice_state' : 'none',
                        'date' : fields.date.today(),
                        'address_id' : order.partner_shipping_address_id.id,
                        'company_id' : order.company_id.id,
                    })

                # Out move: Stock -> Client
                move_pool.create(cursor, user_id, {
                    'name': line.description,
                    'picking_id': out_picking_id,
                    'product_id': line.product_id.id,
                    'date': fields.date.today(),
                    'date_expected': order.date_out_shipping,
                    'product_qty': line.quantity,
                    'product_uom': line.product_id_uom.id,
                    'product_uos' : line.product_id_uom.id,
                    'product_uos_qty' : line.quantity,
                    'address_id': order.partner_shipping_address_id.id,
                    'location_id': warehouse_stock_id,
                    'location_dest_id' : customer_output_id,
                    'state': 'draft',
                })

            # Confirm picking orders
            if out_picking_id:
                workflow.trg_validate(user_id, 'stock.picking',
                    out_picking_id, 'button_confirm', cursor)
                self.write(cursor, user_id, order.id,
                    {'out_picking_id' : out_picking_id}),

                # Check assignement (TODO: This should be optional)
                picking_pool.action_assign(cursor, user_id, [out_picking_id])

        return True

    def action_ongoing(self, cursor, user_id, ids):

        """
        We switch to ongoing state when the out picking has been confirmed,
        and invoices have been generated. We have to generate the input picking.
        """

        orders = self.browse(cursor, user_id, ids)
        picking_pool, move_pool = map(
            self.pool.get, ('stock.picking', 'stock.move'))
        workflow = netsvc.LocalService("workflow")

        for order in orders:
            in_picking_id = picking_pool.create(cursor, user_id, {
                'origin' : order.out_picking_id.origin,
                'type' : 'in',
                'state' : 'auto',
                'move_type' : 'one',
                'invoice_state' : 'none',
                'date' : time.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                'address_id' : order.partner_shipping_address_id.id,
                'company_id' : order.company_id.id,
            })
            for line in order.out_picking_id.move_lines:
                move_pool.create(cursor, user_id, {
                    'name': line.name,
                    'picking_id': in_picking_id,
                    'product_id': line.product_id.id,
                    'date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    'date_expected': order.date_end_rent,
                    'product_qty': line.product_qty,
                    'product_uom': line.product_uom.id,
                    'product_uos' : line.product_uos.id,
                    'product_uos_qty' : line.product_uos_qty,
                    'address_id': line.address_id.id,
                    'location_id': line.location_dest_id.id,
                    'location_dest_id' : line.location_id.id,
                    'state': 'draft',
                })
            
            self.write(cursor, user_id, order.id,
                {'in_picking_id' : in_picking_id, 'state' : 'ongoing'})
            
            # Confirm the picking
            workflow.trg_validate(user_id, 'stock.picking',
                in_picking_id, 'button_confirm', cursor)

            # Check assignement (TODO: This should be optional)
            picking_pool.action_assign(cursor, user_id, [in_picking_id])
        
        return True

    def action_generate_invoices(self, cursor, user_id, ids):

        """
        This action is called by the workflow activity 'ongoing'. We generate an invoice for the duration period.
        The interval is the duration unity : if you rent for 2 Month, there will be 2 invoices.
        """

        orders = self.browse(cursor, user_id, ids)

        for order in orders:

            period_function = self._periods[order.rent_invoice_period][1]
            period_function = getattr(self, period_function)

            invoices_id = period_function(cursor, user_id, order)

        self.write(cursor, user_id, ids, {'invoices_ids' : [(6, 0, invoices_id)]})

        return True

    def action_cancel(self, cursor, user_id, ids):

        """
        If you cancel the order before invoices have been generated, it's ok.
        Else, you can cancel only if invoices haven't been confirmed yet.
        You can't cancel an order which have confirmed picking.
        """

        orders = self.browse(cursor, user_id, ids)

        for order in orders:

            if order.state in ('draft', 'confirmed', 'ongoing'):
                # Check invoices
                invoice_ids = []
                for invoice in order.invoices_ids:
                    if invoice.state not in ('draft', 'cancel'):
                        raise osv.except_osv(_("You can't cancel this order."),
                            _("This order have confirmed invoice, and can't be deleted right now."))
                    invoice_ids.append(invoice.id)

                # Check stock.picking objects
                shipping_exption = osv.except_osv(_("You can't cancel this order."),
                    _("This order have confirmed shipping orders !"))
                if order.out_picking_id.id and order.out_picking_id.state == 'done':
                    raise shipping_exption
                if order.in_picking_id.id and order.in_picking_id.state == 'done':
                    raise shipping_exption

                # Remove objects associated to this order
                picking_ids = [getattr(order, field).id for field in ('out_picking_id', 'in_picking_id')\
                                if getattr(order, field).id]
                self.write(cursor, user_id, order.id, {
                    'out_picking_id' : False,
                    'in_picking_id' : False,
                    'invoices_ids' : [(5)],
                    'state' : 'cancelled',
                })

                self.pool.get('account.invoice').unlink(cursor, user_id, invoice_ids)
                self.pool.get('stock.picking').unlink(cursor, user_id, picking_ids)
            else:
                raise osv.except_osv(_('Error'), _("You can't cancel an order in this state."))

        return True

    @cache(30)
    def get_duration_unities(self, cursor, user_id, context=None):

        """
        Return the duration unities depending of the company configuration.

        Note: We cache the result because it will certainly not change a lot,
        and it will cause a lot of useless queries on orders with a lot of lines.
        """

        min_unity = self.pool.get('res.users').browse(
            cursor, user_id, user_id).company_id.rent_unity
        result = []
        found = False

        for key, name in UNITIES:
            if key == min_unity:
                found = True
            if found:
                result.append((key, name))

        return result

    def get_order_from_lines(self, cursor, user_id, ids, context=None):

        """
        Returns lines ids associated to this order.
        """

        lines = self.pool.get('rent.order.line').browse(cursor, user_id, ids)
        return [line.order_id.id for line in lines]

    def get_end_date(self, cursor, user_id, ids, field_name, arg, context=None):

        """
        Returns the rent order end date, based on the duration.
        """

        orders = self.browse(cursor, user_id, ids, context=context)
        result = {}

        for order in orders:

            begin = datetime.datetime.strptime(order.date_begin_rent, DEFAULT_SERVER_DATETIME_FORMAT)
            duration = order.rent_duration
            days = duration * UNITIES_FACTORS['day'][order.rent_duration_unity]
            end = begin + datetime.timedelta(days=days)
            end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

            result[order.id] = end

        return result

    def get_invoiced_rate(self, cursor, user_id, ids, fields_name, arg, context=None):

        """
        Returns the percentage of invoices which have been confirmed.
        """

        orders = self.browse(cursor, user_id, ids, context=context)
        result = {}

        for order in orders:
            invoices_count = len(order.invoices_ids)
            if not invoices_count:
                result[order.id] = 0
                continue
            invoices_confirmed = len(
                [i for i in order.invoices_ids if i.state in ('open', 'paid')])
            result[order.id] = invoices_confirmed / invoices_count * 100.0
        return result

    def get_totals(self, cursor, user_id, ids, fields_name, arg, context=None):

        """
        Compute the total if the rent order, with taxes.
        """

        result = {}
        tax_pool, fiscal_position_pool = map(self.pool.get, ['account.tax', 'account.fiscal.position'])
        orders = self.browse(cursor, user_id, ids, context=context)

        for order in orders:

            total = 0.0
            total_with_taxes = 0.0
            total_taxes = 0.0
            total_taxes_with_discount = 0.0

            for line in order.rent_line_ids:

                # We map the tax_ids thanks to the fiscal position, if specified. Check account/partner.py
                # for the map_tax function used to do the mapping.
                tax_ids = line.tax_ids
                if order.fiscal_position.id:
                    tax_ids = tax_pool.browse(cursor, user_id, fiscal_position_pool.map_tax(
                        cursor, user_id, order.fiscal_position, tax_ids, context=context),context=context)
                
                # The compute_all function is defined in the account module  Take a look.
                prices = tax_pool.compute_all(cursor, user_id, tax_ids, line.real_price, line.quantity)

                total += prices['total']
                total_with_taxes += prices['total_included']
                total_taxes += math.fsum([tax.get('amount', 0.0) for tax in prices['taxes']])
                total_taxes_with_discount += math.fsum(
                    [tax.get('amount', 0.0) * (1 - (order.discount or 0.0) / 100.0) for tax in prices['taxes']])

            # We apply the global discount
            total_with_discount = total * (1 - (order.discount or 0.0) / 100.0)
            total_with_taxes_with_discount = total_with_discount + total_taxes_with_discount

            # TODO: When implementing priceslist, we will have to use currency.round() to round these numbers
            result[order.id] = {
                'total' : total,
                'total_with_taxes' : total_with_taxes,
                'total_taxes' : total_taxes,
                'total_taxes_with_discount' : total_taxes_with_discount,
                'total_with_discount' : total_with_discount,
                'total_with_taxes_with_discount' : total_with_taxes_with_discount,
            }

        return result

    def get_invoice_comment(self, cursor, user_id, order, date, current, max, period_begin, period_end):

        """
        This method must return a comment that will be added to the invoice.
        """

        partner_lang = openlib.partner.get_partner_lang(cursor, user_id, order.partner_id)
        datetime_format = partner_lang.date_format + _(' at ') + partner_lang.time_format

        begin_date = openlib.to_datetime(order.date_begin_rent).strftime(datetime_format)
        end_date = openlib.to_datetime(order.date_end_rent).strftime(datetime_format)

        period_begin = openlib.to_datetime(period_begin).strftime(datetime_format)
        period_end = openlib.to_datetime(period_end).strftime(datetime_format)

        return _(
            "Rental from %s to %s, invoice %d/%d.\n"
            "Invoice for the period from %s to %s."
        ) % (
            begin_date,
            end_date,
            current,
            max,
            period_begin,
            period_end,
        )

    def get_invoice_at(self, cursor, user_id, order, date, current, max, invoice_period_begin, invoice_period_end):

        """
        Generates an invoice at the specified date. The two last arguenbts current and max
        defines the maximum number of invoices and the current invoice number. For example: current=4, max=12.
        """

        invoice_pool, invoice_line_pool = map(self.pool.get, ('account.invoice', 'account.invoice.line'))

        # Create the invoice
        invoice_id = invoice_pool.create(cursor, user_id,
            {
                'name' : _('Invoice %d/%d') % (current, max),
                'origin' : order.ref,
                'type' : 'out_invoice',
                'state' : 'draft',
                'date_invoice' : date,
                'partner_id' : order.partner_id.id,
                'address_invoice_id' : order.partner_invoice_address_id.id,
                'account_id' : order.partner_id.property_account_receivable.id,
                'fiscal_position' : order.fiscal_position.id,
                'comment' : self.get_invoice_comment(
                    cursor, user_id, order, date, current, max, invoice_period_begin, invoice_period_end),
            }
        )

        # Create the lines
        lines_ids = [line.id for line in order.rent_line_ids]
        lines_data = self.pool.get('rent.order.line').get_invoice_lines_data(cursor, user_id, lines_ids)

        for line_data in lines_data:
            line_data['invoice_id'] = invoice_id
            invoice_line_pool.create(cursor, user_id, line_data)

        return invoice_id

    def get_invoice_periods(self, cursor, user_id, context=None):

        """
        Returns a list of available periods (which have been registered with register_invoice_period()).
        """

        return [(period, self._periods[period][0]) for period in self._periods]

    def get_invoices_for_once_period(self, cursor, user_id, order):

        """
        Generates only one invoice (at the end of the rent).
        """

        return [self.get_invoice_at(cursor, user_id, order,
            order.date_begin_rent, 1, 1, order.date_begin_rent, order.date_end_rent)]

    def test_have_invoices(self, cursor, user_id, ids, *args):

        """
        Method called by the workflow to test if the order have invoices.
        """

        return len(self.browse(cursor, user_id, ids[0]).invoices_ids) > 0

    def test_out_shipping_done(self, cursor, user_id, ids, *args):

        """
        Called by the workflow. Returns True once the product has been output shipped.
        """
        
        lines = self.browse(cursor, user_id, ids[0]).out_picking_id.move_lines or []

        return all(line.state == 'done' for line in lines)
    
    def test_in_shipping_done(self, cursor, user_id, ids, *args):

        """
        Called by the workflow. Returns True once the product has been input shipped.
        """
        
        return all(line.state == 'done' for line in self.browse(
            cursor, user_id, ids[0]).in_picking_id.move_lines)

    _name = 'rent.order'
    _sql_constraints = []
    _rec_name = 'ref'
    _periods = {}
    _order = 'date_created DESC,ref DESC'

    _columns = {
        'state' : fields.selection(STATES, _('State'), readonly=True, help=_(
            'Gives the state of the rent order :\n'
            '- Quotation\n-Confirmed\n-Ongoing (Products have been shipped)\n'
            '- Done (Products have been get back)')),
        'ref' : fields.char(_('Reference'), size=128, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The reference is a unique identifier that identify this order. ')),
        'date_created' : fields.datetime(_('Date'), readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Date of the creation of this order.')),
        'date_begin_rent' : fields.datetime(_('Rent begin date'), required=True,
            readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'Date of the begin of the leasing.')),
        'date_end_rent' : fields.function(get_end_date, type="datetime", method=True, string=_("Rent end date")),
        'rent_duration_unity' : fields.selection(get_duration_unities, _('Duration unity'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration unity, available choices depends of your company configuration.')),
        'rent_duration' : fields.integer(_('Duration'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration of the lease, expressed in selected unit.')),
        'rent_invoice_period' : fields.selection(get_invoice_periods, _('Invoice Period'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'Period between invoices')),
        'salesman' : fields.many2one('res.users', _('Salesman'), ondelete='SET NULL',
            readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The salesman who handle this order, optional.')),
        'shop_id': fields.many2one('sale.shop', 'Shop', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The shop where this order was created.'), ondelete='RESTRICT'),
        'company_id': fields.related('shop_id', 'company_id', type='many2one', relation='res.company',
            string=_('Company'), store=True, readonly=True),
        'partner_id': fields.many2one('res.partner', _('Customer'), required=True, change_default=True,
            domain=[('customer', '=', 'True')], context={'search_default_customer' : True},
            readonly=True, states={'draft' : [('readonly', False)]}, ondelete='RESTRICT', help=_(
            'Select a customer. Only partners marked as customer will be shown.')),
        'partner_invoice_address_id': fields.many2one('res.partner.address', _('Invoice Address'), readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=_(
            'Invoice address for current Rent Order.')),
        'partner_order_address_id': fields.many2one('res.partner.address', _('Ordering Address'), readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=_(
            'The name and address of the contact who requested the order or quotation.')),
        'partner_shipping_address_id': fields.many2one('res.partner.address', 'Shipping Address', readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=_(
            'Shipping address for current rent order.')),
        'rent_line_ids' : fields.one2many('rent.order.line', 'order_id', _('Order Lines'), readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Lines of this rent order.')),
        'notes': fields.text(_('Notes'), help=_(
            'Enter informations you want about this order.')),
        'discount' : fields.float(_('Global discount (%)'),
            readonly=True, states={'draft': [('readonly', False)]}, help=_(
            'Apply a global discount to this order.')),
        'fiscal_position' : fields.many2one('account.fiscal.position', _('Fiscal Position'), readonly=True,
            states={'draft': [('readonly', False)]}, ondelete='SET NULL', help=_(
            'Fiscal Position applied to taxes and accounts.')),
        'invoices_ids': fields.many2many('account.invoice', 'rent_order_invoices', 'rent_order_id', 'invoice_id',
            _('Invoices'), readonly=True),
        'invoiced_rate' : fields.function(get_invoiced_rate, string=_('Invoiced'), help=_(
            'Invoiced percent, calculated on the numver if invoices confirmed.'), method=True),
        'date_out_shipping' : fields.datetime(_('Shipping date'), readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Date of the shipping.')),
        'out_picking_id' : fields.many2one('stock.picking', _('Output picking id'), help=_(
            'The picking object which handle Stock->Client moves.'), ondelete='RESTRICT'),
        'in_picking_id' : fields.many2one('stock.picking', _('Input picking id'), help=_(
            'The picking object which handle Client->Stock moves.'), ondelete='RESTRICT'),
        'description' : fields.char(_('Object'), size=255, help=_(
            'A small description of the rent order. Used in the report.')),
        'total' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Untaxed amount"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Total"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Taxes"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Untaxed amount (with discount)"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Taxes (with discount)"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Total (with discount)"), digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
    }

    _defaults = {
        'date_created': fields.datetime.now,
        'date_begin_rent': fields.datetime.now,
        'date_out_shipping': fields.datetime.now,
        'state':
            'draft',
        'salesman': # Default salesman is the curent user
            lambda self, cursor, user_id, context: user_id,
        'ref': # The ref sequence is defined in sequence.xml (Default: RENTXXXXXXX)
            lambda self, cursor, user_id, context:
                self.pool.get('ir.sequence').get(cursor, user_id, 'rent.order'),
        'rent_duration_unity' :
            lambda self, cursor, user_id, context: self.get_duration_unities(cursor, user_id, context)[0][0],
        'rent_duration' : 1,
        'rent_invoice_period' : 'once',
        'shop_id' : 1, # TODO: Use ir.values to handle multi-company configuration
        'discount' : 0.0,

    }

    _sql_constraints = [
        ('ref_uniq', 'unique(ref)', _('Rent Order reference must be unique !')),
        #('valid_created_date', 'check(date_created >= CURRENT_DATE)', _('The date must be today of later.')),
        #('valid_begin_date', 'check(date_begin_rent >= CURRENT_DATE)', _('The begin date must be today or later.')),
        ('begin_after_create', 'check(date_begin_rent >= date_created)', _('The begin date must later than the order date.')),
        ('valid_discount', 'check(discount >= 0 AND discount <= 100)', _('Discount must be a value between 0 and 100.')),
    ]

# We register invoice periods for Rent orders.
# See the doc of register_invoice_period for more informations.
RentOrder.register_invoice_period('once', _('Once'), 'get_invoices_for_once_period')
#RentOrder.register_invoice_period('monthly', _('Monthly'))
#RentOrder.register_invoice_period('quaterly', _('Quaterly'))
#RentOrder.register_invoice_period('yearly', _('Yearly'))

class RentOrderLine(osv.osv):

    """
    Rent order lines define products that will be rented.
    """

    def on_product_changed(self, cursor, user_id, ids, product_id, quantity):

        """
        This method is called when the product changed :
            - Fill the tax_ids field with product's taxes
            - Fill the description field with product's name
            - Fill the product UoM
        """

        result = {}

        if not product_id:
            return result

        product = self.pool.get('product.product').browse(cursor, user_id, product_id)

        if not product.id:
            return result # Might never happened

        result['description'] = product.name
        result['tax_ids'] = [tax.id for tax in product.taxes_id]
        result['product_id_uom'] = product.uom_id.id
        result['product_type'] = 'rent' if product.can_be_rent else 'service'

        if result['product_type'] == 'rent':
            result['unit_price'] = product.rent_price
        else:
            result['unit_price'] = product.list_price

        warning = self.check_product_quantity(cursor, user_id, product, quantity)

        return {'value' : result, 'warning' : warning}

    def on_quantity_changed(self, cursor, user_id, ids, product_id, quantity):

        """
        Checks the new quantity on product quantity changed.
        """

        result = {}
        if not product_id:
            return result
        product = self.pool.get('product.product').browse(cursor, user_id, product_id)
        if not product.id:
            return result
        warning = self.check_product_quantity(cursor, user_id, product, quantity)
        return {'value' : result, 'warning' : warning}

    def get_order_price(self, line):

        """
        Returns the order price for the line.
        """

        if line.product_type == 'rent':
            return 0.0
        return line.unit_price
        
    def get_rent_price(self, line, order_duration, order_unity, product_price_unity, product_price_factor):

        """
        Returns the rent price for the line.
        """

        if line.product_type != 'rent':
            return 0.0

        return line.unit_price * product_price_factor * order_duration

    def get_prices(self, cursor, user_id, ids, fields_name, arg, context):

        """
        Returns the price for the duration for one of this product.
        """

        lines = self.browse(cursor, user_id, ids, context=context)
        result = {}

        for line in lines:

            order_duration = line.order_id.rent_duration
            order_unity = line.order_id.rent_duration_unity
            
            try:
                product_price_unity = line.order_id.get_duration_unities(cursor, user_id)[0][0]
            except KeyError:
                raise osv.except_osv(_('Invalid duration unit'), _('It seems that there is an invalid duration unity '
                                       'in your company configuration. Contact your system administrator.'))

            product_price_factor = UNITIES_FACTORS[product_price_unity][order_unity]

            rent_price = self.get_rent_price(line, order_duration, order_unity,
                product_price_unity, product_price_factor)
            order_price = self.get_order_price(line)
            line_price = (rent_price or order_price) * (1-line.discount/100.0)

            result[line.id] = {
                'rent_price' : rent_price,
                'order_price' : order_price,
                'line_price' : line_price * line.quantity,
                'real_price' : line_price,
            }

        return result

    def get_invoice_lines_data(self, cursor, user_id, ids, context=None):

        """
        Returns a dictionary that data used to create the invoice lines.
        """

        rent_lines = self.browse(cursor, user_id, ids, context)
        result = []

        for rent_line in rent_lines:

            # The account that will be used is the income account of the product (or its category)
            invoice_line_account_id = rent_line.product_id.product_tmpl_id.property_account_income.id
            if not invoice_line_account_id:
                invoice_line_account_id = rent_line.product_id.categ_id.property_account_income_categ.id
            if not invoice_line_account_id:
                raise osv.except_osv(_('Error !'), _('There is no income account defined for this product: "%s" (id:%d)')
                    % (rent_line.product_id.name, rent_line.product_id.id,))

            invoice_line_data = {
                'name': rent_line.description,
                'account_id': invoice_line_account_id,
                'price_unit': rent_line.unit_price,
                'quantity': rent_line.quantity,
                'discount': rent_line.discount,
                'product_id': rent_line.product_id.id or False,
                'invoice_line_tax_id': [(6, 0, [x.id for x in rent_line.tax_ids])],
                'note': rent_line.notes,
                'sequence' : 10,
            }

            result.append(invoice_line_data)

        return result

    def check_product_type(self, cursor, user_id, ids, context=None):

        """
        Check that the product can be rented if it's makred as 'rent', and that is is
        a service product it it's marked as 'Service' or at least, sellable.
        """

        lines = self.browse(cursor, user_id, ids, context)

        for line in lines:
            if line.product_type == 'rent' and not line.product_id.can_be_rent:
                return False
            elif line.product_type == 'service':
                if line.product_id.type != 'service' or not line.product_id.sale_ok:
                    return False
        return True

    def check_product_quantity(self, cursor, user_id, product, quantity):

        """
        This method is not called from a constraint. It checks if there is enought quantity of this product,
        and return a 'warning usable' dictionnary, or an empty one.
        """

        warning = {}
        if product.type != 'product':
            return warning
        if product.virtual_available < quantity:
            warning = {
                'title' : _("Not enought quantity !"),
                'message' : _("You don't have enought quantity of this product. You asked %d, but there is "
                              "only %d available. You can continue, but you are warned.") % (quantity, product.virtual_available)
            }
        return warning

    _name = 'rent.order.line'
    _rec_name = 'description'
    _columns = {
        'description' : fields.char(_('Description'), size=180, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'This description will be used in invoices.')),
        'order_id' : fields.many2one('rent.order', _('Order'), required=True, ondelete='CASCADE'),
        'product_id' : fields.many2one('product.product', _('Product'), required=True, readonly=True,
             context="{'search_default_rent' : True}", states={'draft': [('readonly', False)]}, help=_(
            'The product you want to rent.'),),
        'product_type' : fields.selection(PRODUCT_TYPE, _('Type of product'), required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
                "Select Rent if you want to rent this product. Service means that you will sell this product "
                "with the others rented products. Use it to sell some services like installation or assurances. "
                "Products which are sold will be invoiced once, with the first invoice.")),
        'product_id_uom' : fields.related('product_id', 'uom_id', relation='product.uom', type='many2one',
            string=_('UoM'), readonly=True, help=_('The Unit of Measure of this product.')),
        'quantity' : fields.integer(_('Quantity'), required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'How many products to rent.')),
        'discount' : fields.float(_('Discount (%)'), readonly=True, digits=(16, 2),
            states={'draft': [('readonly', False)]}, help=_(
            'If you want to apply a discount on this order line.')),
        'state' : fields.related('order_id', 'state', type='selection', selection=STATES, readonly=True, string=_('State')),
        'tax_ids': fields.many2many('account.tax', 'rent_order_line_taxes', 'rent_order_line_id', 'tax_id',
            _('Taxes'), readonly=True, states={'draft': [('readonly', False)]}),
        'notes' : fields.text(_('Notes')),
        'unit_price' : fields.float(_('Unit Price'), required=True, states={'draft':[('readonly', False)]}, help=_(
            'The price per duration or the sale price, depending of the product type.')),
        'real_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Price for duration"),
            help=_('This price correspond to the price of the product, not matter its type. In the case of a rented '
                   'product, its equal to the price for the duration, and in the case of a service product, to the'
                   'unit price of the product.')),
        'rent_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Price per duration")),
        'order_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Price at order")),
        'line_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Subtotal")),
    }

    _defaults = {
        'state' : STATES[0][0],
        'quantity' : 1,
        'discount' : 0.0,
        'order_price' : 0.0,
    }

    _sql_constraints = [
        ('valid_discount', 'check(discount >= 0 AND discount <= 100)', _('Discount must be a value between 0 and 100.')),
        ('valid_price', 'check(unit_price > 0)', _('The price must be superior to 0.'))
    ]

    _constraints = [
        (check_product_type, _("You can't use this product type with this product. "
            "Check that the product is marked for rent or for sale. Moreover, "
            "Service products must be declared as 'Service' in the product view."), ['product_type']),
    ]

RentOrder(), RentOrderLine()
