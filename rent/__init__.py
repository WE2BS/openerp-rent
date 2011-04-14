# -*- encoding: utf-8 -*-
#
# OpenERP Rent Module
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

def get_default_unity_category(obj, cr, uid, context=None):

    user_company_id = obj.pool.get('res.users')._get_company(cr, uid)
    unity_category_id = None

    if user_company_id:
        unity_category_id = obj.pool.get('res.company').browse(cr, uid,
            user_company_id, context=context).rent_unity_category.id

    if not unity_category_id:
        data = openlib.Searcher(cr, uid, 'ir.model.data',
            context=context, name='duration_uom_categ', module='rent').browse_one()
        return data.res_id if data else None

    return unity_category_id

import rent
import company
import product
import pooler
import openlib

