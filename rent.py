# -*- encoding: utf-8 -*-
#
# OpenERP Rent - A rent module for OpenERP 6
# Copyright (C) 2010-Today Thibaut DIRLIK <thibaut.dirlik@gmail.com>
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

import datetime

from osv import osv, fields
from tools.translate import _

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
UNITIES = (
    ('hour', _('Hour')),
    ('day', _('Day')),
    ('month', _('Month')),
    ('year', _('Year')),
)
TYPES = (
    ('sale', 'Sale'),
    ('rental', 'Rental'),
)

def convert_datetimes(*args):

    """
    This function returns a list of datetimes object for each date passed as a string.
    """

    return [datetime.datetime.strptime(arg, DATE_FORMAT) for arg in args]

class SaleOrder(osv.osv):

    """
    We replace the sale order to add the possibility to switch between sellign and renting.
    The order header will be the same, only order lines will change.
    """

    _name = 'sale.order'
    _inherit = 'sale.order'
    _columns = {
        'sale_type' : fields.selection(TYPES, _('Order type'), required=True),
        'rent_order_lines': fields.one2many('rent.order.line', 'order_id', 'Rent Order Lines',
            readonly=True, states={'draft': [('readonly', False)]}),
    }
    _defaults = {
        'sale_type' : 'sale',
    }
    
class RentOrderLine(osv.osv):

    """
    This class represents a rented product. The price is determined in function of the
    duration and the specified quantity.
    """

    def _check_date(self, cursor, user_id):

        """
        The begin date of the line can't be before the rent order date.
        """

    def _get_duration_unities(self, cursor, user_id, context=None):

        """
        Return the duration unities depending of the company configuration.
        """

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

    def _get_unit_price(self, cursor, user_id, ids, field_name, arg, context=None):

        """
        Note that the unit price in the case of a rent is not the price of the product
        but the price for 'one' of the selected duration unity (i.e 1 Month)
        """

        return {}

    def _get_line_price(self, cursor, user_id, ids, field_name, arg, context=None):

        """
        The line price is the unit price * the duration.
        """

        return {}

    _name ='rent.order.line'
    _inherit = 'sale.order.line'
    _columns = {
        'order_id': fields.many2one('sale.order', 'Rent Order Reference', required=True, ondelete='cascade', select=True, readonly=True, states={'draft':[('readonly',False)]}),
        'product_id' : fields.many2one('product.product', _('Product'),
            domain=[('can_be_rent', '=', True)], required=True),
        'begin_datetime' : fields.datetime(_('Begin'), required=True),
        'duration_value' : fields.integer(_('Duration'), required=True),
        'duration_unity' : fields.selection(_get_duration_unities, _('Duration unity'), required=True),
        'price_unit' : fields.function(_get_unit_price, type="float", string=_('Unit price')),
        'price_subtotal' : fields.function(_get_line_price, type="float", string=_('Subtotal')),
    }

SaleOrder(), RentOrderLine()
