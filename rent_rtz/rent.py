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

from openlib.orm import *
from openlib.tools import *
from openlib.github import report_bugs

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

class RentOrderRtz(osv.osv, ExtendedOsv):

    _inherit = 'rent.order'

    @report_bugs
    def get_invoice_comment(self, cursor, user_id, order, date, current, max, period_begin, period_end):

        """
        This method is overriden from rent.order object to only show dates, not times.
        """

        # We use the lang of the partner instead of the lang of the user to put the text into the invoice.
        partner = self.get(order.partner_id, _object='res.partner')
        partner_lang = self.get(code=partner.lang, _object='res.lang')
        context = {'lang' : partner.lang}
        
        format = partner_lang.date_format

        begin_date = to_datetime(order.date_begin_rent).strftime(format)
        end_date = to_datetime(order.date_end_rent).strftime(format)

        return _(
            "Rental from %s to %s.\n"
            "Invoice %d/%d.\n"
        ) % (
            begin_date,
            end_date,
            current,
            max,
        )

RentOrderRtz()

class RentOrderRtzLine(osv.osv, ExtendedOsv):

    @report_bugs
    def get_rent_price(self, line, duration_unit_price):

        """
        Returns the rent price for the line.
        """

        if line.product_type != 'rent':
            return 0.0

        return duration_unit_price * line.coeff

    @report_bugs
    def get_default_coeff(self, cursor, user_id, context=None):
        if context is None:
            context = {}
        if not 'duration' in context:
            return 1
        else:
            if context['duration'] in COEFF_MAPPING:
                # We check that the duration unity is days, because Rtz only rent for days. If it rent for anything
                # else that a day, we set the bigger coeff by default.
                duration_unity_id = context['duration_unity']
                duration_unity_xmlid = self.pool.get('product.uom').get_xml_id(
                    cursor, user_id, [duration_unity_id], context=context)
                duration_unity_xmlid = duration_unity_xmlid[duration_unity_id]
                if not duration_unity_xmlid or duration_unity_xmlid != 'rent.uom_day':
                    return COEFF_MAPPING['more']
                return COEFF_MAPPING[context['duration']]
        return COEFF_MAPPING['more']

    @report_bugs
    def get_invoice_lines_data(self, cursor, user_id, ids, context=None):

        """
        We append the coeff value tu the name in the invoice line.
        """

        # TODO: Find a way to avoid the double browse (the one within super() and this one
        lines = self.browse(cursor, user_id, ids, context)
        result = super(RentOrderRtzLine, self).get_invoice_lines_data(cursor, user_id, ids, context)

        for index, line_data in enumerate(result):
            line_data['name'] += ' (Coeff: %d)' % lines[index].coeff

        return result

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
