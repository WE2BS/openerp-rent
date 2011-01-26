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

from osv import osv, fields
from tools.translate import _
from tools.misc import cache

UNITIES = (
    ('hour', _('Hour')),
    ('day', _('Day')),
    ('month', _('Month')),
    ('year', _('Year')),
)

class RentOrder(osv.osv):

    # A Rent Order is almost like a Sale Order except that the way we generate invoices
    # is really different, and there is a notion of duration. I decided to not inherit
    # sale.order because there were a lot of useless things for a Rent Order.

    @cache(30)
    def _get_duration_unities(self, cursor, user_id, context=None):

        # Return the duration unities depending of the company configuration.
        #
        # Note: We cache the result because it will certainly not change a lot,
        # and it will cause a lot of useless queries on orders with a lot of lines.

        min_unity = self.pool.get('res.users').browse(
            cursor, user_id, user_id, context=context).company_id.rent_unity
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
        'state' : fields.selection((
            ('draft', 'Quotation'), # Default state
            ('confirmed', 'Confirmed'), # Confirmed, have to generate invoices
            ('ongoing', 'Ongoing'), # Invoices generated, waiting for payments
            ('done', 'Done'), # All payments recieved
        ), _('State'), readonly=True, help=_('Gives the state of the rent order.')),
        'ref' : fields.char(_('Reference'), size=128, required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The reference is a unique identifier that identify this order.')),
        'date_created' : fields.date(_('Order date'), readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'Date of the creation of this order.')),
        'date_confirmed' : fields.date(_('Confirm date'), help=_(
            'Date on which the Rent Order has been confirmed.')),
        'date_begin_rent' : fields.date(_('Rent begin date'), required=True, help=_(
            'Date of the begin of the leasing.')),
        'rent_duration_unity' : fields.selection(_get_duration_unities, _('Duration unity'), help=_(
            'The duration unity, available choices depends of your company configuration.')),
        'rent_duration' : fields.integer(_('Duration'), help=_(
            'The duration of the lease, expressed in selected unit.')),
        'salesman' : fields.many2one('res.users', _('Salesman'), help=_(
            'The salesman, optional.')),
        'shop_id': fields.many2one('sale.shop', 'Shop', required=True, readonly=True,
            states={'draft': [('readonly', False)]}, help=_(
            'The shop where this order was created.')),
        'partner_id': fields.many2one('res.partner', _('Customer'), required=True, change_default=True,
            domain=[('customer', '=', 'True')], context={'search_default_customer' : True}, help=_(
            'Select a customer. Only partners marked as customer will be shown.')),
        'partner_invoice_address_id': fields.many2one('res.partner.address', _('Invoice Address'), readonly=True,
            required=True, states={'draft': [('readonly', False)]}, help=_(
            'Invoice address for current Rent Order.')),
        'partner_order_address_id': fields.many2one('res.partner.address', _('Ordering Contact'), readonly=True,
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
    }

    _defaults = {
        'date_created':
            lambda *args, **kwargs: time.strftime('%Y-%m-%d'),
        'state':
            'draft',
        'salesman': # Default salesman is the curent user
            lambda self, cursor, user_id, context: user_id,
        'ref': # The ref sequence is defined in sequence.xml (Default: RENTXXXXXXX)
            lambda self, cursor, user_id, context:
                self.pool.get('ir.sequence').get(cursor, user_id, 'rent.order'),
    }

    _sql_constraints = [
        ('ref_uniq', 'UNIQUE(ref)', _('Rent Order Reference must be unique !')),
    ]

class RentOrderLine(osv.osv):

    _name = 'rent.order.line'
    _columns = {
        'name' : fields.char('lol', size=32),
        'order_id' : fields.many2one('rent.order', _('Order')),
        'product_id' : fields.many2one('product.product', _('Product')),
    }
    
RentOrder(), RentOrderLine()
