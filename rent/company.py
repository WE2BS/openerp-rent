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

class Company(osv.osv):

    _inherit = 'res.company'
    _name = 'res.company'
    _columns = {
        'rent_unity_category' : fields.many2one('product.uom.categ', string='Rent Duration Category',
            help="The category of products used for renting durations.", required=True)
    }
    _defaults = {
        'rent_unity_category' :
            lambda self, cr, uid, context: Searcher(cr, uid, 'ir.model.data',
                name='duration_uom_categ', module='rent').browse_one().res_id
    }

Company()
