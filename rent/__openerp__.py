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

{
    "name": "Rent",
    "version": "0.2",
    "author": "UIDE/WE2BS",
    "category": "Generic Modules/Sales & Purchases",
    "website": "https://github.com/thibautd/openerp-rent",
    "description":
    """
    This module manages the leasing of products to partners.
    """,
    "depends": ["base", "openlib", "sale", "report_aeroo"],
    "init_xml": [],
    "demo_xml": [],
    "update_xml": ['data/uoms.xml', 'data/intervals.xml', 'views/rent.xml', 'views/product.xml', 'views/menus.xml',
                   'views/sequence.xml', 'views/company.xml', 'workflow/rent.xml', 'security/ir.model.access.csv',
                   'reports/reports.xml'],
    "active": False,
    "test": [],
    "installable": True
}
