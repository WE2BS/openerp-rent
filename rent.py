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
import decimal_precision as dp

from osv import osv, fields
from tools.translate import _
from tools.misc import cache
from dateutil.relativedelta import *

# We define a function to convert days to month. Some customer mays want exact
# number of days, other could consider that there are 30 days in a month.
def convert_days_to_month(begin_date, number_of_days):
    return 30 * number_of_days

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
    We replace the sale order to add the possibility to switch between selling and renting.
    The order header will be the same, only order lines will change.
    """

    def _get_order(self, cr, uid, ids, context=None):
        result = {}
        for line in self.pool.get('rent.order.line').browse(cr, uid, ids, context=context):
            result[line.order_id.id] = True
        return result.keys()

    def _amount_all(self, cr, uid, ids, field_name, arg, context=None):

        """
        This method has been overriden from sale.order to handle rent order lines.
        """

        cur_obj = self.pool.get('res.currency')
        res = {}

        for order in self.browse(cr, uid, ids, context=context):

            res[order.id] = {'amount_untaxed': 0.0, 'amount_tax': 0.0, 'amount_total': 0.0, }
            val = val1 = 0.0
            cur = order.pricelist_id.currency_id

            # Here is the only change
            lines = order.order_line if order.sale_type == 'sale' else order.rent_order_lines

            for line in lines:
                val1 += line.price_subtotal
                val += self._amount_line_tax(cr, uid, line, context=context)

            res[order.id]['amount_tax'] = cur_obj.round(cr, uid, cur, val)
            res[order.id]['amount_untaxed'] = cur_obj.round(cr, uid, cur, val1)
            res[order.id]['amount_total'] = res[order.id]['amount_untaxed'] + res[order.id]['amount_tax']

        return res

    _name = 'sale.order'
    _inherit = 'sale.order'
    _columns = {
        'sale_type' : fields.selection(TYPES, _('Order type'), required=True),
        'rent_order_lines': fields.one2many('rent.order.line', 'order_id', 'Rent Order Lines',
            readonly=True, states={'draft': [('readonly', False)]}),
        'amount_untaxed': fields.function(_amount_all, method=True, digits_compute= dp.get_precision('Sale Price'), string='Untaxed Amount',
            store = {
                'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['rent_order_lines'], 10),
                'rent.order.line': (_get_order, ['price_unit', 'tax_id', 'discount', 'product_uom_qty'], 10),
            },
            multi='sums', help="The amount without tax."),
        'amount_tax': fields.function(_amount_all, method=True, digits_compute= dp.get_precision('Sale Price'), string='Taxes',
            store = {
                'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['rent_order_lines'], 10),
                'rent.order.line': (_get_order, ['price_unit', 'tax_id', 'discount', 'product_uom_qty'], 10),
            },
            multi='sums', help="The tax amount."),
        'amount_total': fields.function(_amount_all, method=True, digits_compute= dp.get_precision('Sale Price'), string='Total',
            store = {
                'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['rent_order_lines'], 10),
                'rent.order.line': (_get_order, ['price_unit', 'tax_id', 'discount', 'product_uom_qty'], 10),
            },
            multi='sums', help="The total amount."),
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

    @cache(30)
    def _get_duration_unities(self, cursor, user_id, context=None):

        """
        Return the duration unities depending of the company configuration.
        
        Note: We cache the result because it will certainly not change a lot,
        and it will cause a lot of useless queries on order with a lot of lines.
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
        but the price for the selected duration (i.e 2 Month). This price will be multiplied
        by the number of product to get the line total.
        """

        lines = self.browse(cursor, user_id, ids, context=context)
        base_unity = self._get_duration_unities(cursor, user_id, context=context)[0][0]
        prices = {}

        for line in lines:

            duration = line.duration_value
            unity = line.duration_unity
            factor = UNITIES_FACTORS[base_unity][unity]
            price = line.product_id.rent_price * factor * duration

            prices[line.id] = price

        return prices

    _name ='rent.order.line'
    _inherit = 'sale.order.line'
    _defaults = {
        'begin_datetime' : lambda *args, **kwargs: str(datetime.datetime.now()),
        'duration_unity' : lambda self, cursor, user_id, context: self._get_duration_unities(cursor, user_id, context)[0],
        'duration_value' : 1,
    }
    _columns = {
        'begin_datetime' : fields.datetime(_('Begin'), required=True),
        'duration_value' : fields.integer(_('Duration'), required=True),
        'duration_unity' : fields.selection(_get_duration_unities, _('Duration unity'), required=True),
        'price_unit' : fields.function(_get_unit_price, type="float", string=_('Unit price'), method=True),
    }

SaleOrder(), RentOrderLine()
