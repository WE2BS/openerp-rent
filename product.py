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

class Product(osv.osv):

    """
    Extends the basic product.product model :
        - Add a 'can_be_rent' field.
        - Add a 'renters_ids' field : A list of partners that are currently renting the product.
    """

    _name = 'product.product'
    _inherit = 'product.product'

    _columns = {
        'can_be_rent' : fields.boolean('Can be rented', help="Enable this if you want to rent this product.")
    }

    _defaults = {
        'can_be_rent' : False,
    }

Product()
