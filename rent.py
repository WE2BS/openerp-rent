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
from dateutil.relativedelta import *

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

UNITIES = (
    ('hour', _('Hour')),
    ('day', _('Day')),
    ('month', _('Month')),
    ('year', _('Year')),
)

UNITIES_FACTORS = {
    'hour' : {
        'hour' : 1.0,
        'day' : 24.0,
        'month' : 24.0*30,
        'year' : 365.0 * 24,
    },
    'day' : {
        'day' : 1.0,
        'month' : 30.0,
        'year' : 365.0,
    },
    'month' : {
        'month' : 1.0,
        'year' : 12.0,
    },
    'year' : {
        'year' : 1.0,
    }
}

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

#        lines = self.browse(cursor, user_id, ids, context=context)
#        base_unity = self._get_duration_unities(cursor, user_id, context=context)[0][0]
#        prices = {}
#
#        for line in lines:
#
#            duration = line.duration_value
#            unity = line.duration_unity
#            factor = UNITIES_FACTORS[base_unity][unity]
#            price = line.product_id.price * factor * duration
#
#            prices[line.id] = price
#
#        return prices

    def _get_line_price(self, cr, uid, ids, field_name, arg, context=None):

        """
        In the case of a rent line, the price depends of the duration, the number of product and the price per duration.

        Ex: A product cost 1€/Month, 100 product are rented, 100€/Month, for 3 months, which does a total
        of 300€ for 3 months.

        The duration unity must be converted too: if it is defined in days in the product, and we rent
        for a month/year, we have to convert the price per day in price per month.

        To be the more accurate, with use the dateutil module to calculate exactly how many days there are between dates.
        """

#        tax_obj = self.pool.get('account.tax')
#        cur_obj = self.pool.get('res.currency')
#        res = {}
#        if context is None:
#            context = {}
#        for line in self.browse(cr, uid, ids, context=context):
#            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
#            taxes = tax_obj.compute_all(cr, uid, line.tax_id, price, line.product_uom_qty, line.order_id.partner_invoice_id.id, line.product_id, line.order_id.partner_id)
#            cur = line.order_id.pricelist_id.currency_id
#            res[line.id] = cur_obj.round(cr, uid, cur, taxes['total'])
#        return res
#
#        return {}

    _name ='rent.order.line'
    _inherit = 'sale.order.line'

    _columns = {
        'begin_datetime' : fields.datetime(_('Begin')),
        'duration_value' : fields.integer(_('Duration'),),
        'duration_unity' : fields.selection(_get_duration_unities, _('Duration unity')),
        'price_unit' : fields.function(_get_unit_price, type="float", string=_('Unit price'), method=True),
        'price_subtotal' : fields.function(_get_line_price, type="float", string=_('Subtotal'), method=True),
    }

SaleOrder(), RentOrderLine()
