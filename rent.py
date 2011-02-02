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

from osv import osv, fields
from tools.translate import _
from tools.misc import cache

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
    ('draft', 'Quotation'), # Default state
    ('confirmed', 'Confirmed'), # Confirmed, have to generate invoices
    ('ongoing', 'Ongoing'), # Invoices generated, waiting for payments
    ('done', 'Done'), # All invoices have been paid
    ('cancelled', 'Cancelled'), # The order has been cancelled
)

class RentOrder(osv.osv):

    # A Rent Order is almost like a Sale Order except that the way we generate invoices
    # is really different, and there is a notion of duration. I decided to not inherit
    # sale.order because there were a lot of useless things for a Rent Order.

    def on_client_changed(self, cursor, user_id, ids, client_id):

        # Called when the client has changed : we update all address fields :
        #   Order address, invoice address and shipping address.

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
                'Client has not any address', 'You must define a least one default address for this client.')

        return { 'value' : result }

    def on_confirm_clicked(self, cursor, user_id, *args, **kwargs):

        print 'lol', args, kwargs

    @cache(30)
    def get_duration_unities(self, cursor, user_id, context=None):

        # Return the duration unities depending of the company configuration.
        #
        # Note: We cache the result because it will certainly not change a lot,
        # and it will cause a lot of useless queries on orders with a lot of lines.

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

    _name = 'rent.order'
    _sql_constraints = []
    _rec_name = 'ref'

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
        'rent_duration_unity' : fields.selection(get_duration_unities, _('Duration unity'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration unity, available choices depends of your company configuration.')),
        'rent_duration' : fields.integer(_('Duration'),
            required=True, readonly=True, states={'draft' : [('readonly', False)]}, help=_(
            'The duration of the lease, expressed in selected unit.')),
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
            lambda self, cursor, user_id, context: self.get_duration_unities(cursor, user_id, context)[0],
        'rent_duration' : 1,
        'shop_id' : 1, # TODO: Use ir.values to handle multi-company configuration
        'discount' : 0.0,

    }

    _sql_constraints = [
        ('ref_uniq', 'UNIQUE(ref)', _('Rent Order reference must be unique !')),
        ('valid_created_date', 'CHECK(date_created >= CURRENT_DATE)', _('The date must be today of later.')),
        ('valid_begin_date', 'CHECK(date_begin_rent >= CURRENT_DATE)', _('The begin date must be today or later.')),
        ('begin_after_create', 'CHECK(date_begin_rent >= date_created)', _('The begin date must later than the order date.')),
        ('valid_discount', 'CHECK(discount >= 0 AND discount <= 100', _('Discount must be a value between 0 and 100.')),
    ]

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

    _name = 'rent.order.line'
    _rec_name = 'description'
    _columns = {
        'description' : fields.char(_('Description'), size=180, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'This description will be used in invoices.')),
        'order_id' : fields.many2one('rent.order', _('Order'), required=True),
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
