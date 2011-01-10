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

def convert_datetimes(*args):

    """
    This function returns a list of datetimes object for each date passed as a string.
    """

    return [datetime.datetime.strptime(arg, DATE_FORMAT) for arg in args]

class RentOrder(osv.osv):

    """
    Represents the a rent order:
     - The date of the order (required, default today)
     - A reference for this order
     - The partner (client) products are rented to.

    Only products that are marked as 'rentable' can be rented.
    """

    _name = 'rent.order'
    _sql_constraints = [('rent_date_order', 'CHECK(begin_date < end_date)', 'Begin date must be before the end date.'),]
    _columns = {
        'date' : fields.date(_('Date'), required=True),
        'ref' : fields.char(_('Reference'), size=200),
        'line_ids' : fields.one2many('rent.line', 'rent_id', _('Products'), required=True),
        'partner_id' : fields.many2one('res.partner', _('Client'), ondelete='restrict', required=True,
            context={'search_default_customer' : 1}),
    }
    

class RentLine(osv.osv):

    """
    This class represents a rented product. The price is determined in function of the
    duration and the specified quantity.
    """

    def _calculate_price(self, cursor, user_id, ids, field_name, arg, context=None):

        """
        Returns the price of a product depending on the duration of the rent.
        """

        print context, ids

        if not ids:
            return

        lines = self.browse(cursor, user_id, ids, context=context)
        results = {}

        for line in lines:

            pass
        
        return results

    _name ='rent.line'
    _columns = {
        'rent_id' : fields.many2one('rent.order', 'Rent'),
        'product_id' : fields.many2one('product.product', 'Product'),
        'duration_value' : fields.integer(_('Duration')),
        'duration_unity' : fields.selection(UNITIES, _('Duration unity')),
        'price' : fields.function(_calculate_price, type="float", method=True, string=_('Price for the duration'))
    }
    _defaults = {
        'price' : 0,
    }

RentOrder(), RentLine()
