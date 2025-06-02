from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    mother_name = fields.Char(string="اسم الأم")
    birth_date = fields.Date(string="تاريخ الميلاد")
    weight = fields.Float(string="الوزن (كغم)")
    height = fields.Float(string="الطول (سم)")
    visible_marks = fields.Text(string="العلامات الظاهرة")
    signature_image = fields.Binary(string="توقيع ولي الأمر")
    is_player = fields.Boolean(string="لاعب", default=False)
    player_tag_id = fields.Many2one(
        'res.partner.category', 
        string="فئة اللاعب", 
        domain=[('parent_id', '=', False)], 
        help="اختر فئة (تصنيف) للاتصال إن كان لاعبًا"
    )
