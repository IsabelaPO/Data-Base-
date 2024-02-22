#!/usr/bin/python3
from logging.config import dictConfig

import math
import aux
import psycopg
from flask import session
from flask import flash
from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from psycopg.rows import namedtuple_row
from psycopg_pool import ConnectionPool

# postgres://{user}:{password}@{hostname}:{port}/{database-name}
DATABASE_URL = "postgres://db:db@postgres/db"

pool = ConnectionPool(conninfo=DATABASE_URL)
# the pool starts connecting immediately.


dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s:%(lineno)s - %(funcName)20s(): %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["wsgi"]},
    }
)

app = Flask(__name__)
app.config.update(
    TESTING=True,
    SECRET_KEY='fbb370e7b1c424e039de8304b2013a5895bf1ab62c08b4a8b7efa6f240798c79'
)
log = app.logger


@app.route("/", methods=("GET",))
@app.route("/customers", methods=("GET",))
def customer_index():
    """Show all the accounts, most recent first."""

    page = int(request.args.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page
    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            customers = cur.execute(
                """
                SELECT cust_no, name, email, phone
                FROM customer
                ORDER BY cust_no
                LIMIT %(per_page)s OFFSET %(offset)s;
                """,
                {"per_page":per_page,"offset":offset},
            ).fetchall()
            log.debug(f"Found {cur.rowcount} rows.")
        
        with conn.cursor(row_factory=namedtuple_row) as cur:
            customers_all = cur.execute(
                """
                SELECT count(*) as total
                FROM customer;
                """,
                {},
            ).fetchone().total
            log.debug(f"Found {cur.rowcount} rows.")

    total_pages = math.ceil(customers_all / per_page)

    # API-like response is returned to clients that request JSON explicitly (e.g., fetch)
    if (
        request.accept_mimetypes["application/json"]
        and not request.accept_mimetypes["text/html"]
    ):
        return jsonify(customers,page,total_pages)

    return render_template("account/index.html", customers=customers,page=page, total_pages=total_pages)


@app.route("/customers/register",methods= ("GET","POST"))
def customer_add():
    """Add new customer to database"""

    if request.method == "POST":
        
        name = request.form["name"]
        address = request.form["address"]
        phone = request.form["phone"]
        email = request.form["email"]
        error = None

        if not name:
            error = "Name is required."
        if not email:
            error = "Email is required."
        if not address:
            error = "Address is required."
        if not phone:
            error = "Phone is required."

        if not phone.isdigit() or len(phone)>15:
            error = "Phone is required to be max 15 digits."

        if aux.has_digits(name):
            error = "Name is required to be only charecters."

        if error is not None:
            flash(error)
        else:
            with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                    customer = cur.execute(
                        """
                        SELECT max(cust_no) as last
                        FROM customer;
                        """,
                        {},
                    ).fetchone()
                    log.debug(f"Found {cur.rowcount} rows.")
                    log.debug(f"Found {customer[0]} rows.")

                cust_no = int(customer[0]) +1
                cust_no = str(cust_no)

                try:
                    with conn.cursor(row_factory=namedtuple_row) as cur:
                        cur.execute(
                            """
                            INSERT INTO customer VALUES (%(cust_no)s, %(name)s, %(email)s, %(phone)s, %(address)s);
                            """,
                            {"cust_no": cust_no, "name": name, "email": email, "phone": phone, "address": address},
                        )
                        log.debug(f"Inserted {cur.rowcount} rows.")
                except Exception as e:
                    error = "An error occurred while inserting the customer: " + str(e)
                    flash(error)

            return redirect(url_for("customer_index"))

    return render_template("account/add_customer.html")

@app.route("/customers/<cust_no>/profile", methods=("GET",))
def customer_profile(cust_no):

    with pool.connection() as conn:

        with conn.cursor(row_factory=namedtuple_row) as cur:
            customer_orders = cur.execute(
                """
                SELECT order_no FROM orders WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no":cust_no},
            ).fetchall()
            log.debug(f"Found {cur.rowcount} rows.")

        with conn.cursor(row_factory=namedtuple_row) as cur:
            customer_info = cur.execute(
                """
                SELECT * FROM customer WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no":cust_no},
            ).fetchone()


    return render_template("account/profile.html", customer_orders=customer_orders,customer_info=customer_info)

@app.route("/customers/<cust_no>/<order_no>", methods=("GET","POST"))
def order_status(cust_no, order_no):

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            log.debug(f"Found {order_no} ,{cust_no}rows.")
            contains= cur.execute(
                """
                SELECT p.name, p.sku, c.qty, c.qty*p.price as total_p 
                FROM contains c
                JOIN product p USING (sku)
                WHERE order_no = %(order_no)s;
                """,
                {"order_no":order_no },
            ).fetchall()

        with conn.cursor(row_factory=namedtuple_row) as cur:
            paid=cur.execute(
                """
                SELECT cust_no, order_no
                FROM pay
                WHERE order_no = %(order_no)s
                AND cust_no = %(cust_no)s;
                """,
                {"order_no": order_no, "cust_no": cust_no},
            ).fetchone()
        
        if request.method == "POST":

            with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                    
                    contains= cur.execute(
                        """
                        INSERT INTO pay VALUES (%(order_no)s,%(cust_no)s);
                        """,
                        {"order_no":order_no,"cust_no":cust_no },
                    )

                return redirect(url_for("order_status", order_no=order_no, cust_no=cust_no))

        if paid is not None:
            paid = True
        else:
            paid = False


    return render_template("account/order.html", contains=contains, paid=paid, order_no=order_no, cust_no=cust_no )

@app.route("/customers/<cust_no>/make_order", methods=("GET","POST"))
def make_order(cust_no):
    
    log.debug(f"Found {request.form} rows.")
    if "cart" not in request.args:
        session.clear()

    cart = session.get('cart', {})

    page = int(request.args.get('page', 1))
    per_page = 4
    offset = (page - 1) * per_page

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            products = cur.execute(
                """
                SELECT sku,name, description, price
                FROM product
                ORDER BY price
                LIMIT %(per_page)s OFFSET %(offset)s;
                """,
                {"per_page":per_page,"offset":offset},
            ).fetchall()
            log.debug(f"Found {cur.rowcount} rows.")

        with conn.cursor(row_factory=namedtuple_row) as cur:
            all_products = cur.execute(
                """
                SELECT count(*) as total
                FROM product;
                """,
                {},
            ).fetchone().total
            log.debug(f"Found {cur.rowcount} rows.")

    total_pages = math.ceil(all_products / per_page)

    if request.method == "POST":
    
        if "add" in request.form:
            sku = str(request.form["add"])
            qty = int(request.form[sku])
            cart[sku]=qty
            session['cart'] = cart
            log.debug(f"Found {cur.rowcount} rows.")

        elif "checkout" in request.form:
            
            with conn.cursor(row_factory=namedtuple_row) as cur:
                    order = cur.execute(
                        """
                        SELECT max(order_no) as last
                        FROM orders;
                        """,
                        {},
                    ).fetchone()

            order_no = int(order[0]) +1


            with conn.cursor(row_factory=namedtuple_row) as cur:

                cur.execute(
                    """
                    BEGIN;
                    """,
                    {},
                )

                cur.execute(
                    """
                    INSERT INTO orders VALUES(%(order_no)s,%(cust_no)s,current_date);
                    """,
                    {"cust_no":cust_no,"order_no":order_no},
                )

                for key in cart:
                    cur.execute(
                    """
                    INSERT INTO contains VALUES(%(order_no)s,%(sku)s,%(qty)s);
                    """,
                    {"order_no":order_no,"sku":key,"qty":cart[key]},
                )
                cur.execute(
                    """
                    COMMIT;
                    """,
                )
            session.clear()
            flash("Order placed successfully!")
            return redirect(url_for("customer_profile",cust_no=cust_no))
        
    return render_template("account/make_order.html", products=products,page=page, total_pages=total_pages,cust_no=cust_no,cart=cart)

@app.route("/products/<sku>/edit_supplier",methods=("GET","POST"))
def supplier_edit(sku):

    if request.method == "POST" :

        if 'confirmation' in request.form and "yes"==request.form['confirmation']:
            tin = request.args.get('tin')
            with pool.connection() as conn:
                try:
                    with conn.cursor(row_factory=namedtuple_row) as cur:
                                cur.execute(
                                """
                                DELETE FROM delivery WHERE tin = %(tin)s;
                                """,
                                {"tin":tin},
                            )
                except Exception as e:
                    error = "An error occurred while inserting the product: " + str(e)
                    flash(error)

                try:
                    with conn.cursor(row_factory=namedtuple_row) as cur:
                                cur.execute(
                                """
                                DELETE FROM supplier WHERE tin = %(tin)s;
                                """,
                                {"tin":tin},
                            )
                except Exception as e:
                        error = "An error occurred while inserting the product: " + str(e)
                        flash(error)

            return redirect(url_for("supplier_edit",sku=sku))
        
        elif 'confirmation' in request.form:
            return redirect(url_for("supplier_edit",sku=sku))

        with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                        delivery = cur.execute(
                        """
                        SELECT address FROM delivery WHERE tin = %(tin)s;
                        """,
                        {"tin":request.form['delete']},
                    ).fetchall()
                log.debug(f"Found {delivery} rows.")

        if delivery :
            return render_template("product/show_dependecie.html",tin=request.form['delete'],dependencies = delivery,sku=sku)
        
        else:
            try:
                with pool.connection() as conn:
                    with conn.cursor(row_factory=namedtuple_row) as cur:
                            cur.execute(
                            """
                            DELETE FROM supplier WHERE tin = %(tin)s;
                            """,
                            {"tin":request.form['delete']},
                        )
            except Exception as e:
                        error = "An error occurred while inserting the product: " + str(e)
                        flash(error)

            return redirect(url_for("supplier_edit",sku=sku))
    

    page = int(request.args.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page

    with pool.connection() as conn:
            with conn.cursor(row_factory=namedtuple_row) as cur:
                suppliers = cur.execute(
                    """
                    SELECT tin ,name, address, date
                    FROM supplier
                    WHERE sku = %(sku)s
                    ORDER BY date
                    LIMIT %(per_page)s OFFSET %(offset)s;
                    """,
                    {"per_page":per_page,"offset":offset,"sku":sku},
                ).fetchall()
                log.debug(f"Found {cur.rowcount} rows.")

            with conn.cursor(row_factory=namedtuple_row) as cur:
                all_suppliers = cur.execute(
                """
                SELECT count(*) as total
                FROM supplier
                WHERE sku = %(sku)s;
                """,
                {"sku":sku},
            ).fetchone().total
            log.debug(f"Found {all_suppliers} rows.")

    total_pages = math.ceil(all_suppliers / per_page)

    return render_template("product/supplier_edit.html",sku=sku,suppliers=suppliers,page=page, total_pages=total_pages)






@app.route("/porducts/<sku>/add_supplier",methods=("GET","POST"))
def supplier_add(sku):

    if request.method == "POST":
        
        name = request.form["name"]
        tin = request.form["tin"]
        address = request.form["address"]
        error = None

        if not name:
            error = "Name is required."
        if not address:
            error = "Address is required."
        if not tin:
            error = "TIN is required."

        if not tin.isnumeric() or len(tin)>20:
            error = "TIN is required to be max 20 digits."

        if error is not None:
            flash(error)
            return render_template("product/add_supplier.html",sku=sku,error=error)

        with pool.connection() as conn:
            with conn.cursor(row_factory=namedtuple_row) as cur:
                        exists = cur.execute(
                            """
                            SELECT tin FROM supplier WHERE tin = %(tin)s;
                            """,
                            {"tin":tin},
                        ).fetchone()
        if exists is not None:
            return render_template("product/add_supplier.html",sku=sku,error="TIN already exists.")
        
        with pool.connection() as conn:
            with conn.cursor(row_factory=namedtuple_row) as cur:
                        cur.execute(
                            """
                            INSERT INTO supplier VALUES (%(tin)s, %(name)s, %(address)s, %(sku)s, current_date);
                            """,
                            {"sku":sku,"tin":tin,"name":name,"address":address},
                        )
        return redirect(url_for("supplier_edit",sku=sku))
    return render_template("product/add_supplier.html", sku=sku)








@app.route("/products", methods=("GET","POST"))
def product_index():
    """Show all the accounts, most recent first."""

    page = int(request.args.get('page', 1))
    per_page = 5
    offset = (page - 1) * per_page

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            products = cur.execute(
                """
                SELECT sku,name, description, price
                FROM product
                ORDER BY price
                LIMIT %(per_page)s OFFSET %(offset)s;
                """,
                {"per_page":per_page,"offset":offset},
            ).fetchall()
            log.debug(f"Found {cur.rowcount} rows.")

        with conn.cursor(row_factory=namedtuple_row) as cur:
            all_products = cur.execute(
                """
                SELECT count(*) as total
                FROM product;
                """,
                {},
            ).fetchone().total
            log.debug(f"Found {cur.rowcount} rows.")

    total_pages = math.ceil(all_products / per_page)

    # API-like response is returned to clients that request JSON explicitly (e.g., fetch)
    if (
        request.accept_mimetypes["application/json"]
        and not request.accept_mimetypes["text/html"]
    ):
        return jsonify(products)


    return render_template("product/product.html", products=products,page=page, total_pages=total_pages)

@app.route("/product/register",methods=("GET","POST"))
def product_add():

    if request.method == "POST":
        
        sku = request.form["sku"]
        name = request.form["name"]
        description = request.form["description"]
        price = request.form["price"]
        ean = request.form["ean"]
        error = None

        if not sku:
            error = "SKU is required."
        if not name:
            error = "Name is required."
        if not description:
            error = "Description is required."
        if not price:
            error = "Price is required."

        if not float(price) :
            error = "Price is required to be numeric."

        if ean:
            if not ean.isdigit():
                error = "EAN is required to be numeric."

        if error is not None:
            flash(error)

        else:
            with pool.connection() as conn:

                with conn.cursor(row_factory=namedtuple_row) as cur:
                        exists = cur.execute(
                            """
                            SELECT sku FROM product WHERE sku = %(sku)s;
                            """,
                            {"sku": sku},
                        ).fetchone()
                if exists is not None:
                    return render_template("product/add_product.html",error="SKU already exists.")

                try:
                    log.debug(f"Inserted {price} prices.")
                    with conn.cursor(row_factory=namedtuple_row) as cur:
                        cur.execute(
                            """
                            INSERT INTO product VALUES (%(sku)s, %(name)s, %(description)s, %(price)s, %(ean)s);
                            """,
                            {"sku": sku, "name": name, "description": description, "price": price, "ean": ean or None},
                        )
                        log.debug(f"Inserted {cur.rowcount} rows.")
                except Exception as e:
                    error = "An error occurred while inserting the product: " + str(e)
                    flash(error)

            return redirect(url_for("product_index"))

    return render_template("product/add_product.html")

@app.route("/products/<sku>/edit",methods=("GET","POST"))
def product_edit(sku):

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            product = cur.execute(
                """
                SELECT * FROM product WHERE sku = %(sku)s;
                """,
                {"sku":sku},
            ).fetchone()
    
    if request.method =="POST":

        if 'description' in request.form:

            description = request.form["description"]

            with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                    cur.execute(
                        """
                        UPDATE product SET description = %(description)s WHERE sku = %(sku)s ;
                        """,
                        {"description":description, "sku":sku},
                    )

        if 'price' in request.form:
            
            price = request.form["price"]
            error = None
            if not price:
                error = "Price is required."

            if not float(price) :
                error = "Price is required to be numeric."

            if error is not None:
                flash(error)

            with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                    cur.execute(
                        """
                        UPDATE product SET price = %(price)s WHERE sku = %(sku)s ;
                        """,
                        {"price":price,"sku":sku},
                    )
        flash("SAVED.")

        return redirect(url_for("product_edit",sku = sku ))
    
    return render_template("product/product_edit.html",product=product)


@app.route("/accounts/<cust_no>/update", methods=("GET", "POST"))
def customer_update(cust_no):
    """Update the account balance."""

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            customer = cur.execute(
                """
                SELECT cust_no, branch_name, balance
                FROM account
                WHERE account_number = %(cust_no)s;
                """,
                {"account_number": cust_no},
            ).fetchone()
            log.debug(f"Found {cur.rowcount} rows.")

    if request.method == "POST":
        balance = request.form["balance"]

        error = None

        if not balance:
            error = "Balance is required."

        if not float(balance):
            error = "Balance is required to be numeric."

        if error is not None:
            flash(error)
        else:
            with pool.connection() as conn:
                with conn.cursor(row_factory=namedtuple_row) as cur:
                    cur.execute(
                        """
                        UPDATE account
                        SET balance = %(balance)s
                        WHERE account_number = %(account_number)s;
                        """,
                        {"account_number": cust_no, "balance": balance},
                    )
                conn.commit()
            return redirect(url_for("account_index"))

    return render_template("account/update.html", account=customer)


@app.route("/customers/<int:cust_no>/confirm_delete", methods=["GET"])
def confirm_delete_c(cust_no):
    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            # Retrieve customer information
            customer_info = cur.execute(
                """
                SELECT * FROM customer WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no": cust_no},
            ).fetchone()

            order_info= cur.execute(
                """
                SELECT order_no
                FROM orders
                WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no": cust_no}
            ).fetchall()            
            # Retrieve order numbers associated with the customer
            cur.execute(
                """
                SELECT order_no
                FROM orders
                WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no": cust_no}
            )
            order_nos = [row.order_no for row in cur.fetchall()]

            # Retrieve pay, process, and contains information
            pay = []
            process = []
            contains = []

            for order_no in order_nos:
                pay_result = cur.execute(
                    """
                    SELECT cust_no FROM pay
                    WHERE cust_no = %(cust_no)s;
                    """,
                    {"cust_no": cust_no},
                ).fetchall()
                pay.extend(pay_result)

                process_result = cur.execute(
                    """
                    SELECT order_no FROM process
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
                process.extend(process_result)

                contains_result = cur.execute(
                    """
                    SELECT order_no FROM contains
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
                contains.extend(contains_result)

    return render_template("account/confirm_delete.html", customer_info=customer_info, order_info=order_info, pay=pay, process=process, contains=contains)



@app.route("/customers/<int:cust_no>/delete", methods=("POST",))
def customer_delete(cust_no):
    """Delete the customer from multiple tables."""

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            # Retrieve all order_no values associated with the customer
            cur.execute(
                """
                SELECT order_no
                FROM orders
                WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no": cust_no}
            )
            order_nos = [row.order_no for row in cur.fetchall()]

            for order_no in order_nos:
                # Delete rows associated with each order_no
                cur.execute(
                    """
                    DELETE FROM pay
                    WHERE cust_no = %(cust_no)s;
                    """,
                    {"cust_no": cust_no},
                )
                cur.execute(
                    """
                    DELETE FROM process
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )
                cur.execute(
                    """
                    DELETE FROM contains
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )

                # Delete the order itself
                cur.execute(
                    """
                    DELETE FROM orders
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )

            # Delete the customer
            cur.execute(
                """
                DELETE FROM customer
                WHERE cust_no = %(cust_no)s;
                """,
                {"cust_no": cust_no},
            )

            conn.commit()

    return redirect(url_for("customer_index"))


@app.route("/products/<sku>/confirm_delete", methods=["GET"])
def confirm_delete_p(sku):
    """Delete the product."""

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            cur.execute(
                """
                SELECT order_no
                FROM contains
                WHERE sku = %(sku)s;
                """,
                {"sku": sku}
            )
            order_nos = [row.order_no for row in cur.fetchall()]
            
            cur.execute(
                """
                SELECT tin
                FROM supplier
                WHERE sku = %(sku)s;
                """,
                {"sku": sku}
            )
            TINs = [row.tin for row in cur.fetchall()]

            pay = []
            process = []
            contains = []

            for order_no in order_nos:
                # Delete rows associated with each order_no
                pay_results=cur.execute(
                    """
                    SELECT order_no FROM pay
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
                pay.extend(pay_results)

                process_result=cur.execute(
                    """
                    SELECT order_no FROM process
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
                process.extend(process_result)

                contains_results=cur.execute(
                    """
                    SELECT order_no FROM contains
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
                contains.extend(contains_results)

                # Delete the order itself
                order_info=cur.execute(
                    """
                    SELECT order_no FROM orders
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                ).fetchall()
            
            delivery = []

            for TIN in TINs:
                # Delete rows associated with each TIN
                delivery_results=cur.execute(
                    """
                    SELECT tin FROM delivery
                    WHERE tin = %(tin)s;
                    """,
                    {"tin": TIN},
                ).fetchall()
                delivery.extend(delivery_results)
                
            supplier=cur.execute(
                """
                SELECT sku FROM supplier
                WHERE sku = %(sku)s;
                """,
                {"sku": sku},
            ).fetchall()
            
            product=cur.execute(
                """
                SELECT * FROM product
                WHERE sku = %(sku)s;
                """,
                {"sku": sku},
            ).fetchone()
            
            
    return render_template("product/confirm_delete.html", product=product, order_info=order_info, supplier=supplier, pay=pay, process=process, contains=contains, delivery=delivery)

@app.route("/product/<sku>/delete", methods=("POST",))
def product_delete(sku):
    """Delete the product."""

    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            cur.execute(
                """
                SELECT order_no
                FROM contains
                WHERE sku = %(sku)s;
                """,
                {"sku": sku}
            )
            order_nos = [row.order_no for row in cur.fetchall()]
            
            cur.execute(
                """
                SELECT tin
                FROM supplier
                WHERE sku = %(sku)s;
                """,
                {"sku": sku}
            )
            TINs = [row.tin for row in cur.fetchall()]
            
            for order_no in order_nos:
                # Delete rows associated with each order_no
                cur.execute(
                    """
                    DELETE FROM pay
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )
                cur.execute(
                    """
                    DELETE FROM process
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )
                cur.execute(
                    """
                    DELETE FROM contains
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )

                # Delete the order itself
                cur.execute(
                    """
                    DELETE FROM orders
                    WHERE order_no = %(order_no)s;
                    """,
                    {"order_no": order_no},
                )
                
            for TIN in TINs:
                # Delete rows associated with each TIN
                cur.execute(
                    """
                    DELETE FROM delivery
                    WHERE tin = %(tin)s;
                    """,
                    {"tin": TIN},
                )
                
            cur.execute(
                """
                DELETE FROM supplier
                WHERE sku = %(sku)s;
                """,
                {"sku": sku},
            )
            
            cur.execute(
                """
                DELETE FROM product
                WHERE sku = %(sku)s;
                """,
                {"sku": sku},
            )
            
            
        conn.commit()
    return redirect(url_for("product_index"))

@app.route("/ping", methods=("GET",))
def ping():
    log.debug("ping!")
    return jsonify({"message": "pong!", "status": "success"})


if __name__ == "__main__":
    app.run()
