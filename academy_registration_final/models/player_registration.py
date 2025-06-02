from odoo import models, fields

class AcademyPlayerRegistration(models.Model):
    _name = "academy.player.registration"
    _description = "استمارة تسجيل لاعبي أكاديمية إسبانيول"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="جهة الاتصال (العميل)",
        required=True,
        ondelete="cascade",
    )
    first_name       = fields.Char(string="الاسم الثلاثي", required=True)
    nickname         = fields.Char(string="اللقب")
    mother_name      = fields.Char(string="اسم الأم")
    birth_date       = fields.Date(string="تاريخ الميلاد")
    address          = fields.Char(string="العنوان")
    phone_number     = fields.Char(string="رقم الهاتف")
    weight           = fields.Float(string="الوزن (كغ)")
    height           = fields.Float(string="الطول (سم)")
    visible_marks    = fields.Char(string="العلامات الظاهرة")
    photo_player     = fields.Binary(string="صورة اللاعب")

    parent_name      = fields.Char(string="اسم ولي الأمر", required=True)
    parent_signature = fields.Binary(string="توقيع ولي الأمر")
    parent_date      = fields.Date(string="تاريخ التوقيع")
    commitment_text  = fields.Text(
        string="نص التعهد",
        default=(
            "أتعهد بسلامة الحالة الصحية والبدنية وهو مؤهل للعب، وعليه أوافق على مشاركته "
            "بأكاديمية نادي إسبانيول وفقاً للشروط والأحكام."
        ),
        readonly=True
    )

class ResPartner(models.Model):
    _inherit = "res.partner"

    player_registration_ids = fields.One2many(
        comodel_name="academy.player.registration",
        inverse_name="partner_id",
        string="استمارات تسجيل الأكاديمية"
    )
