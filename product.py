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

from osv import osv, fields
from tools.translate import _

from rent import UNITIES

def get_unity_display(name):
    for key, value in UNITIES:
        if key == name:
            return value
    raise Exception('Invalid unity key.')

class Product(osv.osv):

    # Extends the basic product.product model :
    #    - Add a 'can_be_rent' field.
    #    - The price for the rent.

    def check_rent_price(self, cursor, user_id, ids, context=None):

        """
        We check that the rent price is neither empty or 0 if the product can be rent.
        """

        products = self.browse(cursor, user_id, ids, context=context)

        for product in products:

            if product.can_be_rent:
                if not product.rent_price or product.rent_price <= 0:
                    return False

        return True

    def fields_get(self, cr, user, fields=None, context=None):

        # We override this method to change the rent_price label on-the-fly.
        # For example, if 'Day' was selected on the company duration unity,
        # the label will be 'Rent price (in Day)'.

        result = super(osv.osv, self).fields_get(cr, user, fields, context)
        unity = self.pool.get(
            'res.users').browse(cr, user, user, context=context).company_id.rent_unity

        if 'rent_price' in result:
            result['rent_price']['string'] = result['rent_price']['string'] % get_unity_display(unity)

        return result

    _name = 'product.product'
    _inherit = 'product.product'

    _columns = {
        'can_be_rent' : fields.boolean(_('Can be rented'), help=_(
            'Enable this if you want to rent this product.')),
        'rent_price' : fields.float(_('Rent price (per %s)'), help=_(
            'The price is expressed for the duration unity defined in the company configuration.')),
    }

    _defaults = {
        'can_be_rent' : False,
        'rent_price' : 0.0,
    }

    _constraints = [(check_rent_price, _('The Rent price must be a positive value.'), ['rent_price']),]

Product()
