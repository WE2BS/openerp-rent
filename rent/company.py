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
from openlib import Searcher
from tools.translate import _

class Company(osv.osv):

    # We override the res.company model to add a configuration field which define
    # the minimum rent time unity (Hour, Day, Month, Year).
    #
    # All rent duration will be multiple of this unity. For example, if you set it to 'Day',
    # and you rent a product for 2 Months, it will be ~60 days.
    #
    # The price defined on products is the price for 1 time unity.

    _inherit = 'res.company'
    _name = 'res.company'
    _columns = {
        'rent_unity' : fields.many2one('product.uom', string=_('Rent minimal unity'),
            help=_("This will define the minimum rent unity. "
                   "You won't be able to rent a product for less that one of this unity. "
                   "Products prices will also be defined for this unity."),
            required=True)
    }
    _defaults = {
        'rent_unity' :
            lambda self, cursor, user_id, context: Searcher(cursor, user_id, 'ir.model.data',
                name='uom_day', module='rent').browse_one().res_id
    }

Company()
