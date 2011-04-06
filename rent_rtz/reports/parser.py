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

from datetime import datetime
from report import report_sxw
from tools.misc import DEFAULT_SERVER_DATETIME_FORMAT

class Parser(report_sxw.rml_parse):

    def __init__(self, cr, uid, name, context):
        super(Parser, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'format_datetime': self.format_datetime,
        })

    def format_datetime(self, value):

        """
        Format the datetime into a date only string.
        """

        datetime_object = datetime.strptime(value, DEFAULT_SERVER_DATETIME_FORMAT)

        return datetime_object.strftime('%d/%m/%y')