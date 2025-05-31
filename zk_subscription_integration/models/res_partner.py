# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # الحقول القديمة - للتوافق مع الكود الحالي
    zk_biometric_id = fields.Char(
        string="معرّف البصمة (قديم)",
        help="المعرّف الفريد للعميل في جهاز البصمة ZK (للتوافق)"
    )
    
    zk_status = fields.Selection([
        ('active', 'مفعلة'),
        ('disabled', 'معطلة'),
    ], string="حالة البصمة (قديم)", default='active',
        help="حالة بصمة العميل في الجهاز (للتوافق)"
    )
    
    # الحقول الجديدة - متوافقة مع النظام الجديد
    has_fingerprint = fields.Boolean(
        string="لديه بصمة",
        default=False,
        help="يشير إلى ما إذا كان الشريك لديه بصمة مسجلة"
    )
    
    fingerprint_id = fields.Char(
        string="معرّف البصمة",
        help="المعرّف الفريد للشريك في جهاز البصمة ZK"
    )
    
    fingerprint_active = fields.Boolean(
        string="بصمة نشطة",
        default=False,
        help="حالة نشاط البصمة - نشطة أو غير نشطة"
    )
    
    has_active_subscription = fields.Boolean(
        string="لديه اشتراك نشط",
        compute='_compute_has_active_subscription',
        store=True,
        help="يشير إلى ما إذا كان العميل لديه اشتراك نشط أم لا"
    )
    
    @api.depends('sale_order_ids', 'sale_order_ids.next_invoice_date', 'sale_order_ids.subscription_state')
    def _compute_has_active_subscription(self):
        """حساب ما إذا كان العميل لديه اشتراك نشط أم لا"""
        today = fields.Date.today()
        for partner in self:
            active_subscription = partner.sale_order_ids.filtered(
                lambda s: s.is_subscription and 
                          s.next_invoice_date and 
                          s.next_invoice_date >= today and
                          s.subscription_state == 'open'
            )
            partner.has_active_subscription = bool(active_subscription)
            
    def action_enable_zk_biometric(self):
        """تفعيل بصمة العميل في جميع أجهزة ZK المتصلة"""
        self.ensure_one()
        
        # التحقق من وجود معرف بصمة (حقل جديد أو قديم)
        fingerprint_id = self.fingerprint_id or self.zk_biometric_id
        if not fingerprint_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('خطأ'),
                    'message': _('لم يتم تعيين معرّف البصمة لهذا العميل'),
                    'type': 'danger',
                }
            }
        
        # تحديث حالة البصمة في كلا الحقلين للتوافق
        self.write({
            'zk_status': 'active',
            'fingerprint_active': True,
            'has_fingerprint': True
        })
        
        # إذا لم يكن لديه حقل fingerprint_id فقم بتعيينه من الحقل القديم
        if not self.fingerprint_id and self.zk_biometric_id:
            self.fingerprint_id = self.zk_biometric_id
        
        # الاتصال بأجهزة ZK وتفعيل البصمة
        devices = self.env['zk.device'].search([('active', '=', True)])
        success_count = 0
        for device in devices:
            # نمرر الشريك كاملاً بدلاً من معرف البصمة فقط
            result = device.enable_user(self)
            if result:
                success_count += 1
                
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم التفعيل'),
                'message': _('تم تفعيل البصمة في %s من أصل %s جهاز') % (success_count, len(devices)),
                'type': 'success',
            }
        }
        
    def action_disable_zk_biometric(self):
        """تعطيل بصمة العميل في جميع أجهزة ZK المتصلة"""
        self.ensure_one()
        
        # التحقق من وجود معرف بصمة (حقل جديد أو قديم)
        fingerprint_id = self.fingerprint_id or self.zk_biometric_id
        if not fingerprint_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('خطأ'),
                    'message': _('لم يتم تعيين معرّف البصمة لهذا العميل'),
                    'type': 'danger',
                }
            }
            
        # تحديث حالة البصمة في كلا الحقلين للتوافق
        self.write({
            'zk_status': 'disabled',
            'fingerprint_active': False
        })
        
        # إذا لم يكن لديه حقل fingerprint_id فقم بتعيينه من الحقل القديم
        if not self.fingerprint_id and self.zk_biometric_id:
            self.fingerprint_id = self.zk_biometric_id
        
        # الاتصال بأجهزة ZK وتعطيل البصمة
        devices = self.env['zk.device'].search([('active', '=', True)])
        success_count = 0
        for device in devices:
            # نمرر الشريك كاملاً بدلاً من معرف البصمة فقط
            result = device.disable_user(self)
            if result:
                success_count += 1
                
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم التعطيل'),
                'message': _('تم تعطيل البصمة في %s من أصل %s جهاز') % (success_count, len(devices)),
                'type': 'success',
            }
        }
