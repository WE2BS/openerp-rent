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
from openlib.orm import *

class InvoiceInterval(osv.osv, ExtendedOsv):

    """
    This object represents a invoice interval the user can used when invoicing rent orders.

    In this object, we define the name of the interval, and the name of the python method called.
    If you want to add support for a specific interval, just creates one of this object, inherit rent.order
    and add your custom method with this signature :

        method(self, cr, uid, order, context=None)

    Where order is the result of a browse() on the current order. This method must returns a list of the created
    invoices ids, or raise an exception.
    """

    _name = 'rent.interval'
    _columns = {
        'name' : fields.char('Name', size=150, required=True, translate=True),
        'method' : fields.char('Method', size=255, required=True),
        'not_allowed_duration_unities' : fields.many2many('product.uom', 'rent_interval_not_allowed_durations',
            'interval_id', 'duration_id', string='Duration not allowed with this interval !'),
    }

InvoiceInterval()
