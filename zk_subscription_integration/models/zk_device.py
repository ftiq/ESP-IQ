# -*- coding: utf-8 -*-

import logging
import datetime
from datetime import datetime, timedelta
from pytz import timezone, all_timezones
from zk import ZK
from zk.exception import ZKErrorResponse, ZKNetworkError
from socket import timeout

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ZKDevice(models.Model):
    _name = 'zk.device'
    _description = 'جهاز بصمة ZK'
    _inherit = ['mail.thread']
    _rec_name = 'name'

    name = fields.Char(string="اسم الجهاز", required=True, tracking=True)
    ip_address = fields.Char(string="عنوان IP", required=True, tracking=True, help="أدخل عنوان IP لجهاز البصمة أو الشبكة")
    port = fields.Integer(string="رقم المنفذ", default=4370, required=True, tracking=True, help="المنفذ الذي يسمح بالاتصال بالجهاز")
    active = fields.Boolean(string="نشط", default=True)
    location = fields.Char(string="الموقع", help="موقع تركيب الجهاز", tracking=True)
    last_sync = fields.Datetime(string="آخر مزامنة", readonly=True)
    connection_status = fields.Selection([
        ('connected', 'متصل'),
        ('disconnected', 'غير متصل'),
    ], string="حالة الاتصال", default='disconnected', readonly=True, tracking=True)
    device_model = fields.Char(string="موديل الجهاز", tracking=True)
    device_serial = fields.Char(string="الرقم التسلسلي", tracking=True)
    password = fields.Char(string="كلمة المرور", tracking=True, help="حدد كلمة المرور إذا كان جهاز البصمة محميًا بكلمة مرور")
    protocol = fields.Selection(selection=[('tcp', 'TCP'), ('udp', 'UDP')], 
                              string='البروتوكول', required=True, default='tcp', tracking=True,
                              help="UDP مناسب للأجهزة القديمة ذات كميات البيانات الصغيرة، يجب استخدام TCP مع الأجهزة التي تحتوي على كميات أكبر من البيانات")
    ommit_ping = fields.Boolean(string="تخطي فحص الاتصال (Ping)", default=True, tracking=True, 
                              help="عدم محاولة إرسال ping إلى عنوان IP قبل الاتصال بالجهاز")
    time_out = fields.Integer('مهلة الاتصال (ثانية)', default=60, tracking=True, help="حدد الوقت الذي تنتهي فيه الجلسة")
    
    def _get_zk_connection(self):
        """إنشاء اتصال مع جهاز البصمة"""
        self.ensure_one()
        
        _logger.info("محاولة إنشاء اتصال مع جهاز %s على %s:%s", 
                   self.name, self.ip_address, self.port)
        
        force_udp = False
        if self.protocol == 'udp':
            force_udp = True
            _logger.info("استخدام بروتوكول UDP")
        else:
            _logger.info("استخدام بروتوكول TCP")
            
        # معالجة تناقض أسماء الحقول (ipaddress مقابل ip_address)
        ip_address = self.ip_address
        
        # معالجة كلمة المرور
        password = self.password or 0
        
        # إذا كانت كلمة المرور سلسلة نصية، حاول تحويلها إلى رقم
        if isinstance(password, str) and password.isdigit():
            password = int(password)
        
        # التأكد من الطرف الزمني
        timeout = self.time_out or 5
        
        _logger.info("إنشاء اتصال ZK مع الإعدادات: IP=%s, Port=%s, Timeout=%s, Force UDP=%s", 
                   ip_address, self.port, timeout, force_udp)
                   
        try:
            # إنشاء كائن ZK
            zk = ZK(ip_address, port=self.port, timeout=timeout, 
                  password=password, force_udp=force_udp, ommit_ping=self.ommit_ping)
            return zk
        except Exception as e:
            _logger.error("خطأ في إنشاء اتصال ZK: %s", str(e))
            raise
    
    def test_connection(self):
        """اختبار الاتصال بجهاز البصمة"""
        self.ensure_one()
        conn = None
        zk = self._get_zk_connection()
        
        try:
            conn = zk.connect()
            if conn:
                self.write({
                    'connection_status': 'connected',
                    'last_sync': fields.Datetime.now()
                })
                # الحصول على معلومات الجهاز إن أمكن
                try:
                    self.device_model = conn.get_device_name()
                    self.device_serial = conn.get_serialnumber()
                except Exception as e:
                    _logger.warning("تعذر الحصول على معلومات الجهاز: %s", str(e))
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('نجاح'),
                        'message': _('تم الاتصال بجهاز البصمة %s بنجاح') % self.name,
                        'type': 'success',
                    }
                }
        except ZKNetworkError as e:
            if e.args[0] == "Device (ping %s) is Unreachable" % self.ip_address:
                self.write({'connection_status': 'disconnected'})
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('خطأ الاتصال'),
                        'message': _('تأكد من أن الجهاز (ping %s) قيد التشغيل ومتصل بالشبكة') % self.ip_address,
                        'type': 'warning',
                    }
                }
            else:
                self.write({'connection_status': 'disconnected'})
                raise UserError(e)
        except ZKErrorResponse as e:
            self.write({'connection_status': 'disconnected'})
            if e.args[0] == 'Unauthenticated':
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('فشل المصادقة'),
                        'message': _('غير قادر على الاتصال (فشل المصادقة)، يرجى تزويد كلمة المرور الصحيحة للجهاز.'),
                        'type': 'warning',
                    }
                }
            else:
                raise UserError(e)
        except timeout:
            self.write({'connection_status': 'disconnected'})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('انتهت مهلة الاتصال'),
                    'message': _('انتهت مهلة الاتصال، تأكد من تشغيل الجهاز وعدم حظره بواسطة جدار الحماية'),
                    'type': 'warning',
                }
            }
        except Exception as e:
            _logger.error("فشل الاتصال بجهاز البصمة: %s", str(e))
            self.write({'connection_status': 'disconnected'})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('خطأ'),
                    'message': _('فشل الاتصال بجهاز البصمة: %s') % str(e),
                    'type': 'danger',
                }
            }
        finally:
            if conn:
                conn.disconnect()
    
    def enable_user(self, partner_or_id):
        """تفعيل مستخدم في جهاز البصمة
        
        يمكن تمرير إما كائن شريك كامل أو معرف بصمة فقط
        """
        self.ensure_one()
        
        _logger.info("محاولة تفعيل مستخدم على جهاز %s (الآيبي: %s - المنفذ: %s)",
                    self.name, self.ip_address, self.port)
        
        # التحقق من نوع المعامل الممرر
        if isinstance(partner_or_id, str):
            # تم تمرير معرف البصمة فقط (نص)
            user_id = partner_or_id
            _logger.info("تم تمرير معرف البصمة كنص: %s", user_id)
            # البحث عن الشريك بناءً على معرف البصمة
            partner = self.env['res.partner'].search([
                '|',
                ('zk_biometric_id', '=', user_id),
                ('fingerprint_id', '=', user_id)
            ], limit=1)
            if not partner:
                _logger.warning("لم يتم العثور على شريك بمعرف البصمة %s", user_id)
                # نحاول تفعيل المستخدم مباشرة باستخدام المعرف
        else:
            # تم تمرير كائن شريك كامل
            partner = partner_or_id
            _logger.info("تم تمرير كائن شريك: %s (الهوية: %s)", partner.name, partner.id)
            # التحقق من وجود معرف بصمة
            if not partner.fingerprint_id and not partner.zk_biometric_id:
                _logger.warning("لا يمكن تفعيل المستخدم %s (الهوية: %s) - لا يوجد معرف بصمة", 
                            partner.name, partner.id)
                return False
            user_id = partner.fingerprint_id or partner.zk_biometric_id
            _logger.info("معرف البصمة المستخرج من الشريك: %s", user_id)
        
        conn = None
        zk = self._get_zk_connection()
        _logger.info("تم تهيئة الاتصال بجهاز ZK: %s", self.name)
        
        try:
            _logger.info("محاولة الاتصال بجهاز ZK على %s:%s", self.ip_address, self.port)
            conn = zk.connect()
            
            if not conn:
                _logger.error("فشل الاتصال بجهاز %s (الآيبي: %s - المنفذ: %s) عند محاولة تفعيل المستخدم", 
                              self.name, self.ip_address, self.port)
                return False
            
            _logger.info("تم الاتصال بنجاح بجهاز %s", self.name)
                
            # تفعيل المستخدم - إجراء جديد باستخدام منهجية مختلفة
            _logger.info("محاولة تفعيل المستخدم باستخدام الأمر المباشر للجهاز ZK")
            
            # تعطيل الجهاز للقراءة/الكتابة
            _logger.info("تعطيل الجهاز مؤقتًا للكتابة")
            conn.disable_device()
            
            try:
                # التحقق من وجود المستخدم في الجهاز
                _logger.info("التحقق من وجود المستخدم بمعرف %s", user_id)
                users = conn.get_users()
                _logger.info("تم العثور على %d مستخدم في الجهاز", len(users) if users else 0)
                
                # محاولة تفعيل المستخدم باستخدام طريقة جديدة
                from zk.user import User
                
                # التحقق من وجود المستخدم في الجهاز
                user_exists = False
                for user in users:
                    if str(user.user_id) == str(user_id):
                        user_exists = True
                        _logger.info("وجدنا المستخدم المطلوب في الجهاز: %s", user.user_id)
                        # أزل المستخدم ثم أعد إنشاءه كنشط
                        _logger.info("أزل المستخدم القديم لإعادة إنشاءه")
                        conn.delete_user(user_id)
                        break
                
                # إنشاء المستخدم من جديد
                name = ""
                if partner and partner.name:
                    name = partner.name
                elif not name:
                    name = "User " + str(user_id)
                    
                _logger.info("إنشاء مستخدم جديد: ID=%s, الاسم=%s, نشط=True", user_id, name)
                
                # إنشاء مستخدم جديد بشكل مباشر
                new_user = User(user_id=str(user_id), name=name, privilege=0, password='', group_id='', user_id_card='', card=0)
                new_user.enabled = True
                
                # إرسال المستخدم إلى الجهاز
                _logger.info("حفظ المستخدم الجديد في الجهاز")
                conn.set_user(new_user)
                
                # التحقق من النجاح
                _logger.info("التحقق من نجاح العملية")
                users_after = conn.get_users()
                success = False
                
                for user in users_after:
                    if str(user.user_id) == str(user_id) and user.enabled:
                        _logger.info("تم العثور على المستخدم وهو نشط الآن")
                        success = True
                        break
                
                if success:
                    _logger.info("تم تفعيل المستخدم بنجاح")
                else:
                    _logger.warning("لم يتم العثور على المستخدم أو لم يتم تفعيله بعد محاولة التفعيل")
                
            except Exception as ex:
                _logger.error("خطأ أثناء محاولة تفعيل المستخدم: %s", str(ex))
                success = False
                
            _logger.info("إعادة تفعيل الجهاز")
            conn.enable_device()
            
            if success:
                _logger.info("تم تفعيل المستخدم %s (%s) في جهاز %s بنجاح", 
                            partner.name if partner else user_id, user_id, self.name)
                # تحديث حالة الشريك إذا كان موجودًا
                if partner:
                    partner.write({'fingerprint_active': True})
                return True
            else:
                _logger.error("فشل تفعيل المستخدم %s في جهاز %s", user_id, self.name)
                return False
                
        except Exception as e:
            _logger.error("استثناء عند محاولة تفعيل المستخدم %s (%s) في جهاز %s: %s", 
                         partner.name, user_id, self.name, str(e))
            return False
        finally:
            if conn:
                conn.disconnect()
    
    def disable_user(self, partner_or_id):
        """تعطيل مستخدم في جهاز البصمة
        
        يمكن تمرير إما كائن شريك كامل أو معرف بصمة فقط
        """
        self.ensure_one()
        
        _logger.info("محاولة تعطيل مستخدم على جهاز %s (الآيبي: %s - المنفذ: %s)",
                    self.name, self.ip_address, self.port)
        
        # التحقق من نوع المعامل الممرر
        if isinstance(partner_or_id, str):
            # تم تمرير معرف البصمة فقط (نص)
            user_id = partner_or_id
            _logger.info("تم تمرير معرف البصمة كنص: %s", user_id)
            # البحث عن الشريك بناءً على معرف البصمة
            partner = self.env['res.partner'].search([
                '|',
                ('zk_biometric_id', '=', user_id),
                ('fingerprint_id', '=', user_id)
            ], limit=1)
            if not partner:
                _logger.warning("لم يتم العثور على شريك بمعرف البصمة %s", user_id)
                # سنحاول تعطيل المستخدم باستخدام المعرف مباشرة
        else:
            # تم تمرير كائن شريك كامل
            partner = partner_or_id
            _logger.info("تم تمرير كائن شريك: %s (الهوية: %s)", partner.name, partner.id)
            # التحقق من وجود معرف بصمة
            if not partner.fingerprint_id and not partner.zk_biometric_id:
                _logger.warning("لا يمكن تعطيل المستخدم %s (الهوية: %s) - لا يوجد معرف بصمة", 
                            partner.name, partner.id)
                return False
            user_id = partner.fingerprint_id or partner.zk_biometric_id
            _logger.info("معرف البصمة المستخرج من الشريك: %s", user_id)
        
        conn = None
        zk = self._get_zk_connection()
        _logger.info("تم تهيئة الاتصال بجهاز ZK: %s", self.name)
        
        try:
            _logger.info("محاولة الاتصال بجهاز ZK على %s:%s", self.ip_address, self.port)
            conn = zk.connect()
            
            if not conn:
                _logger.error("فشل الاتصال بجهاز %s (الآيبي: %s - المنفذ: %s) عند محاولة تعطيل المستخدم", 
                              self.name, self.ip_address, self.port)
                return False
            
            _logger.info("تم الاتصال بنجاح بجهاز %s", self.name)
            
            # محاولة تعطيل المستخدم بشكل مباشر
            _logger.info("محاولة تعطيل المستخدم باستخدام الأمر المباشر للجهاز ZK")
            
            # نهج مباشر: إما حذف المستخدم أو تعطيله
            _logger.info("تعطيل الجهاز مؤقتًا للكتابة")
            conn.disable_device()
            
            try:
                # طريقة 1: محاولة حذف المستخدم من الجهاز
                _logger.info("محاولة حذف المستخدم بمعرف %s من الجهاز", user_id)
                success = conn.delete_user(user_id=str(user_id))
                _logger.info("نتيجة محاولة الحذف: %s", success)
                
                # طريقة 2: إذا لم ينجح الحذف، نحاول تعطيل المستخدم
                if not success:
                    _logger.info("التحقق من وجود المستخدم بمعرف %s", user_id)
                    users = conn.get_users()
                    _logger.info("تم العثور على %d مستخدم في الجهاز", len(users) if users else 0)
                    
                    # التحقق من وجود المستخدم ومحاولة تعديله
                    from zk.user import User
                    for user in users:
                        if str(user.user_id) == str(user_id):
                            _logger.info("وجدنا المستخدم المطلوب وسنقوم بتعطيله: %s", user.user_id)
                            # إنشاء نسخة معدلة من المستخدم وتعطيلها
                            user.enabled = False
                            conn.set_user(user)
                            success = True
                            _logger.info("تم تعديل حالة المستخدم إلى معطل")
                            break
                
                if not success:
                    _logger.warning("لم يتم العثور على المستخدم لتعطيله")
                
            except Exception as ex:
                _logger.error("خطأ أثناء محاولة تعطيل المستخدم: %s", str(ex))
                success = False
            
            _logger.info("إعادة تفعيل الجهاز")
            conn.enable_device()
            
            if success:
                _logger.info("تم تعطيل المستخدم %s (%s) في جهاز %s بنجاح", 
                            partner.name if partner else user_id, user_id, self.name)
                # تحديث حالة الشريك إذا كان موجودًا
                if partner:
                    partner.write({'fingerprint_active': False})
                return True
            else:
                _logger.error("فشل تعطيل المستخدم %s في جهاز %s", user_id, self.name)
                return False
                
        except Exception as e:
            _logger.error("استثناء عند محاولة تعطيل المستخدم %s (%s) في جهاز %s: %s", 
                          partner.name, user_id, self.name, str(e))
            return False
        finally:
            if conn:
                conn.disconnect()
    
    def sync_partner_fingerprint(self, partner):
        """مزامنة حالة بصمة الشريك مع جهاز البصمة"""
        self.ensure_one()
        
        # التحقق من وجود معرف بصمة باستخدام الطريقة القديمة أو الجديدة
        fingerprint_id = partner.fingerprint_id or partner.zk_biometric_id
        
        if not fingerprint_id:
            _logger.warning("لا يمكن مزامنة الشريك %s (الهوية: %s) - لا يوجد معرف بصمة", 
                         partner.name, partner.id)
            return False
        
        # التأكد من تعيين حقل has_fingerprint
        if not partner.has_fingerprint:
            partner.has_fingerprint = True
            
        # التأكد من أن fingerprint_id معين
        if not partner.fingerprint_id and partner.zk_biometric_id:
            partner.fingerprint_id = partner.zk_biometric_id
        
        # تحديث حالة البصمة بناءً على حالة الاشتراك
        if partner.has_active_subscription and not partner.fingerprint_active:
            # تفعيل البصمة إذا كان لدى الشريك اشتراك نشط والبصمة غير مفعلة
            return self.enable_user(partner)
        elif not partner.has_active_subscription and partner.fingerprint_active:
            # تعطيل البصمة إذا لم يكن لدى الشريك اشتراك نشط والبصمة مفعلة
            return self.disable_user(partner)
        
        # تحديث zk_status للتوافق مع النظام القديم
        if partner.fingerprint_active != (partner.zk_status == 'active'):
            partner.zk_status = 'active' if partner.fingerprint_active else 'disabled'
        
        # لا يلزم تغيير إذا كانت حالة البصمة متطابقة مع حالة الاشتراك
        return True
    
    def sync_all_users(self):
        """مزامنة جميع المستخدمين مع حالة اشتراكاتهم"""
        self.ensure_one()
        _logger.info("بدأ عملية مزامنة جميع المستخدمين على جهاز %s", self.name)
        
        # البحث عن الشركاء الذين لديهم بصمات - سواء بالطريقة القديمة أو الجديدة
        # الطريقة القديمة - استخدام حقل zk_biometric_id
        partners_old = self.env['res.partner'].search([('zk_biometric_id', '!=', False)])
        # الطريقة الجديدة - استخدام حقل fingerprint_id
        partners_new = self.env['res.partner'].search([('fingerprint_id', '!=', False)])
        
        # دمج النتائج وإزالة التكرار
        partners = partners_old | partners_new
        
        _logger.info("تم العثور على %d شريك لديهم بصمات", len(partners))
        
        success_count = 0
        disabled_count = 0
        
        for partner in partners:
            # إجبار إعادة حساب حالة الاشتراك النشط
            partner._compute_has_active_subscription()
            
            # إذا لم يكن لديه حقل has_fingerprint، نقوم بتعيينه بناءً على وجود معرف البصمة
            if not partner.has_fingerprint and (partner.zk_biometric_id or partner.fingerprint_id):
                partner.has_fingerprint = True
                
            # التأكد من أن معرف البصمة موجود ومنسق
            if not partner.fingerprint_id and partner.zk_biometric_id:
                partner.fingerprint_id = partner.zk_biometric_id
                
            if partner.has_active_subscription and (not partner.fingerprint_active):
                # تفعيل المستخدم إذا كان لديه اشتراك نشط وبصمته معطلة
                if self.enable_user(partner):
                    success_count += 1
            elif not partner.has_active_subscription and partner.fingerprint_active:
                # تعطيل المستخدم إذا لم يكن لديه اشتراك نشط وبصمته مفعلة
                if self.disable_user(partner):
                    disabled_count += 1
            
            # تحديث حالة zk_status للتوافق مع النظام القديم
            if partner.fingerprint_active != (partner.zk_status == 'active'):
                partner.zk_status = 'active' if partner.fingerprint_active else 'disabled'
        
        self.write({'last_sync': fields.Datetime.now()})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('اكتملت المزامنة'),
                'message': _('تم تفعيل %s مستخدم وتعطيل %s مستخدم') % (success_count, disabled_count),
                'type': 'success',
            }
        }
        
    @api.model
    def _cron_check_connection(self):
        """إجراء مجدول للتحقق من حالة اتصال أجهزة البصمة
        يتم تشغيل هذا الإجراء دوريًا للتحقق من أن أجهزة البصمة متصلة وتعمل بشكل صحيح"""
        _logger.info("بدء التحقق من اتصال أجهزة البصمة")
        devices = self.search([('active', '=', True)])
        
        connected_count = 0
        disconnected_count = 0
        
        for device in devices:
            try:
                # محاولة الاتصال بالجهاز
                zk = device._get_zk_connection()
                conn = zk.connect()
                if conn:
                    conn.disconnect()
                    if device.connection_status != 'connected':
                        device.write({'connection_status': 'connected', 'last_sync': fields.Datetime.now()})
                    connected_count += 1
                else:
                    if device.connection_status != 'disconnected':
                        device.write({'connection_status': 'disconnected'})
                    disconnected_count += 1
            except Exception as e:
                _logger.warning("خطأ في الاتصال بجهاز %s: %s", device.name, str(e))
                if device.connection_status != 'disconnected':
                    device.write({'connection_status': 'disconnected'})
                disconnected_count += 1
        
        _logger.info("اكتمل التحقق من اتصال أجهزة البصمة: %s متصل، %s غير متصل", 
                   connected_count, disconnected_count)
        return True
        
    @api.model
    def _cron_sync_fingerprints_with_subscriptions(self):
        """إجراء مجدول لمزامنة البصمات مع حالة الاشتراك
        هذا يضمن تعطيل البصمات عند انتهاء الاشتراكات
        وتفعيلها عندما تكون الاشتراكات نشطة"""
        _logger.info("بدء مزامنة البصمات مع حالة الاشتراك")
        
        # 1. أولاً: نتحقق مباشرة من الاشتراكات المنتهية لتعطيل البصمات المرتبطة بها
        today = fields.Date.today()
        _logger.info("البحث عن الاشتراكات المنتهية بتاريخ %s", today)
        
        # البحث عن الاشتراكات المنتهية (بناءً على تاريخ الانتهاء أو حالة الاشتراك)
        expired_subscriptions = self.env['sale.order'].search([
            ('is_subscription', '=', True),
            ('state', '=', 'sale'),
            '|',
            ('subscription_state', '=', '6_churn'),  # إما أن الاشتراك منتهٍ صراحةً
            '&',  # أو أن تاريخ الانتهاء قد حل
            ('end_date', '!=', False),
            ('end_date', '<', today)
        ])
        
        _logger.info("تم العثور على %d اشتراك منتهي", len(expired_subscriptions))
        
        # تجميع الشركاء المرتبطين بالاشتراكات المنتهية
        partners_with_expired_subs = self.env['res.partner']
        for sub in expired_subscriptions:
            partners_with_expired_subs |= sub.partner_id
            _logger.info("الاشتراك %s للشريك %s منتهٍ (تاريخ الانتهاء: %s، الحالة: %s)", 
                       sub.name, sub.partner_id.name, sub.end_date, sub.subscription_state)
        
        # تعطيل البصمات للشركاء الذين انتهت اشتراكاتهم
        disabled_count = 0
        devices = self.search([('connection_status', '=', 'connected')])
        
        # البحث عن الشركاء الذين لديهم بصمات بطريقة متوافقة
        fingerprint_partners = partners_with_expired_subs.filtered(
            lambda p: (p.has_fingerprint and p.fingerprint_active) or 
                      (p.zk_biometric_id and p.zk_status == 'active')
        )
        
        for partner in fingerprint_partners:
            # تحقق من عدم وجود اشتراكات أخرى نشطة
            partner._compute_has_active_subscription()
            if not partner.has_active_subscription:
                _logger.info("تعطيل بصمة الشريك %s بسبب انتهاء الاشتراك", partner.name)
                
                # التأكد من وجود الحقول المطلوبة
                if not partner.has_fingerprint and partner.zk_biometric_id:
                    partner.has_fingerprint = True
                
                if not partner.fingerprint_id and partner.zk_biometric_id:
                    partner.fingerprint_id = partner.zk_biometric_id
                
                # تحديث حالة البصمة
                partner.write({
                    'fingerprint_active': False,
                    'zk_status': 'disabled'
                })
                
                # مزامنة مع أجهزة البصمة
                for device in devices:
                    try:
                        if device.disable_user(partner):
                            disabled_count += 1
                            break  # إذا نجحت على جهاز واحد، لا داعي للاستمرار
                    except Exception as e:
                        _logger.error("خطأ في مزامنة بصمة الشريك %s على الجهاز %s: %s", 
                                    partner.name, device.name, str(e))
        
        # 2. ثم: نتحقق من جميع الشركاء الذين لديهم بصمات
        _logger.info("التحقق من جميع الشركاء الذين لديهم بصمات")
        partners_with_fingerprints = self.env['res.partner'].search([('has_fingerprint', '=', True)])
        
        # للمزامنة الكاملة، نقوم بتشغيل sync_all_users على كل جهاز متصل
        for device in devices:
            try:
                device.sync_all_users()
            except Exception as e:
                _logger.error("خطأ في مزامنة المستخدمين على الجهاز %s: %s", device.name, str(e))
        
        _logger.info("اكتملت مزامنة البصمات مع حالة الاشتراك")
        return True
