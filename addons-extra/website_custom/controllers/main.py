
import json
import logging

from datetime import datetime
from werkzeug.exceptions import Forbidden, NotFound
from werkzeug.urls import url_decode, url_encode, url_parse

from odoo import fields, http, SUPERUSER_ID, tools, _
from odoo.fields import Command
from odoo.http import request, route
from odoo.addons.website.controllers.form import WebsiteForm
from odoo.addons.website.controllers import main
from odoo.addons.payment.controllers import portal as payment_portal
from odoo.exceptions import AccessError, MissingError, ValidationError


_logger = logging.getLogger(__name__)

class WebsiteSale(payment_portal.PaymentPortal):

    @http.route('/sale/confirmation', type='http', auth='public', website=True, sitemap=False)
    def sale_confirmation(self, **post):

        order = request.website.sale_get_order()
        print("order ", order)
        order.action_confirm()
        mail_values = {
            'subject': f"Commande {order.name} confirmée",
            'email_to': f"{request.env.company.email}",
            'body_html': f"La commande {order.name} a été confirmé par le client veuillez s'il vous plait procéder à la livraison",
        }
        mail = request.env['mail.mail'].sudo().create(mail_values)
        mail.send()

        # Send email to customer
        # Generate the list of items in the order
        items_html = "<ul>"
        for line in order.order_line:
            items_html += f"<li>{line.product_id.name} - Quantité: {line.product_uom_qty} - Prix: {line.price_unit}</li>"
        items_html += "</ul>"

        order_mail_values = {
            'subject': f"Commande {order.name} confirmée",
            'email_to': order.partner_id.email,
            'body_html': f"""
                        <p>Bonjour {order.partner_id.name},</p>
                        <p>Votre commande <strong>{order.name}</strong> a été confirmée.</p>
                        <p>Voici la liste des articles commandés:</p>
                        {items_html}
                        <p>Notre équipe procédera à la livraison dans les heures qui suivent.</p>
                        <p>Merci pour votre confiance.</p>
                        <p>Cordialement,<br/>L'équipe de {request.env.user.company_id.name}</p>
                    """,
        }
        order_mail = request.env['mail.mail'].sudo().create(order_mail_values)
        order_mail.send()
        return request.render('website_custom.confirmation_page')


    def _get_mandatory_fields_billing(self, country_id=False):
        print("_get_mandatory_fields_billing")
        req = ["name", "email"]

        return req

    def _check_shipping_partner_mandatory_fields(self, partner_id):
        print("_check_shipping_partner_mandatory_fields")
        ''' return True if all mandatory fields for shipping address are complete '''
        shipping_fields_required = self._get_mandatory_fields_shipping(partner_id.country_id.id)
        return all(partner_id.read(shipping_fields_required)[0].values())

    def _get_mandatory_fields_shipping(self, country_id=False):
        req = ["name", "phone"]

        return req

    def checkout_form_validate(self, mode, all_form_values, data):
        # mode: tuple ('new|edit', 'billing|shipping')
        # all_form_values: all values before preprocess
        # data: values after preprocess
        error = dict()
        error_message = []

        if data.get('partner_id'):
            partner_su = request.env['res.partner'].sudo().browse(int(data['partner_id'])).exists()
            if partner_su:
                name_change = 'name' in data and partner_su.name and data['name'] != partner_su.name
                email_change = 'email' in data and partner_su.email and data['email'] != partner_su.email

                # Prevent changing the partner name if invoices have been issued.
                if name_change and not partner_su._can_edit_name():
                    error['name'] = 'error'
                    error_message.append(_(
                        "Changing your name is not allowed once invoices have been issued for your"
                        " account. Please contact us directly for this operation."
                    ))

                # Prevent change the partner name or email if it is an internal user.
                if (name_change or email_change) and not all(partner_su.user_ids.mapped('share')):
                    error.update({
                        'name': 'error' if name_change else None,
                        'email': 'error' if email_change else None,
                    })
                    error_message.append(_(
                        "If you are ordering for an external person, please place your order via the"
                        " backend. If you wish to change your name or email address, please do so in"
                        " the account settings or contact your administrator."
                    ))

        # Required fields from form
        required_fields = [f for f in (all_form_values.get('field_required') or '').split(',') if f]

        # Required fields from mandatory field function
        country_id = int(data.get('country_id', False))

        _update_mode, address_mode = mode
        if address_mode == 'shipping':
            required_fields += self._get_mandatory_fields_shipping(country_id)
        else: # 'billing'
            required_fields += self._get_mandatory_fields_billing(country_id)
            if all_form_values.get('use_same'):
                # If the billing address is also used as shipping one, the phone is required as well
                # because it's required for shipping addresses
                required_fields.append('phone')

        # error message for empty required fields
        for field_name in required_fields:
            val = data.get(field_name)
            if isinstance(val, str):
                val = val.strip()
            if not val:
                error[field_name] = 'missing'

        # email validation
        if data.get('email') and not tools.single_email_re.match(data.get('email')):
            error["email"] = 'error'
            error_message.append(_('Invalid Email! Please enter a valid email address.'))

        # vat validation
        Partner = request.env['res.partner']
        if data.get("vat") and hasattr(Partner, "check_vat"):
            if country_id:
                data["vat"] = Partner.fix_eu_vat_number(country_id, data.get("vat"))
            partner_dummy = Partner.new(self._get_vat_validation_fields(data))
            try:
                partner_dummy.sudo().check_vat()
            except ValidationError as exception:
                error["vat"] = 'error'
                error_message.append(exception.args[0])

        if [err for err in error.values() if err == 'missing']:
            error_message.append(_('Some required fields are empty.'))

        return error, error_message

