Configuration
=============

OpenERP Rent is flexiable and let your configure a lot of things.

General configuration
---------------------

You can configure OpenERP Rent in the company configuration tab. Go to ``Administration->Company``, select your company
and open to the ``Configuration`` tab. You should see a group named ``Rent`` containing configuration fields.

``Day begin``

    This field defines the begin time of a normal day. This value will be used as default value for new rent orders,
    depending on what you put in the ``Rent default begin/shipping`` field.

``Afternoon begin``

    This field defines the begin time of the afternoon (after launch). This value will be used as default value for
    new rent orders, depending on what you put in the ``Rent default begin/shipping`` field.

``Afternoon end``

    This field defines the time at which the work day is considered finished. This value will be used to defined the
    return time of products. For example, if you rent a product from the January 1st at 9am for 1 day, the default product
    return datetime will be January 1st at ``Afternoon end`` value.

``Rent default begin/shipping``

    This field defines the default begin datetime of your rent order and its
    assodiated shipping order. When you create a rent order, the begin datetime will be one of the following, depending
    of the selected value :
    
    * ``Today`` : The date will be today, and the time will be either the ``Day begin``, if you create the rent order
      before the time specified in ``Day begin``. If you are between the ``Day begin`` time and the ``Afternoon begin``
      time, the rent order will be started at the specified in ``Afternoon begin``. If you are after the
      ``Afternoon begin`` time, it will be created at the current time + 1 hour.

    * ``Tomorrow (Morning)`` : The rent order begin datetime will be tomorrow at the ``Day begin`` time.

    * ``Tomorrow (Afternoon)`` : The rent order begin datetime will be tomorrow at the ``Day afternoon`` time.

    * ``Empty`` : No default value, you must fill it manually.

Products configuration
----------------------

Once you have done the global configuration to fit your company needs, you have toconfigure your products. Go to
``Sales->Products->Products`` and create or select and existing product. First of all, if you want to rent a product,
you must check the ``Can be rented`` checkbox in the ``Characteristics`` group (top right).

If you want your product to bo sold only once with a rent order as a service, like *Installation* or *Configuration*,
just check the ``Can be sold`` checkbox and mark the product as a ``Service`` in ``Product type``.

Product types
~~~~~~~~~~~~~

OpenERP Rent let your rent different products : *Service* products and *Stockable (or Consumable)* products. *Services*
product won't generate a out/in shipping order, whereas *Stockable* products will.

Their is also a difference in the workflow : a *Service*-only rent order will start automatically at
the rent order begin datetime, whereas a *Stockable* product will start when the products have been shipped to the client.

If you mix both *Service* and *Stockable* products in a rent order, it will start with the shipping of the products.

Product rent price
~~~~~~~~~~~~~~~~~~

When you check the ``Can be rented`` wheckbox, you can (and must) define a rent price. You can express the price in the
unity of your choice (``Day``, ``Month``, ``Year``). This price will be converted automatically in the rent order.

For example, if a product costs 15€ per month, and you rent it for 15 days, the customer will pay 7,5€. Because
it's complicated to convert unities based on duration, OpenERP Rent uses the following factors to do the convertion :

    * 1 Month = 30 Days
    * 1 Year = 12 Months, or 360 Days

Go to ``Sales->Configuration->Product->Units of Measure->Units of Measure`` to configure these factors to fit your needs.
