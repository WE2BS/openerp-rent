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

from osv import osv, fields
from tools.translate import _
from tools.misc import cache, DEFAULT_SERVER_DATE_FORMAT
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
    ('ongoing', _('Ongoing')), # Invoices generated, waiting for payments
    ('done', _('Done')), # All invoices have been paid
    ('cancelled', _('Cancelled')), # The order has been cancelled
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

        return { 'value' : result }

        return result

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

        return {
            'name': 'Customer Invoices',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.invoice',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'current',
            'domain': [('origin', '=', order.ref)],
            'context' : {'form_view_ref' : view_xml_id}
        }

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

        self.write(cursor, user_id, ids, {
            'state' : 'ongoing',
            'invoice_ids' : [(6, 0, invoices_id)]
        })

        return True

    def action_cancel(self, cursor, user_id, ids):

        """
        If you cancel the order before invoices have been generated, it's ok.
        Else, you can cancel only of invoices haven't been confirmed yet.
        """

        orders = self.browse(cursor, user_id, ids)

        for order in orders:

            if order.state == 'ongoing':
                invoices_ids = []
                for invoice in order.invoice_ids:
                    if invoice.state not in ('draft', 'cancel'):
                        raise osv.except_osv(_("You can't cancel this order."),
                            _("This order have confirmed invoice, and can't be deleted right now."))
                    invoices_ids.append(invoice.id)

                # Else, we just remove the invoices
                self.pool.get('account.invoice').unlink(cursor, user_id, invoices_ids)

            self.write(cursor, user_id, ids, {'state':'cancelled'})

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

    def get_end_date(self, cursor, user_id, ids, field_name, arg, context=None):

        """
        Returns the rent order end date, based on the duration.
        """

        orders = self.browse(cursor, user_id, ids, context=context)
        result = {}

        for order in orders:

            begin = datetime.datetime.strptime(order.date_begin_rent, DEFAULT_SERVER_DATE_FORMAT).date()
            duration = order.rent_duration
            days = duration

            if order.rent_duration_unity == 'month':
                days = duration * UNITIES_FACTORS['day']['month']
            elif order.rent_duration_unity == 'year':
                days = duration * UNITIES_FACTORS['day']['year']

            end = begin + datetime.timedelta(days=days)
            end = end.strftime(DEFAULT_SERVER_DATE_FORMAT)

            result[order.id] = end

        return result

    def get_totals(self, cursor, user_id, ids, fields_name, arg, context=None):

        """
        Compute the total if the rent order, with taxes.
        """

        result = {}
        tax_pool = self.pool.get('account.tax')
        orders = self.browse(cursor, user_id, ids, context=context)

        for order in orders:

            total = 0.0
            total_with_taxes = 0.0
            total_taxes = 0.0
            total_taxes_with_discount = 0.0

            for line in order.rent_line_ids:

                # The compute_all function is defined in the account -module  Take a look.
                prices = tax_pool.compute_all(cursor, user_id, line.tax_ids, line.unit_price, line.quantity)

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

    def get_invoice_between(self, cursor, user_id, order, begin_date, duration, current, max):

        """
        Generates an invoice at the specified date, for the specified duration. The two last arguenbts current and max
        defines the maximum number of invoices and the current invoice number. For example: current=4, max=12.
        """

        # Create the invoice
        invoice_id = self.pool.get('account.invoice').create(cursor, user_id,
            {
                'name' : _('Invoice %d/%d') % (current, max),
                'origin' : order.ref,
                'type' : 'out_invoice',
                'state' : 'draft',
                'date_invoice' : begin_date,
                'partner_id' : order.partner_id.id,
                'address_invoice_id' : order.partner_invoice_address_id.id,
                'account_id' : order.partner_id.property_account_receivable.id,
            }
        )

        # Create the lines
        lines_ids = [line.id for line in order.rent_line_ids]
        lines_data = self.pool.get('rent.order.line').get_invoice_lines_data(cursor, user_id, lines_ids)
        for line_data in lines_data:
            line_data['invoice_id'] = invoice_id
            self.pool.get('account.invoice.line').create(cursor, user_id, line_data)

        return invoice_id

    def get_invoice_periods(self, cursor, user_id, context=None):

        """
        Returns a list of available periods (that have been registered with register_invoice_period()).
        """

        return [(period, self._periods[period][0]) for period in self._periods]

    def get_invoices_for_once_period(self, cursor, user_id, order):

        """
        Generates only one invoice for the rent duration.
        """

        return [self.get_invoice_between(cursor, user_id, order, order.date_begin_rent, order.rent_duration, 1, 1)]

    _name = 'rent.order'
    _sql_constraints = []
    _rec_name = 'ref'
    _periods = {}
    _order = 'date_created DESC,ref DESC'

    _columns = {
        'state' : fields.selection(STATES, _('State'), readonly=True, help=_('Gives the state of the rent order.')),
        'ref' : fields.char(_('Reference'), size=128, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The reference is a unique identifier that identify this order.')),
        'date_created' : fields.date(_('Date'), readonly=True, required=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Date of the creation of this order.')),
        'date_confirmed' : fields.date(_('Confirm date'), help=_(
            'Date on which the Rent Order has been confirmed.')),
        'date_begin_rent' : fields.date(_('Rent begin date'), required=True,
            readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'Date of the begin of the leasing.')),
        'date_end_rent' : fields.function(get_end_date, type="date", method=True, string=_("Rent end date")),
        'rent_duration_unity' : fields.selection(get_duration_unities, _('Duration unity'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration unity, available choices depends of your company configuration.')),
        'rent_duration' : fields.integer(_('Duration'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration of the lease, expressed in selected unit.')),
        'rent_invoice_period' : fields.selection(get_invoice_periods, _('Invoice Period'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'Period between invoices')),
        'salesman' : fields.many2one('res.users', _('Salesman'),
            readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The salesman who handle this order, optional.')),
        'shop_id': fields.many2one('sale.shop', 'Shop', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The shop where this order was created.')),
        'partner_id': fields.many2one('res.partner', _('Customer'), required=True, change_default=True,
            domain=[('customer', '=', 'True')], context={'search_default_customer' : True},
            readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'Select a customer. Only partners marked as customer will be shown.')),
        'partner_invoice_address_id': fields.many2one('res.partner.address', _('Invoice Address'), readonly=True,
            required=True, states={'draft': [('readonly', False)]}, help=_(
            'Invoice address for current Rent Order.')),
        'partner_order_address_id': fields.many2one('res.partner.address', _('Ordering Address'), readonly=True,
            required=True, states={'draft': [('readonly', False)]}, help=_(
            'The name and address of the contact who requested the order or quotation.')),
        'partner_shipping_address_id': fields.many2one('res.partner.address', 'Shipping Address', readonly=True,
            required=True, states={'draft': [('readonly', False)]}, help=_(
            'Shipping address for current rent order.')),
        'rent_line_ids' : fields.one2many('rent.order.line', 'order_id', _('Order Lines'), readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Lines of this rent order.')),
        'notes': fields.text(_('Notes'), help=_(
            'Enter informations you want about this order.')),
        'discount' : fields.float(_('Global discount (%)'),
            readonly=True, states={'draft': [('readonly', False)]}, help=_(
            'Apply a global discount to this order.')),
        'invoice_ids': fields.many2many('account.invoice', 'rent_order_line_tax', 'rent_order_line_id', 'tax_id',
            _('Taxes'), readonly=True, states={'draft': [('readonly', False)]}),

        'total' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Untaxed amount"), digits_compute=get_precision('Sale Price')),
        'total_with_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Total"), digits_compute=get_precision('Sale Price')),
        'total_taxes' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Taxes"), digits_compute=get_precision('Sale Price')),
        'total_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Untaxed amount (with discount)"), digits_compute=get_precision('Sale Price')),
        'total_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Taxes (with discount)"), digits_compute=get_precision('Sale Price')),
        'total_with_taxes_with_discount' : fields.function(get_totals, multi=True, method=True, type="float",
            string=_("Total (with discount)"), digits_compute=get_precision('Sale Price')),
    }

    _defaults = {
        'date_created':
            lambda *args, **kwargs: time.strftime('%Y-%m-%d'),
        'date_begin_rent':
            lambda *args, **kwargs: time.strftime('%Y-%m-%d'),
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
        ('ref_uniq', 'UNIQUE(ref)', _('Rent Order reference must be unique !')),
        ('valid_created_date', 'CHECK(date_created >= CURRENT_DATE)', _('The date must be today of later.')),
        ('valid_begin_date', 'CHECK(date_begin_rent >= CURRENT_DATE)', _('The begin date must be today or later.')),
        ('begin_after_create', 'CHECK(date_begin_rent >= date_created)', _('The begin date must later than the order date.')),
        ('valid_discount', 'CHECK(discount >= 0 AND discount <= 100)', _('Discount must be a value between 0 and 100.')),
    ]

# We register invoice periods for Rent orders.
# See the doc of register_invoice_period for more informations.
RentOrder.register_invoice_period('once', _('One invoice'), 'get_invoices_for_once_period')
#RentOrder.register_invoice_period('monthly', _('Monthly'))
#RentOrder.register_invoice_period('quaterly', _('Quaterly'))
#RentOrder.register_invoice_period('yearly', _('Yearly'))

class RentOrderLine(osv.osv):

    """
    Rent order lines define products that will be rented.
    """

    def on_product_changed(self, cursor, user_id, ids, product_id, description):

        """
        This method is called when the product changed :
            - Fill the tax_ids field with product's taxes
            - Fill the description field with product's name
        """

        result = {}

        if not product_id:
            return result

        product = self.pool.get('product.product').browse(cursor, user_id, product_id)

        if not product.id:
            return result

        result['description'] = product.name
        result['tax_ids'] = [tax.id for tax in product.taxes_id]
        result['product_id_uom'] = product.uom_id.id

        return {'value' : result}

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

            # The factor is used to convert the product price unity into the order price unity.
            # Example:
            #   UNITIES_FACTORS['day']['year'] will return a factor to convert days to years
            #   (365 in this case). So, to convert a price which is defined per day in price per year,
            #   you have to multiply the price per 365.
            unit_price = line.product_id.rent_price * product_price_factor * order_duration

            result[line.id] = {
                'unit_price' : unit_price,
                'line_price' : unit_price * line.quantity,
            }

        return result

    def get_invoice_lines_data(self, cursor, user_id, ids, context=None):

        """
        Returns a dictionary that contains rent.order.line ids as key, and a dictionary of data used to create the invoice lines.
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

        # Add a header with the rent duration (thanks to account_invoice_layout module
        result.insert(0, {
            'state' : 'title',
            'name' : _('Rent from %s to %s, for a total of %s %s'),
        })

        return result
        
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
        'product_id_uom' : fields.related('product_id', 'uom_id', relation='product.uom', type='many2one',
            string=_('UoM'), readonly=True, help=_('The Unit of Measure of this product.')),
        'quantity' : fields.integer(_('Quantity'), required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'How many products to rent.')),
        'discount' : fields.float(_('Discount (%)'), readonly=True, digits=(16, 2),
            states={'draft': [('readonly', False)]}, help=_(
            'If you want to apply a discount on this order line.')),
        'state' : fields.related('order_id', 'state', type='selection', selection=STATES, readonly=True, string=_('State')),
        'tax_ids': fields.many2many('account.tax', 'rent_order_line_tax', 'rent_order_line_id', 'tax_id',
            _('Taxes'), readonly=True, states={'draft': [('readonly', False)]}),
        'notes' : fields.text(_('Notes')),
        'unit_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Price per duration")),
        'line_price' : fields.function(get_prices, method=True, multi=True, type="float", string=_("Subtotal")),
    }

    _defaults = {
        'state' : STATES[0][0],
        'quantity' : 1,
        'discount' : 0.0,
    }

    _sql_constraints = [
        ('valid_discount', 'CHECK(discount >= 0 AND discount <= 100)', _('Discount must be a value between 0 and 100.')),
    ]

RentOrder(), RentOrderLine()
