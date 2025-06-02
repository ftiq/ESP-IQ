{
  "name": "Partner as Player",
  "version": "1.0",
  "category": "Contacts",
  "summary": "توسيع res.partner بحيث يصبح سجل لاعب (Player)",
  "description": "هذه الوحدة تضيف حقولًا خاصّة باللاعب مع ربط تقرير التسجيل.",
  "author": "Your Company / اسمكم",
  "depends": ["base"],
  "data": [
    "views/res_partner_views.xml",
    "report/report_registration.xml",
    "report/registration_templates.xml"
  ],
  "installable": True,
  "application": False
}