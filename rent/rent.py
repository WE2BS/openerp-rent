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

# OpenLib is a library I wrote for OpenERP, you can download it here :
# https://github.com/WE2BS/openerp-openlib
import openlib

from osv import osv, fields
from tools.translate import _
from tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from decimal_precision import get_precision

_logger = logging.getLogger('rent')

STATES = (
    ('draft', 'Quotation'), # Default state
    ('confirmed', 'Confirmed'), # Confirmed, have to generate invoices
    ('ongoing', 'Ongoing'), # Invoices generated, waiting for confirmation
    ('done', 'Done'), # All invoices have been confirmed
    ('cancelled', 'Cancelled'), # The order has been cancelled
)

PRODUCT_TYPE = (
    ('rent', 'Rent'),
    ('service', 'Service'),
)

class RentOrder(osv.osv):

    # A Rent Order is almost like a Sale Order except that the way we generate invoices
    # is really different, and there is a notion of duration. I decided to not inherit
    # sale.order because there were a lot of useless things for a Rent Order.

    def on_client_changed(self, cr, uid, ids, client_id):

        """
        Called when the client has changed : we update all addresses fields :
        Order address, invoice address and shipping address.
        """

        result = {}
        client = self.pool.get('res.partner').browse(cr, uid, client_id)

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

    def on_duration_changed(self, cr, uid, ids, rent_begin, duration, duration_unity_id, context=None):

        """
        This method is called when the duration or duration unity changed. Input shipping date
        is updated to be set at the end of the duration automatically.
        """

        if not rent_begin or not duration or not duration_unity_id:
            return {}
        
        # Converts the duration in days and add these days to the rent input shipping date
        day_unity = openlib.Searcher(cr, uid, 'product.uom', context=context,
            category_id__xmlid='rent.duration_uom_categ', name='Day').browse_one()
        days = self.pool.get('product.uom')._compute_qty(cr, uid,
            duration_unity_id, duration, day_unity.id)

        # Depending of the widget, the begin date can be a date or a datetime
        try:
            begin = openlib.to_datetime(rent_begin)
        except ValueError:
            try:
                begin = openlib.to_date(rent_begin)
            except ValueError:
                raise osv.except_osv('Begin date have an invalid format.')

        end = begin + datetime.timedelta(days=days-1) # We remove 1 day to set the return date the same day that the rent end date
        end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        return {'value' : {'date_in_shipping' : end}}


    def on_draft_clicked(self, cr, uid, ids, context=None):

        """
        This method is called when the rent order is in cancelled state and the user clicked on 'Go back to draft'.
        """

        orders = self.browse(cr, uid, ids, context=context)
        wkf_service = netsvc.LocalService("workflow")
        self.write(cr, uid, ids, {'state' : 'draft'})

        for order in orders:
            # Delete and re-create the workflow
            wkf_service.trg_delete(uid, 'rent.order', order.id, cr)
            wkf_service.trg_create(uid, 'rent.order', order.id, cr)

        for id, name in self.name_get(cr, uid, ids):
            self.log(cr, uid, order.id, _('The Rent Order "%s" has been reset.') % name)

        return True

    def on_show_invoices_clicked(self, cr, uid, ids, context=None):

        """
        Show the invoices which have been generated.
        """

        order = self.browse(cr, uid, ids, context=context)[0]
        view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'account', 'invoice_form')
        view_id = view_id and view_id[1] or False
        view_xml_id = self.pool.get('ir.ui.view').get_xml_id(cr, uid, [view_id])[view_id]

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

    def action_confirmed(self, cr, uid, ids):

        """
        Called when the workflow goes to confirmed. Currently, the module only handles stockable/consummable products.
        """

        orders = self.browse(cr, uid, ids)
        ok = False

        for order in orders:
            for line in order.rent_line_ids:
                if line.product_type == 'rent':
                    if line.product_id.type in ('consu', 'product'):
                        ok = True

        if not ok:
            raise osv.except_osv('Error', "You must rent a least one stockable/consommable product, the module "
                "doesn't support (yet) Service only rent.")

        self.write(cr, uid, ids, {'state' : 'confirmed'})
        
        return True

    def action_generate_out_move(self, cr, uid, orders_ids):

        """
        Create the stock moves of the specified orders objects. For each order, two picking are created :
            - An output picking, to send the product to the customer.
            - An input picking, to get the products back.
        """

        orders = self.browse(cr, uid, orders_ids)
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

                    out_picking_id = picking_pool.create(cr, uid, {
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
                move_pool.create(cr, uid, {
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
                workflow.trg_validate(uid, 'stock.picking',
                    out_picking_id, 'button_confirm', cr)
                self.write(cr, uid, order.id,
                    {'out_picking_id' : out_picking_id}),

                # Check assignement (TODO: This should be optional)
                picking_pool.action_assign(cr, uid, [out_picking_id])

        return True

    def action_ongoing(self, cr, uid, ids):

        """
        We switch to ongoing state when the out picking has been confirmed.
        We have to generate the input picking.
        """

        orders = self.browse(cr, uid, ids)
        picking_pool, move_pool = map(
            self.pool.get, ('stock.picking', 'stock.move'))
        workflow = netsvc.LocalService("workflow")

        for order in orders:
            in_picking_id = picking_pool.create(cr, uid, {
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
                move_pool.create(cr, uid, {
                    'name': line.name,
                    'picking_id': in_picking_id,
                    'product_id': line.product_id.id,
                    'date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    'date_expected': order.date_in_shipping,
                    'product_qty': line.product_qty,
                    'product_uom': line.product_uom.id,
                    'product_uos' : line.product_uos.id,
                    'product_uos_qty' : line.product_uos_qty,
                    'address_id': line.address_id.id,
                    'location_id': line.location_dest_id.id,
                    'location_dest_id' : line.location_id.id,
                    'state': 'draft',
                })
            
            self.write(cr, uid, order.id,
                {'in_picking_id' : in_picking_id, 'state' : 'ongoing'})
            
            # Confirm the picking
            workflow.trg_validate(uid, 'stock.picking',
                in_picking_id, 'button_confirm', cr)

            # Check assignement (TODO: This should be optional)
            picking_pool.action_assign(cr, uid, [in_picking_id])
        
        return True

    def action_generate_invoices(self, cr, uid, ids, context=None):

        """
        This action is called by the workflow activity 'ongoing'. We generate invoices for the duration period.
        """

        orders = self.browse(cr, uid, ids)

        for order in orders:

            period_function = order.rent_invoice_period.method
            period_function = getattr(self, period_function)

            if not period_function:
                raise osv.except_osv('Programming Error', 'The invoice interval method "%s" does not exist.')

            invoices_id = period_function(cr, uid, order, context)

        self.write(cr, uid, ids, {'invoices_ids' : [(6, 0, invoices_id)]})

        return True

    def action_cancel(self, cr, uid, ids):

        """
        If you cancel the order before invoices have been generated, it's ok.
        Else, you can cancel only if invoices haven't been confirmed yet.
        You can't cancel an order which have confirmed picking.
        """

        orders = self.browse(cr, uid, ids)

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
                self.write(cr, uid, order.id, {
                    'out_picking_id' : False,
                    'in_picking_id' : False,
                    'invoices_ids' : [(5)],
                    'state' : 'cancelled',
                })

                self.pool.get('account.invoice').unlink(cr, uid, invoice_ids)
                self.pool.get('stock.picking').unlink(cr, uid, picking_ids)
            else:
                raise osv.except_osv(_('Error'), _("You can't cancel an order in this state."))

        return True

    def get_order_from_lines(self, cr, uid, ids, context=None):

        """
        Returns lines ids associated to this order.
        """

        lines = self.pool.get('rent.order.line').browse(cr, uid, ids)
        return [line.order_id.id for line in lines]

    def get_end_date(self, cr, uid, ids, field_name, arg, context=None):

        """
        Returns the rent order end date, based on the duration.
        """

        orders = self.browse(cr, uid, ids, context=context)
        result = {}

        for order in orders:

            begin = openlib.to_datetime(order.date_begin_rent)
            duration = order.rent_duration
            day_unity = openlib.Searcher(cr, uid, 'product.uom',
                category_id__xmlid='rent.duration_uom_categ', name='Day').browse_one()
            
            # Converts the order duration (expressed in days/month/years) into the days duration
            days = self.pool.get('product.uom')._compute_qty(cr, uid,
                order.rent_duration_unity.id, duration, day_unity.id)

            end = begin + datetime.timedelta(days=days-1) # Removed one day to have a more realistic duration
            end = end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

            result[order.id] = end

        return result

    def get_invoiced_rate(self, cr, uid, ids, fields_name, arg, context=None):

        """
        Returns the percentage of invoices which have been confirmed.
        """

        orders = self.browse(cr, uid, ids, context=context)
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

    def get_totals(self, cr, uid, ids, fields_name, arg, context=None):

        """
        Compute the total if the rent order, with taxes.
        """

        result = {}
        tax_pool, fiscal_position_pool = map(self.pool.get, ['account.tax', 'account.fiscal.position'])
        orders = self.browse(cr, uid, ids, context=context)

        for order in orders:

            total = 0.0
            total_with_taxes = 0.0
            total_taxes = 0.0
            total_taxes_with_discount = 0.0
            total_buy_price = 0
            total_sell_price = 0

            for line in order.rent_line_ids:

                # We map the tax_ids thanks to the fiscal position, if specified.
                tax_ids = line.tax_ids
                if order.fiscal_position.id:
                    tax_ids = tax_pool.browse(cr, uid, fiscal_position_pool.map_tax(
                        cr, uid, order.fiscal_position, tax_ids, context=context),context=context)
                
                # The compute_all function is defined in the account module  Take a look.
                prices = tax_pool.compute_all(cr, uid, tax_ids, line.duration_unit_price, line.quantity)

                total_buy_price += tax_pool.compute_all(cr, uid, tax_ids,
                    line.product_id.product_tmpl_id.standard_price, line.quantity)['total_included']
                total_sell_price += tax_pool.compute_all(cr, uid, tax_ids,
                    line.product_id.product_tmpl_id.list_price, line.quantity)['total_included']

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
                'total_products_buy_price' : total_buy_price,
                'total_products_sell_price' : total_sell_price,
            }

        return result

    def get_invoice_comment(self, cr, uid, order, date, current, max, period_begin, period_end):

        """
        This method must return a comment that will be added to the invoice.
        """

        # We use the lang of the partner instead of the lang of the user to put the text into the invoice.
        context = {'lang' : openlib.get_partner_lang(cr, uid, order.partner_id).code}

        partner_lang = openlib.partner.get_partner_lang(cr, uid, order.partner_id)
        datetime_format = partner_lang.date_format + _(' at ') + partner_lang.time_format
        datetime_format = datetime_format.encode('utf-8')

        begin_date = openlib.to_datetime(order.date_begin_rent).strftime(datetime_format).decode('utf-8')
        end_date = openlib.to_datetime(order.date_end_rent).strftime(datetime_format).decode('utf-8')

        period_begin = openlib.to_datetime(period_begin).strftime(datetime_format).decode('utf-8')
        period_end = openlib.to_datetime(period_end).strftime(datetime_format).decode('utf-8')

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

    def get_invoice_at(self, cr, uid, order, date, current, max, invoice_period_begin, invoice_period_end):

        """
        Generates an invoice at the specified date. The two last arguenbts current and max
        defines the maximum number of invoices and the current invoice number. For example: current=4, max=12.
        """

        invoice_pool, invoice_line_pool = map(self.pool.get, ('account.invoice', 'account.invoice.line'))

        # Create the invoice
        invoice_id = invoice_pool.create(cr, uid,
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
                    cr, uid, order, date, current, max, invoice_period_begin, invoice_period_end),
            }
        )

        # Create the lines
        lines_ids = [line.id for line in order.rent_line_ids]
        lines_data = self.pool.get('rent.order.line').get_invoice_lines_data(cr, uid, lines_ids)

        for line_data in lines_data:
            line_data['invoice_id'] = invoice_id
            invoice_line_pool.create(cr, uid, line_data)

        # Update taxes
        invoice_pool.button_reset_taxes(cr, uid, [invoice_id])

        return invoice_id

    def get_invoice_for_once_period(self, cr, uid, order, context=None):

        """
        Generates only one invoice (at the end of the rent).
        """

        return [self.get_invoice_at(cr, uid, order,
            order.date_begin_rent, 1, 1, order.date_begin_rent, order.date_end_rent)]

    def get_products_buy_price(self, cr, uid, ids, field_name, args, context=None):

        """
        Returns the total of the buy price of all products. This is used to evaluate the price
        of the rented products, in case of problems with assurances.
        """

        orders = self.browse(cr, uid, ids, context=context)
        result = {}

        for order in orders:
            total = 0
            for line in order.rent_line_ids:
                buy_price_untaxed = line.product_id.product_tmpl_id.standard_price
                total += line.product_id.product_tmpl_id.standard_price * line.quantity
            result[order.id] = total

        return result

    def get_products_sell_price(self, cr, uid, ids, field_name, args, context=None):

        """
        Returns the total of sell price of all products. This is used to evaluate the price
        of the rented products, in case of problems with assurances.
        """

        orders = self.browse(cr, uid, ids, context=context)
        result = {}



        return result

    def test_have_invoices(self, cr, uid, ids, *args):

        """
        Method called by the workflow to test if the order have invoices.
        """

        return len(self.browse(cr, uid, ids[0]).invoices_ids) > 0

    def test_out_shipping_done(self, cr, uid, ids, *args):

        """
        Called by the workflow. Returns True once the product has been output shipped.
        """
        
        lines = self.browse(cr, uid, ids[0]).out_picking_id.move_lines or []

        return all(line.state == 'done' for line in lines)
    
    def test_in_shipping_done(self, cr, uid, ids, *args):

        """
        Called by the workflow. Returns True once the product has been input shipped.
        """
        
        return all(line.state == 'done' for line in self.browse(
            cr, uid, ids[0]).in_picking_id.move_lines)

    def default_duration_unity(self, cr, uid, context=None):

        """
        Returns the 1st UoM present into the Duration category.
        """

        unity = openlib.Searcher(cr, uid, 'product.uom', context=context,
            category_id__name='Duration').browse_one()

        if not unity:
            _logger.warning("It seems that there isn't a reference unity in the 'Duration' UoM category. "
                            "Please check that the category exists, and there's a reference unity.")

        return unity.id if unity else False

    def default_invoice_period(self, cr, uid, context=None):

        """
        Returns the 1st available interval.
        """

        interval = openlib.Searcher(cr, uid, 'rent.interval', context=context).browse_one()
        return interval.id if interval else False

    _name = 'rent.order'
    _sql_constraints = []
    _rec_name = 'ref'
    _periods = {}
    _order = 'date_created DESC,ref DESC'

    _columns = {
        'state' : fields.selection(STATES, 'State', readonly=True, help=
            'Gives the state of the rent order :\n'
            '- Quotation\n- Confirmed\n- Ongoing (Products have been shipped)\n'
            '- Done (Products have been get back)'),
        'ref' : fields.char('Reference', size=128, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help='The reference is a unique identifier that identify this order.'),
        'date_created' : fields.datetime('Date', readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help='Date of the creation of this order.'),
        'date_begin_rent' : fields.datetime('Rent begin date', required=True,
            readonly=True, states={'draft' : [('readonly', False)]}, help='Date of the begin of the leasing.'),
        'date_end_rent' : fields.function(get_end_date, type="datetime", method=True, string="Rent end date",
            store={ 'rent.order' : (lambda self, cr, uid, ids, context: ids, ['rent_duration', 'rent_duration_unity'],10,)}),
        'rent_duration_unity' : fields.many2one('product.uom', string='Unity', domain=[('category_id.name', '=', 'Duration')],
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=
            'The duration unity, available choices depends of your company configuration.'),
        'rent_duration' : fields.integer('Duration',
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=
            'The duration of the lease, expressed in selected unit.'),
        'rent_invoice_period' : fields.many2one('rent.interval', 'Invoice Period',
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help='Period between invoices'),
        'salesman' : fields.many2one('res.users', 'Salesman', ondelete='SET NULL',
            readonly=True, states={'draft' : [('readonly', False)]}, help=
            'The salesman who handle this order, optional.'),
        'shop_id': fields.many2one('sale.shop', 'Shop', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help='The shop where this order was created.', ondelete='RESTRICT'),
        'company_id': fields.related('shop_id', 'company_id', type='many2one', relation='res.company',
            string='Company', store=True, readonly=True),
        'partner_id': fields.many2one('res.partner', 'Customer', required=True, change_default=True,
            domain=[('customer', '=', 'True')], context={'search_default_customer' : True},
            readonly=True, states={'draft' : [('readonly', False)]}, ondelete='RESTRICT', help=
            'Select a customer. Only partners marked as customer will be shown.'),
        'partner_invoice_address_id': fields.many2one('res.partner.address', 'Invoice Address', readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=
            'Invoice address for current Rent Order.'),
        'partner_order_address_id': fields.many2one('res.partner.address', 'Ordering Address', readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=
            'The name and address of the contact who requested the order or quotation.'),
        'partner_shipping_address_id': fields.many2one('res.partner.address', 'Shipping Address', readonly=True,
            required=True, states={'draft': [('readonly', False)]}, ondelete='RESTRICT', help=
            'Shipping address for current rent order.'),
        'rent_line_ids' : fields.one2many('rent.order.line', 'order_id', 'Order Lines', readonly=True,
            states={'draft': [('readonly', False)]}, help='Lines of this rent order.'),
        'notes': fields.text('Notes', help='Enter informations you want about this order.'),
        'discount' : fields.float('Global discount (%)',
            readonly=True, states={'draft': [('readonly', False)]}, help=
            'Apply a global discount to this order.'),
        'fiscal_position' : fields.many2one('account.fiscal.position', 'Fiscal Position', readonly=True,
            states={'draft': [('readonly', False)]}, ondelete='SET NULL', help=
            'Fiscal Position applied to taxes and accounts.'),
        'invoices_ids': fields.many2many('account.invoice', 'rent_order_invoices', 'rent_order_id', 'invoice_id',
            'Invoices', readonly=True),
        'invoiced_rate' : fields.function(get_invoiced_rate, string='Invoiced', help=
            'Invoiced percent, calculated on the numver if invoices confirmed.', method=True),
        'date_out_shipping' : fields.datetime('Shipping date', readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help='Date of the shipping.'),
        'date_in_shipping' : fields.datetime('Return date', readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help='Date of products return.'),
        'out_picking_id' : fields.many2one('stock.picking', 'Output picking id', help=
            'The picking object which handle Stock->Client moves.', ondelete='RESTRICT'),
        'in_picking_id' : fields.many2one('stock.picking', 'Input picking id', help=
            'The picking object which handle Client->Stock moves.', ondelete='RESTRICT'),
        'description' : fields.char('Object', size=255, help=
            'A small description of the rent order. Used in the report.'),
        'total' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Untaxed amount", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Total", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Taxes", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Untaxed amount (with discount)", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Taxes (with discount)", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_with_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string="Total (with discount)", digits_compute=get_precision('Sale Price'),
            store={
                'rent.order.line' : (get_order_from_lines, None, 10),
                'rent.order' : (lambda *a: a[3], None, 10),
            }),
        'total_products_buy_price' : fields.function(get_totals, multi=True, type="float",
            string='Products buy price', method=True, digits_compute=get_precision('Sale Price'),
            store={'rent.order.line' : (get_order_from_lines, None, 10),}),
        'total_products_sell_price' : fields.function(get_totals, multi=True, type="float",
            string='Products sell price', method=True, digits_compute=get_precision('Sale Price'),
            store={'rent.order.line' : (get_order_from_lines, None, 10),}),
    }

    _defaults = {
        'date_created': fields.datetime.now,
        'date_begin_rent': fields.datetime.now,
        'date_out_shipping': fields.datetime.now,
        'state':
            'draft',
        'salesman': # Default salesman is the curent user
            lambda self, cr, uid, context: uid,
        'ref': # The ref sequence is defined in sequence.xml (Default: RENTXXXXXXX)
            lambda self, cr, uid, context:
                self.pool.get('ir.sequence').get(cr, uid, 'rent.order'),
        'rent_duration' : 1,
        'rent_duration_unity' : default_duration_unity,
        'rent_invoice_period' : default_invoice_period,
        'shop_id' : 1, # TODO: Use ir.values to handle multi-company configuration
        'discount' : 0.0,
    }

    _sql_constraints = [
        ('ref_uniq', 'unique(ref)', 'Rent Order reference must be unique !'),
        #('valid_created_date', 'check(date_created >= CURRENT_DATE)', _('The date must be today of later.')),
        #('valid_begin_date', 'check(date_begin_rent >= CURRENT_DATE)', _('The begin date must be today or later.')),
        ('begin_after_create', 'check(date_begin_rent >= date_created)', 'The begin date must later than the order date.'),
        ('valid_discount', 'check(discount >= 0 AND discount <= 100)', 'Discount must be a value between 0 and 100.'),
    ]

class RentOrderLine(osv.osv):

    """
    Rent order lines define products that will be rented.
    """

    def on_product_changed(self, cr, uid, ids, product_id, quantity):

        """
        This method is called when the product changed :
            - Fill the tax_ids field with product's taxes
            - Fill the description field with product's name
            - Fill the product UoM
        """

        result = {}

        if not product_id:
            return result

        product = self.pool.get('product.product').browse(cr, uid, product_id)

        result['description'] = product.name
        result['tax_ids'] = [tax.id for tax in product.taxes_id]
        result['product_id_uom'] = product.uom_id.id
        result['product_type'] = 'rent' if product.can_be_rent else 'service'

        if result['product_type'] == 'rent':
            result['unit_price'] = product.rent_price
        else:
            result['unit_price'] = product.list_price

        warning = self.check_product_quantity(cr, uid, product, quantity)

        return {'value' : result, 'warning' : warning}

    def on_quantity_changed(self, cr, uid, ids, product_id, quantity):

        """
        Checks the new quantity on product quantity changed.
        """

        result = {}
        if not product_id:
            return result
        product = self.pool.get('product.product').browse(cr, uid, product_id)
        if not product.id:
            return result
        warning = self.check_product_quantity(cr, uid, product, quantity)
        return {'value' : result, 'warning' : warning}

    def get_order_price(self, line):

        """
        Returns the order price for the line.
        """

        if line.product_type == 'rent':
            return 0.0
        return line.unit_price
        
    def get_rent_price(self, line, duration_unit_price):

        """
        Returns the rent price for the line.
        """

        if line.product_type != 'rent':
            return 0.0

        return duration_unit_price * line.order_id.rent_duration

    def get_prices(self, cr, uid, ids, fields_name, arg, context):

        """
        Returns the price for the duration for one of this product.
        """

        lines = self.browse(cr, uid, ids, context=context)
        result = {}

        for line in lines:

            if line.product_type == 'rent':
                # We convert the unit price of the product expressed in a unity (Day, Month, etc) into the unity
                # of the rent order. A unit price of 1€/Day will become a unit price of 30€/Month.
                converted_price = self.pool.get('product.uom')._compute_price(cr, uid,
                    line.product_id.rent_price_unity.id, line.product_id.rent_price, line.order_id.rent_duration_unity.id)
                real_unit_price = converted_price
                duration_unit_price = self.get_rent_price(line, converted_price)
            else:
                real_unit_price = self.get_order_price(line)
                duration_unit_price = real_unit_price

            # We apply the discount on the unit price
            duration_unit_price *= (1-line.discount/100.0)

            result[line.id] = {
                'real_unit_price' : real_unit_price,
                'line_price' : duration_unit_price * line.quantity,
                'duration_unit_price' : duration_unit_price,
            }

        return result

    def get_invoice_lines_data(self, cr, uid, ids, context=None):

        """
        Returns a dictionary that data used to create the invoice lines.
        """

        rent_lines = self.browse(cr, uid, ids, context)
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
                'price_unit': rent_line.real_unit_price,
                'quantity': rent_line.quantity,
                'discount': rent_line.discount,
                'product_id': rent_line.product_id.id or False,
                'invoice_line_tax_id': [(6, 0, [x.id for x in rent_line.tax_ids])],
                'note': rent_line.notes,
                'sequence' : 10,
            }

            result.append(invoice_line_data)

        return result

    def check_product_type(self, cr, uid, ids, context=None):

        """
        Check that the product can be rented if it's makred as 'rent', and that is is
        a service product it it's marked as 'Service' or at least, sellable.
        """

        lines = self.browse(cr, uid, ids, context)

        for line in lines:
            if line.product_type == 'rent' and not line.product_id.can_be_rent:
                return False
            elif line.product_type == 'service':
                if line.product_id.type != 'service' or not line.product_id.sale_ok:
                    return False
        return True

    def check_product_quantity(self, cr, uid, product, quantity):

        """
        This method is not called from a constraint. It checks if there is enought quantity of this product,
        and return a 'warning usable' dictionnary, or an empty one.
        """

        warning = {}
        if product.type != 'product':
            return warning
        if product.qty_available < quantity: # We use the real quantity, not the virtual one for renting !
            warning = {
                'title' : _("Not enought quantity !"),
                'message' : _("You don't have enought quantity of this product. You asked %d, but there are "
                              "%d available. You can continue, but you are warned.") % (quantity, product.qty_available)
            }
        return warning

    _name = 'rent.order.line'
    _rec_name = 'description'
    _columns = {
        'description' : fields.char('Description', size=180, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help='This description will be used in invoices.'),
        'order_id' : fields.many2one('rent.order', 'Order', required=True, ondelete='CASCADE'),
        'product_id' : fields.many2one('product.product', _('Product'), required=True, readonly=True,
             context="{'search_default_rent' : True}", states={'draft': [('readonly', False)]},
             help='The product you want to rent.',),
        'product_type' : fields.selection(PRODUCT_TYPE, 'Type of product', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=
                "Select Rent if you want to rent this product. Service means that you will sell this product "
                "with the others rented products. Use it to sell some services like installation or assurances. "
                "Products which are sold will be invoiced once, with the first invoice."),
        'product_id_uom' : fields.related('product_id', 'uom_id', relation='product.uom', type='many2one',
            string='UoM', readonly=True, help='The Unit of Measure of this product.'),
        'quantity' : fields.integer('Quantity', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help='How many products to rent.'),
        'discount' : fields.float('Discount (%)', readonly=True, digits=(16, 2),
            states={'draft': [('readonly', False)]}, help='If you want to apply a discount on this order line.'),
        'state' : fields.related('order_id', 'state', type='selection', selection=STATES, readonly=True, string='State'),
        'tax_ids': fields.many2many('account.tax', 'rent_order_line_taxes', 'rent_order_line_id', 'tax_id',
            'Taxes', readonly=True, states={'draft': [('readonly', False)]}),
        'notes' : fields.text('Notes'),
        'unit_price' : fields.float('Product Unit Price', required=True, states={'draft':[('readonly', False)]}, help=
            'The price per duration or the sale price, depending of the product type. For rented product, the price '
            'is expressed in the product rent unity, not the order rent unity! BE CAREFUL!'),
        'real_unit_price' : fields.function(get_prices, method=True, multi=True, type="float", string="Unit Price",
            help='This price correspond to the price of the product, not matter its type. In the case of a rented '
                 'product, its equal to the unit price expressed in order duration unity, '
                 'and in the case of a service product, to the sale price of the product.'),
        'duration_unit_price' : fields.function(get_prices, method=True, multi=True, type="float", string="Duration Unit Price",
            help='The price of ONE product for the entire duration.'),
        'line_price' : fields.function(get_prices, method=True, multi=True, type="float", string="Subtotal"),
    }

    _defaults = {
        'state' : STATES[0][0],
        'quantity' : 1,
        'discount' : 0.0,
        'unit_price' : 0.0,
    }

    _sql_constraints = [
        ('valid_discount', 'check(discount >= 0 AND discount <= 100)', 'Discount must be a value between 0 and 100.'),
        ('valid_price', 'check(unit_price > 0)', 'The price must be superior to 0.')
    ]

    _constraints = [
        (check_product_type, "You can't use this product type with this product. "
            "Check that the product is marked for rent or for sale. Moreover, "
            "Service products must be declared as 'Service' in the product view.", ['product_type']),
    ]

RentOrder(), RentOrderLine()
