Installation
============

You should follow these steps to install OpenER Rent. If you are familiar with git, you can directly clone
the `Github repository`_ to get the latest version, else, read this page.

Download
--------

The current version is |release| and can be downloaded from the `Github project page`_ (By clicking on the ``Downloads``
button). We provide a packaged version which includes all the dependancies.

Here is a list of the required modules, if you want to install them manually :

    * `Aeroo Report`_ (6xRC4 or superior)
    * `Aeroo Lib`_ (RC2 or superior)
    * `OpenLib`_ (0.2.5 or superior)

.. _Github project page:
.. _Github repository: http://github.com/WE2BS/openerp-rent
.. _Aeroo Report: https://launchpad.net/aeroo
.. _Aeroo Lib: https://launchpad.net/aeroolib
.. _OpenLib: https://github.com/WE2BS/openerp-openlib

Install modules
---------------

If you downloaded the packaged version, you should have a *zipfile* containing all the required modules.
You must extract these modules in the directory ``bin/addons`` of the OpenERP Server.

Once all modules have been extracted, go to OpenERP ``Administration->Modules->Update modules list`` menu and refresh
the list of availabe modules.

Install rent
------------

Finally, install the ``rent`` module in OpenERP ``Administration->Modules->Modules`` view.
