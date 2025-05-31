# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    zk_biometric_sync_required = fields.Boolean(
        string="يتطلب مزامنة البصمة",
        default=False,
        help="يشير إلى أن حالة الاشتراك تغيرت وتتطلب مزامنة مع أجهزة البصمة"
    )
    
    def check_expired_subscriptions(self, *args):
        """وظيفة مجدولة للتحقق من الاشتراكات المنتهية وتعطيل البصمات
        
        يمكن استدعاء هذه الدالة من إجراء مجدول (بدون معاملات) أو من زر في واجهة المستخدم (بمعامل إضافي).
        *args: تستخدم لقبول أي معاملات إضافية عند الاستدعاء من واجهة المستخدم
        """
        today = fields.Date.today()
        # البحث عن الاشتراكات المنتهية (أوامر البيع المتكررة)
        expired_subscriptions = self.env['sale.order'].search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'open'),
            ('next_invoice_date', '<', today),
        ])
        
        _logger.info("تم العثور على %s اشتراك منتهٍ للتحقق من البصمات", len(expired_subscriptions))
        
        for subscription in expired_subscriptions:
            partner = subscription.partner_id
            if partner and partner.zk_biometric_id and partner.zk_status == 'active':
                # تعطيل البصمة لأن الاشتراك منتهٍ
                _logger.info("تعطيل بصمة العميل %s (معرف البصمة: %s) بسبب انتهاء الاشتراك",
                            partner.name, partner.zk_biometric_id)
                
                # تحديث حالة البصمة في سجل العميل
                partner.write({'zk_status': 'disabled'})
                
                # تحديث حقول البصمة الجديدة
                partner.write({
                    'zk_status': 'disabled',
                    'fingerprint_active': False
                })
                
                # التأكد من وجود معرف بصمة في الحقول الجديدة
                if not partner.fingerprint_id and partner.zk_biometric_id:
                    partner.fingerprint_id = partner.zk_biometric_id
                    partner.has_fingerprint = True
                
                # محاولة تعطيل البصمة في جميع الأجهزة المتصلة
                devices = self.env['zk.device'].search([('active', '=', True)])
                for device in devices:
                    # تمرير كائن الشريك بدلاً من معرف البصمة فقط
                    device.disable_user(partner)
        
        return True
    
    def write(self, vals):
        """تجاوز دالة الكتابة لمراقبة التغييرات في حالة الاشتراك"""
        # تسجيل التغييرات المطلوبة للتحليل لاحقًا
        is_subscription_change = self.is_subscription and ('subscription_state' in vals or 'next_invoice_date' in vals)
        
        # التحقق من هل تمت إضافة حالة إلغاء
        is_cancellation = 'state' in vals and vals['state'] == 'cancel'
        
        # استدعاء الدالة الأصلية لتنفيذ التغييرات
        result = super(SaleOrder, self).write(vals)
        
        # التحقق مما إذا تم تجديد الاشتراك أو تغيرت حالته
        if is_subscription_change or is_cancellation:
            for subscription in self:
                partner = subscription.partner_id
                if partner and partner.zk_biometric_id:
                    # تحديد ما إذا كان الاشتراك نشطًا الآن
                    today = fields.Date.today()
                    # إذا كان هناك إلغاء أو تعليق ، فهو غير نشط
                    if subscription.state == 'cancel' or is_cancellation:
                        is_active = False
                    else:
                        is_active = (subscription.next_invoice_date and 
                                    subscription.next_invoice_date >= today and
                                    subscription.subscription_state == 'open')
                    
                    if is_active and partner.zk_status == 'disabled':
                        # تفعيل البصمة لأن الاشتراك تم تجديده
                        _logger.info("تفعيل بصمة العميل %s (معرف البصمة: %s) بعد تجديد الاشتراك",
                                    partner.name, partner.zk_biometric_id)
                        
                        # تحديث حالة البصمة في سجل العميل
                        partner.write({
                            'zk_status': 'active',
                            'fingerprint_active': True,
                            'has_fingerprint': True
                        })
                        
                        # التأكد من وجود معرف بصمة في الحقول الجديدة
                        if not partner.fingerprint_id and partner.zk_biometric_id:
                            partner.fingerprint_id = partner.zk_biometric_id
                        
                        # محاولة تفعيل البصمة في جميع الأجهزة المتصلة
                        devices = self.env['zk.device'].search([('active', '=', True)])
                        for device in devices:
                            # تمرير كائن الشريك بدلاً من معرف البصمة فقط
                            device.enable_user(partner)
                    elif not is_active and partner.zk_status == 'active':
                        # تعطيل البصمة لأن الاشتراك لم يعد نشطًا
                        _logger.info("تعطيل بصمة العميل %s (معرف البصمة: %s) بسبب إغلاق الاشتراك",
                                    partner.name, partner.zk_biometric_id)
                        
                        # تحديث حالة البصمة في سجل العميل
                        partner.write({
                            'zk_status': 'disabled',
                            'fingerprint_active': False
                        })
                        
                        # التأكد من وجود معرف بصمة في الحقول الجديدة
                        if not partner.fingerprint_id and partner.zk_biometric_id:
                            partner.fingerprint_id = partner.zk_biometric_id
                        
                        # محاولة تعطيل البصمة في جميع الأجهزة المتصلة
                        devices = self.env['zk.device'].search([('active', '=', True)])
                        for device in devices:
                            # تمرير كائن الشريك بدلاً من معرف البصمة فقط
                            device.disable_user(partner)
        
        return result
