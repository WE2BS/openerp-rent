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

import logging

from osv import osv, fields
from tools.translate import _
from openlib.orm import *

_logger = logging.getLogger('rent')

class Product(osv.osv, ExtendedOsv):

    def check_rent_price(self, cr, uid, ids, context=None):

        """
        We check that the rent price is neither empty or 0 if the product can be rent.
        """

        products = self.filter(ids)

        for product in products:
            if product.can_be_rent:
                if not product.rent_price or product.rent_price <= 0:
                    return False
        return True

    def default_price_unity(self, cr, uid, context=None):

        """
        Returns the default price unity (the first in the list).
        """

        unity = self.get(category_id__name='Duration', _object='product.uom')

        if not unity:
            _logger.warning("It seems that there isn't a reference unity in the 'Duration' UoM category. "
                            "Please check that the category exists, and there's a refernce unity.")
        
        return unity.id if unity else False

    _name = 'product.product'
    _inherit = 'product.product'

    _columns = {
        'can_be_rent' : fields.boolean('Can be rented', help='Enable this if you want to rent this product.'),
        'rent_price' : fields.float('Rent price', help=
            'The price is expressed for the duration unity defined in the company configuration.'),
        'rent_price_unity' : fields.many2one('product.uom', 'Rent Price Unity', domain=[('category_id.name', '=', 'Duration')],
            help='Rent duration unity in which the price is defined.'),
    }

    _defaults = {
        'can_be_rent' : False,
        'rent_price' : 1.0,
        'rent_price_unity' : default_price_unity,
    }

    _constraints = [(check_rent_price, _('The Rent price must be a positive value.'), ['rent_price']),]

Product()
