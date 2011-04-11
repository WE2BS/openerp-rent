# -*- encoding: utf-8 -*-
#
# OpenERP Rent - Extention for Rtz Evènement
# Copyright (C) 2010-2011 Thibaut DIRLIK <thibaut.dirlik@gmail.com>
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

import openlib

from osv import osv, fields
from tools.translate import _

COEFF_MAPPING = {
    1 : 1,
    2 : 1.5,
    3 : 2,
    4 : 2.3,
    5 : 2.5,
    6 : 3,
    7 : 3.5,
    8 : 3.3,
    9 : 3.8,
    10 : 4.1,
    11 : 4.4,
    12 : 4.,
    13 : 4.8,
    14 : 5,
    15 : 5.2,
    16 : 5.5,
    17 : 5.7,
    18 : 6,
    19 : 6.2,
    20 : 6.5,
    21 : 6.8,
    22 : 7,
    23 : 7.2,
    24 : 7.5,
    25 : 7.8,
    26 : 8,
    27 : 8.2,
    28 : 8.4,
    29 : 8.6,
    30 : 8.8,
    'more' : 9,
}

class RentOrderRtz(osv.osv):

    def get_invoice_comment(self, cursor, user_id, order, date, current, max, period_begin, period_end):

        """
        This method is overriden from rent.order object to only show dates, not times.
        """

        partner_lang = openlib.partner.get_partner_lang(cursor, user_id, order.partner_id)
        format = partner_lang.date_format

        begin_date = openlib.to_datetime(order.date_begin_rent).strftime(format)
        end_date = openlib.to_datetime(order.date_end_rent).strftime(format)

        period_begin = openlib.to_datetime(period_begin).strftime(format)
        period_end = openlib.to_datetime(period_end).strftime(format)

        return _(
            "Rental from %s to %s, invoice %d/%d.\n"
            "Invoice for the period from %s to %s."
        ) % (
            begin_date,
            end_date,
            current,
            max,
            period_begin,
            period_end,
        )

    _inherit = 'rent.order'

RentOrderRtz()

class RentOrderRtzLine(osv.osv):

    def get_rent_price(self, line, order_duration, order_unity, product_price_unity, product_price_factor):

        """
        We take the coeff field into account when computing the rent price.
        """

        if line.product_type != 'rent':
            return 0.0
        return line.unit_price * product_price_factor * order_duration * line.coeff

    def get_default_coeff(self, cursor, user_id, context=None):
        if context is None:
            context = {}
        if not 'duration' in context:
            return 1
        else:
            if context['duration'] in COEFF_MAPPING:
                return COEFF_MAPPING[context['duration']]
        return COEFF_MAPPING['more']

    _inherit = 'rent.order.line'
    _name = 'rent.order.line'
    
    _columns = {
        'coeff' : fields.float(_('Coefficient'), required=True),
    }
    
    _defaults = {
        'coeff' : get_default_coeff,
    }

    _sql_constraints = [
        ('valid_coeff', 'check(coeff > 0)', _('The coefficient must be superior to 0.')),
    ]

RentOrderRtzLine()
