from urlparse import urlparse, urljoin
from flask import request, url_for, redirect
from flask_wtf import Form, FlaskForm
from wtforms import HiddenField, StringField, PasswordField, BooleanField, TextAreaField, SelectField, SubmitField


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


def get_redirect_target():
    for target in request.args.get('next'), request.referrer:
        if not target:
            continue
        if is_safe_url(target):
            return target


class RedirectForm(FlaskForm):
    next = HiddenField()

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        if not self.next.data:
            self.next.data = get_redirect_target() or ''

    def redirect(self, endpoint='index', **values):
        if is_safe_url(self.next.data):
            return redirect(self.next.data)
        target = get_redirect_target()
        return redirect(target or url_for(endpoint, **values))


class LoginForm(RedirectForm):
    username = StringField('Username')
    password = PasswordField('Password')


class Stage1Form(FlaskForm):
    page_type = SelectField('Page type', choices=[('body', 'Document body text'),
                                                  ('index', 'Index page'),
                                                  ('petition', 'Petition'),
                                                  ('answers', 'Answers to a Petition'),
                                                  ('judgement', 'Judgement on a Petition'),
                                                  ('multiple', 'Multiple documents on page'),
                                                  ('unknown', 'Other / Unknown')
                                                  ])
    handwriting = BooleanField('This page contains mostly handwriting')
    bad_crop = BooleanField("The cropped image doesn't show all the text on the page")
    page_issue = BooleanField('This page has other image issues (please describe)')
    issue_description = TextAreaField('Issues with this page')
    submit = SubmitField("Submit")


def stage2form_factory(page):
    class Stage2Form(FlaskForm):
        save = SubmitField("Save and continue")
        finalise = SubmitField("Finalise")
    F = Stage2Form
    lines = page.lines
    for line in lines:
        line_text = StringField(line.ocr, default=line.corrected)
        is_marginalia = BooleanField("Marginalia", default=line.is_marginalia)
        not_found = BooleanField("Line not found", default=line.not_found)
        setattr(F, "line-%s"%line.position,line_text)
        setattr(F, "line-%s-m"%line.position, is_marginalia)
        setattr(F, "line-%s-n"%line.position, not_found)
    return F


class Stage3Form(FlaskForm):
    finalise = SubmitField("Complete submission")
    stage1 = SubmitField("Fix an error with the page information")
    stage2 = SubmitField("Fix an error with the OCR transcription")
