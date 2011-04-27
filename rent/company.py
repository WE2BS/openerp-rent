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

DEFAULT_BEGIN = (
    ('today', 'Today'),
    ('tomorrow_morning', 'Tomorrow (Morning)'),
    ('tomorrow_after', 'Tomorrow (Afternoon)'),
    ('empty', 'Empty'),
)

class Company(osv.osv):

    """
    These fields are used in the comptation of an order duration.
    """

    _inherit = 'res.company'
    _columns = {
        'rent_morning_begin' : fields.time('Day begin'),
        'rent_afternoon_begin' : fields.time('Afternoon begin'),
        'rent_afternoon_end' : fields.time('Afternoon end'),
        'rent_default_begin' : fields.selection(DEFAULT_BEGIN, 'Rent default begin/shipping')
    }
    _defaults = {
        'rent_morning_begin' : '09:00:00',
        'rent_afternoon_begin' : '14:00:00',
        'rent_afternoon_end' : '19:00:00',
        'rent_default_begin' : 'today',
    }

Company()
