User guide
==========

You can create and manage your rent orders the same you do with sale orders. Go to ``Sales->Sales->Rent Orders``
to list/create/delete your rent orders.

Create a Rent Order
-------------------

The rent order view is similar to the sale order view except for few fields specifics to renting :

    * ``Rent begin date`` : Defines the datetime at wich this rent order will start. In the case of a rent order with
      only stockable products, this field is only informative, because the rent order will start once all products have been shipped.

    * ``Duration / Duration unity`` : Defines the duration of the rent order. It's pretty obvious.

    * ``Shipping Date`` : Defines the date of delivery of products. It can't be after or before the rent begin date.
      This field is ignored in case of a service-only rent order.

    * ``Return Date`` : Defines a specific return date for products. By default, it's the rent order end date.
      This field is ignored in case of a service-only rent order.

    * ``Invoice period`` : Defines how to invoice the customer. For example, if you select a *Monthly* period,
      an invoice will be generated every month during the rent duration. For short rent order (less than a month),
      you can use the *Once* period which generates only once invoice.

.. warning::

    You can't use a ``Day`` duration with a ``Monthly`` invoicing period. Currently, if you want to invoice monthly,
    you must use a ``Month`` or ``Year`` duration unity.

.. note::

    Invoices are generated automatically into a *cron job*. By default, this cron is called once per day. Go to
    ``Administration->Scheduler->Scheduled Ations->Rent - Invoices Cron`` to change this.

Add products
------------

When you add a product to a rent order, there are some options you must be aware of :

    * ``Type of product`` : This is **not** the same that the product's type (*service*, *stockable* or *consumable*).
      It defines if the product will be invoiced only once (*Service*), or if it will be rented and invoiced multiple
      time (*Rent*). For example, if you want to invoice a product named *Installation* only once, you should choose *Service*.

      However, if you want to rent a service product (defined as *Service* in its product view) like *web hosting*,
      you must set this field to *Rent*, because you will invoice it monthly !

    * ``Product Unit Price`` : This field defines the price of the product.

        * In the case of a ``Rent`` product, it defines its price, expressed in the unity defined for the product
          price in the product view. For example, if you defined that a product costs 15€/Day, this field will contain
          ``15`` by default, no matter what unity you choosed for the rent order duration.

        * In the case of a ``Service`` product invoiced once, it defines its sale price. Filled with the product's sale
          price by default.

.. note::

    When you select a product, fields are automatically filled with default values. You shouldn't have to change them.

Handle the workflow
-------------------

There are two cases with rent orders : the rent order is a *service*-only rent order (no shipping), or not.

Services only rent orders
~~~~~~~~~~~~~~~~~~~~~~~~~

These rent orders will be started by a *cron job* or when you click on ``Starts the rent order manually``. When the
rent order is started, you can see its state is *Ongoing*. A service-only rent order is automatically stopped
when the end date is reached, or when you click on ``Stops the rent order manually``.

.. warning::

    A stopped rent order can't be started again !


Deliverable rent orders
~~~~~~~~~~~~~~~~~~~~~~~

If you rent order contains one or more *stockable/consumable* products, it won't be started automatically. It will
be started when the products will be shipped. You must validate the *delivery order* to starts the rent order.

You can access the delivery order associated to your rent order by clicking on the ``Delivery Order`` button on
the right pane.

When you validate the delivery order, an incoming shipment is automatically created, dated of the rent order
*return date*. To stop your rent order, you will have to validate this incoming shipment.

You can acess it using the ``Incoming Shipment`` button on the right pane.
