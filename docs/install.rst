============
Installation
============

------------
Requirements
------------

You have to install the following libraries/modules to use OpenERP Rent :

    * OpenLib v0.2.5+ - http://github.com/WE2BS/openerp-openlib
    * Aeroo Report - https://launchpad.net/aeroo (You need report_aeroo and report_aeroo_ooo if you want PDF)
    * Aeroo Report Library - https://launchpad.net/aeroolib

.. note ::

    At each stable version, we provide a "packaged" version on github which contains all the dependency.

-------------
Configuration
-------------

Once you have install all the required package, install the ``rent`` module in OpenERP. If it's the first time you
install it, you should have a configuration wizard from ``openlib`` which will ask you some information to configure your
github account. If you want to automatically report bugs, fill this wizard.

You can then configure your renting module in your company's *Configuration* tab.
